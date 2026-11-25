"""
Agentica policy engine.

Every tool call passes through `PolicyEngine.check()` — the language model never
reaches the operating system any other way. The check is deterministic:

  1. registered tool?          unknown tool                -> DENY
  2. inside the active scope?  card / loaded toolsets      -> DENY otherwise
  3. known target?             this PC or a registered machine with credentials -> DENY otherwise
  4. strict argument schema    (Pydantic, extra=forbid)    -> DENY on invalid args
  5. risk grading              tool assesses the concrete action against live state
                               (no-op -> R0, start -> R1, stop/restart -> R2, ...)
  6. hardline guardrails       protected services, R3      -> DENY, not overridable
  7. policy.yaml rules         first match wins (tool / target / service globs)
  8. tier defaults             R0 allow · R1 confirm · R2 confirm

CONFIRM means: create an approval record bound to the exact validated arguments;
nothing executes until the operator approves it.
"""
from __future__ import annotations

import fnmatch
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import yaml
from pydantic import ValidationError

log = logging.getLogger("agentica.policy")

TIERS = {"R0": "read-only / no change", "R1": "reversible change", "R2": "disruptive change",
         "R3": "destructive or protected"}
DECISIONS = ("allow", "confirm", "deny")
SAFE_DEFAULTS = {"R0": "allow", "R1": "confirm", "R2": "confirm"}

# Hardline: services that may never be stopped or restarted by the agent, whatever
# policy.yaml says. Stopping them destabilises the host, removes security controls,
# or cuts off the remote management Agentica itself depends on.
HARDLINE_WINDOWS = frozenset(s.lower() for s in (
    "RpcSs", "RpcEptMapper", "DcomLaunch", "LSM", "SamSs", "EventLog", "PlugPlay", "Power", "ProfSvc",
    "Schedule", "Winmgmt", "WinRM", "CryptSvc", "Dhcp", "Dnscache", "nsi", "BFE", "mpssvc", "WinDefend",
    "WdNisSvc", "SecurityHealthService", "wscsvc", "Netlogon", "LanmanWorkstation", "TermService",
    "SENS", "SystemEventsBroker", "BrokerInfrastructure", "CoreMessagingRegistrar", "gpsvc", "KeyIso",
    "VaultSvc", "SgrmBroker", "Audiosrv", "AudioEndpointBuilder", "UserManager", "Themes", "W32Time",
))
HARDLINE_LINUX = frozenset((
    "systemd-journald", "systemd-logind", "systemd-udevd", "systemd-networkd", "systemd-resolved",
    "dbus", "dbus-broker", "polkit", "ssh", "sshd", "networkmanager", "network-manager", "auditd",
))


@dataclass
class Assessment:
    """What a tool says about one concrete call, produced before anything executes."""
    risk: str
    summary: str
    reasons: list[str] = field(default_factory=list)
    service: str | None = None     # subject checked against the protected-service list
    stops_service: bool = False    # True when the action would stop a running service
    noop: bool = False             # already in the requested state
    error: str | None = None       # the action cannot be performed as asked -> DENY
    blocked_by: str = "state"      # for `error`: "state" (a fact about the system) or "request" (fix the call)


@dataclass
class Verdict:
    decision: str                  # ALLOW | CONFIRM | DENY
    risk: str
    summary: str
    reasons: list[str]
    target: str
    error: str | None = None
    rule: str | None = None
    args: dict | None = None       # validated arguments (what will execute)
    # Why a DENY happened: "policy" (hardline / rules / defaults — final), "state" (the system's
    # current state rules it out — final), "request" (malformed or out-of-scope call — the model can fix it).
    blocked_by: str | None = None

    def public(self) -> dict:
        out = {"decision": self.decision, "risk": self.risk, "risk_label": TIERS.get(self.risk, ""),
               "summary": self.summary, "reasons": self.reasons, "target": self.target}
        if self.blocked_by:
            out["blocked_by"] = self.blocked_by
        if self.rule:
            out["rule"] = self.rule
        if self.error:
            out["error"] = self.error
        return out


