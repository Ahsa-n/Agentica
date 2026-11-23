"""Deterministic policy engine — pure Python, no LLM.

Decision order (most restrictive wins when multiple rules apply):
 1. unknown tool
 2. schema invalid
 3. hardline blocklist  → always Deny, cannot be overridden
 4. protected resources
 5. path rules
 6. dangerous patterns
 7. per-target override (most specific glob)
 8. per-tool override
 9. risk-tier default
"""

from __future__ import annotations

import fnmatch
import re
from enum import Enum
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel

from agentica.config.logging import get_logger
from agentica.tools.base import RiskTier, ToolRegistry

logger = get_logger(__name__)

_POLICY_PATH = Path(__file__).parent.parent.parent.parent / "config" / "defaults" / "policy.yaml"


class Decision(str, Enum):
    ALLOW = "allow"
    CONFIRM = "confirm"
    DENY = "deny"


_TIER_DEFAULTS: dict[RiskTier, Decision] = {
    RiskTier.READ: Decision.ALLOW,
    RiskTier.MODIFY: Decision.CONFIRM,
    RiskTier.DESTRUCTIVE: Decision.CONFIRM,
}

_SEVERITY_ORDER = {Decision.ALLOW: 0, Decision.CONFIRM: 1, Decision.DENY: 2}


class PolicyResult(BaseModel):
    decision: Decision
    rule_id: str
    reason: str
    risk_tier: RiskTier | None = None


def _most_restrictive(a: PolicyResult, b: PolicyResult) -> PolicyResult:
    if _SEVERITY_ORDER[a.decision] >= _SEVERITY_ORDER[b.decision]:
        return a
    return b


class PolicyEngine:
    """Load policy.yaml and evaluate tool calls deterministically."""

    def __init__(self, policy_path: Path = _POLICY_PATH) -> None:
        self._path = policy_path
        self._policy: dict = {}
        self._compiled_hardline: list[re.Pattern] = []
        self._load()

    def _load(self) -> None:
        if self._path.exists():
            self._policy = yaml.safe_load(self._path.read_text(encoding="utf-8")) or {}
        else:
            self._policy = {}
        self._compiled_hardline = [
            re.compile(p)
            for p in (self._policy.get("hardline_blocklist") or {}).get("patterns", [])
        ]

    def reload(self) -> None:
        self._load()

    # ------------------------------------------------------------------
    def evaluate(
        self,
        tool_name: str,
        args: dict[str, Any],
        target_id: str | None = None,
        registry: ToolRegistry | None = None,
    ) -> PolicyResult:
        """Return the policy decision for a proposed tool call."""
        results: list[PolicyResult] = []

        # 1. Hardline blocklist — ALWAYS DENY, evaluated FIRST, no override possible
        hardline = self._check_hardline(tool_name, args)
        if hardline:
            return hardline  # short-circuit, never override

        # 2. Unknown tool
        if registry and tool_name not in registry:
            return PolicyResult(
                decision=Decision.DENY,
                rule_id="unknown_tool",
                reason=f"Tool '{tool_name}' is not registered.",
            )

        # 3. Schema validation — get tool object
        tool_obj = registry.get(tool_name) if registry else None

        # 4. Protected resources
        prot = self._check_protected(tool_name, args)
        if prot:
            results.append(prot)

        # 5. Path rules
        path_res = self._check_paths(args)
        if path_res:
            results.append(path_res)

        # 6. Dangerous patterns (non-hardline)
        danger = self._check_dangerous_patterns(args)
        if danger:
            results.append(danger)

        # 7. Per-target override
        target_res = self._check_target_override(tool_name, target_id)
        if target_res:
            results.append(target_res)

        # 8. Per-tool override
        tool_res = self._check_tool_override(tool_name)
        if tool_res:
            results.append(tool_res)

        # 9. Risk-tier default
        tier = tool_obj.spec.risk_tier if tool_obj else None
        if tier is not None:
            results.append(
                PolicyResult(
                    decision=_TIER_DEFAULTS.get(tier, Decision.DENY),
                    rule_id="risk_tier_default",
                    reason=f"Default for risk tier '{tier.value}'.",
                    risk_tier=tier,
                )
            )
        else:
            results.append(
                PolicyResult(
                    decision=Decision.DENY,
                    rule_id="unknown_risk_tier",
                    reason="Tool has no risk tier; denying by default.",
                )
            )

        # Aggregate: most restrictive wins
        final = results[0]
        for r in results[1:]:
            final = _most_restrictive(final, r)

        logger.debug(
            "policy_decision",
            tool=tool_name,
            decision=final.decision,
            rule=final.rule_id,
        )
        return final

    # ------------------------------------------------------------------
    def _check_hardline(self, tool_name: str, args: dict) -> PolicyResult | None:
        combined = tool_name + " " + " ".join(str(v) for v in args.values())
        for pat in self._compiled_hardline:
            if pat.search(combined):
                return PolicyResult(
                    decision=Decision.DENY,
                    rule_id="hardline_blocklist",
                    reason=f"Hardline blocked pattern matched: {pat.pattern}",
                )
        return None

    def _check_protected(self, tool_name: str, args: dict) -> PolicyResult | None:
        protected = (self._policy.get("protected_resources") or {}).get("services", [])
        combined = " ".join(str(v) for v in args.values()).lower()
        for svc in protected:
            if svc.lower() in combined:
                return PolicyResult(
                    decision=Decision.DENY,
                    rule_id="protected_resource",
                    reason=f"Protected resource '{svc}' referenced in args.",
                )
        return None

    def _check_paths(self, args: dict) -> PolicyResult | None:
        dangerous_paths = ["/", "/etc", "/boot", "/sys", "C:\\Windows", "C:\\System32"]
        combined = " ".join(str(v) for v in args.values())
        for dp in dangerous_paths:
            if dp in combined and len(combined.strip()) <= len(dp) + 5:
                return PolicyResult(
                    decision=Decision.CONFIRM,
                    rule_id="dangerous_path",
                    reason=f"Dangerous path '{dp}' in arguments.",
                )
        return None

    def _check_dangerous_patterns(self, args: dict) -> PolicyResult | None:
        # Non-hardline dangerous patterns that warrant Confirm
        warn_patterns = [
            re.compile(r"sudo\s+-s"),
            re.compile(r"chmod\s+-[rR]"),
            re.compile(r">\s*/dev/"),
        ]
        combined = " ".join(str(v) for v in args.values())
        for pat in warn_patterns:
            if pat.search(combined):
                return PolicyResult(
                    decision=Decision.CONFIRM,
                    rule_id="dangerous_pattern",
                    reason=f"Dangerous pattern matched: {pat.pattern}",
                )
        return None

    def _check_target_override(self, tool_name: str, target_id: str | None) -> PolicyResult | None:
        if not target_id:
            return None
        overrides: dict = self._policy.get("target_overrides") or {}
        for glob_pattern, tool_map in overrides.items():
            if fnmatch.fnmatch(target_id, glob_pattern):
                if tool_name in tool_map:
                    dec = Decision(tool_map[tool_name])
                    return PolicyResult(
                        decision=dec,
                        rule_id=f"target_override:{glob_pattern}",
                        reason=f"Target override for '{glob_pattern}' → {dec.value}",
                    )
        return None

    def _check_tool_override(self, tool_name: str) -> PolicyResult | None:
        overrides: dict = self._policy.get("tool_overrides") or {}
        if tool_name in overrides:
            dec = Decision(overrides[tool_name])
            return PolicyResult(
                decision=dec,
                rule_id=f"tool_override:{tool_name}",
                reason=f"Explicit tool override → {dec.value}",
            )
        return None