class PolicyEngine:
    def __init__(self, path: Path, tools: dict, local_name: str,
                 resolve_host: Callable[[str | None], tuple[Any, str | None]]) -> None:
        self.path = path
        self.tools = tools
        self.local_name = local_name
        self.resolve_host = resolve_host
        self._mtime: float | None = None
        self.cfg: dict = self._safe()
        self.error: str | None = None
        self.loaded_at: float = 0
        self.reload(force=True)

    # ------------------------------------------------------------ config

    @staticmethod
    def _safe() -> dict:
        return {"defaults": dict(SAFE_DEFAULTS), "rules": [], "protected_services": [],
                "approval_timeout_minutes": 15}

    def reload(self, force: bool = False) -> None:
        """Re-read policy.yaml when it changes. An invalid file falls back to the strict safe defaults."""
        try:
            mtime = os.path.getmtime(self.path)
        except OSError:
            mtime = None
        if not force and mtime == self._mtime:
            return
        self._mtime = mtime
        if mtime is None:
            self.cfg, self.error = self._safe(), f"{self.path.name} not found; using safe defaults"
            log.warning(self.error)
            return
        try:
            raw = yaml.safe_load(self.path.read_text(encoding="utf-8")) or {}
            self.cfg, self.error = self._validate(raw), None
        except Exception as e:  # noqa: BLE001 - any problem -> fail safe
            self.cfg, self.error = self._safe(), f"{self.path.name} is invalid ({e}); using safe defaults"
            log.warning(self.error)
        self.loaded_at = time.time()

    @staticmethod
    def _validate(raw: dict) -> dict:
        if not isinstance(raw, dict):
            raise ValueError("top level must be a mapping")
        cfg = PolicyEngine._safe()
        defaults = raw.get("defaults") or {}
        if not isinstance(defaults, dict):
            raise ValueError("'defaults' must be a mapping")
        for tier, dec in defaults.items():
            if tier not in SAFE_DEFAULTS:
                raise ValueError(f"defaults: unknown tier '{tier}' (R3 is always deny)")
            if str(dec).lower() not in DECISIONS:
                raise ValueError(f"defaults.{tier}: decision must be one of {DECISIONS}")
            cfg["defaults"][tier] = str(dec).lower()
        prot = raw.get("protected_services") or []
        if not isinstance(prot, list) or not all(isinstance(p, str) for p in prot):
            raise ValueError("'protected_services' must be a list of names")
        cfg["protected_services"] = [p.lower() for p in prot]
        rules = raw.get("rules") or []
        if not isinstance(rules, list):
            raise ValueError("'rules' must be a list")
        for i, r in enumerate(rules):
            if not isinstance(r, dict):
                raise ValueError(f"rules[{i}] must be a mapping")
            unknown = set(r) - {"name", "tool", "target", "service", "decision"}
            if unknown:
                raise ValueError(f"rules[{i}]: unknown keys {sorted(unknown)}")
            if str(r.get("decision", "")).lower() not in DECISIONS:
                raise ValueError(f"rules[{i}].decision must be one of {DECISIONS}")
            cfg["rules"].append({
                "name": str(r.get("name") or f"rule {i + 1}"),
                "tool": str(r.get("tool", "*")).lower(),
                "target": str(r.get("target", "*")).lower(),
                "service": str(r["service"]).lower() if r.get("service") is not None else None,
                "decision": str(r["decision"]).lower(),
            })
        ttl = raw.get("approval_timeout_minutes", 15)
        if not isinstance(ttl, (int, float)) or not 1 <= ttl <= 1440:
            raise ValueError("approval_timeout_minutes must be between 1 and 1440")
        cfg["approval_timeout_minutes"] = ttl
        return cfg

    @property
    def approval_ttl_s(self) -> float:
        return float(self.cfg["approval_timeout_minutes"]) * 60

    def summary(self) -> dict:
        self.reload()
        return {"file": str(self.path), "error": self.error, "loaded_at": self.loaded_at,
                "defaults": {**self.cfg["defaults"], "R3": "deny"}, "tiers": TIERS,
                "rules": self.cfg["rules"], "approval_timeout_minutes": self.cfg["approval_timeout_minutes"],
                "protected_services": {"builtin_windows": sorted(HARDLINE_WINDOWS),
                                       "builtin_linux": sorted(HARDLINE_LINUX),
                                       "extra": self.cfg["protected_services"]}}

    # ------------------------------------------------------------ evaluation

    def _protected(self, service: str) -> bool:
        s = service.lower().removesuffix(".service")
        return s in HARDLINE_WINDOWS or s in HARDLINE_LINUX or s in self.cfg["protected_services"]

    def check(self, name: str, raw_args: Any, scope: list[str] | None, target: str | None):
        """Returns (Verdict, tool | None, validated_args | None, host | None)."""
        self.reload()
        target = (target or "local").strip() or "local"
        tool0 = self.tools.get(name)
        if tool0 is not None and not getattr(tool0, "uses_target", True):
            target = "local"          # the tool decides where it runs (e.g. each application has its own machine)
        host, host_err = self.resolve_host(target)
        label = host.label if host else target
        v, t, a = self._check(name, raw_args, scope, target, host, host_err, label)
        return v, t, a, (host if v.decision != "DENY" else None)

    def _check(self, name, raw_args, scope, target, host, host_err, label):

        def deny(reason: str, risk: str = "R3", summary: str | None = None, reasons=None):
            return Verdict("DENY", risk, summary or f"{name} on {label}", reasons or [reason], label, error=reason,
                           blocked_by="request")

        tool = self.tools.get(name)
        if tool is None:
            return deny(f"'{name}' is not a registered tool."), None, None

        if scope is not None and not set(scope) & set(tool.toolsets):
            loaded = ", ".join(scope) or "none"
            return deny(f"'{name}' is outside the active scope ({loaded}).", tool.risk), tool, None

        if host is None:
            v = deny(str(host_err or f"Unknown target '{target}'."))
            v.blocked_by = getattr(host_err, "kind", "request")   # an unreachable machine is a final fact
            return v, tool, None

        if raw_args is None:
            raw_args = {}
        try:
            args = tool.Args.model_validate(raw_args)
        except ValidationError as e:
            issues = "; ".join(f"{'.'.join(map(str, err['loc'])) or 'args'}: {err['msg']}" for err in e.errors())
            return deny(f"Invalid arguments: {issues}", tool.risk), tool, None

        try:
            a: Assessment = tool.assess(args, host) if tool.assess else Assessment(tool.risk, f"{name} on {label}")
        except Exception as e:  # noqa: BLE001 - e.g. the remote machine is unreachable
            return Verdict("DENY", tool.risk, f"{name} on {label}", [str(e)], label, error=str(e),
                           blocked_by="state"), tool, args
        validated = args.model_dump()
        if a.error:
            return Verdict("DENY", a.risk, a.summary, a.reasons + [a.error], label, error=a.error,
                           args=validated, blocked_by=a.blocked_by), tool, args

        if a.stops_service and a.service and self._protected(a.service):
            msg = (f"'{a.service}' is a protected service; stopping or restarting it is blocked by the "
                   "hardline policy and cannot be overridden.")
            return Verdict("DENY", "R3", a.summary, a.reasons + [msg], label, error=msg, args=validated,
                           blocked_by="policy"), tool, args

        if a.risk == "R3":
            msg = "R3 (destructive) actions are always denied."
            return Verdict("DENY", "R3", a.summary, a.reasons + [msg], label, error=msg, args=validated,
                           blocked_by="policy"), tool, args

        names = {target.lower(), label.lower()} | set(getattr(host, "names", set()))
        for rule in self.cfg["rules"]:
            if not fnmatch.fnmatch(name.lower(), rule["tool"]):
                continue
            if not any(fnmatch.fnmatch(n, rule["target"]) for n in names):
                continue
            if rule["service"] is not None and not (a.service and fnmatch.fnmatch(a.service.lower(), rule["service"])):
                continue
            dec = rule["decision"].upper()
            return Verdict(dec, a.risk, a.summary, a.reasons + [f"policy rule: {rule['name']}"], label,
                           error=f"Refused by policy rule '{rule['name']}'." if dec == "DENY" else None,
                           rule=rule["name"], args=validated,
                           blocked_by="policy" if dec == "DENY" else None), tool, args

        dec = self.cfg["defaults"].get(a.risk, "confirm").upper()
        reasons = a.reasons + [f"default for {a.risk} ({TIERS[a.risk]}): {dec.lower()}"]
        return Verdict(dec, a.risk, a.summary, reasons, label,
                       error="Refused by the default policy." if dec == "DENY" else None,
                       args=validated, blocked_by="policy" if dec == "DENY" else None), tool, args
