"""Guardrails v1 — command analysis and hardline blocking.

Decision order:
1. Parse error → at least Confirm (fail closed)
2. Split on shell operators, strip wrappers, analyse each segment
3. Match against hardline patterns → Deny (cannot override)
4. Match against dangerous patterns → Confirm
5. Otherwise → pass (let policy engine decide by risk tier)
"""

from __future__ import annotations

import re
import shlex
from dataclasses import dataclass
from enum import Enum
from typing import NamedTuple


class GuardrailDecision(str, Enum):
    PASS = "pass"
    CONFIRM = "confirm"
    DENY = "deny"


@dataclass
class GuardrailResult:
    decision: GuardrailDecision
    reason: str
    matched_pattern: str | None = None


# ─── Hardline patterns (always DENY) ─────────────────────────────────────────

_HARDLINE: list[tuple[str, re.Pattern]] = [
    ("rm_rf_root",        re.compile(r"\brm\b.*-[a-zA-Z]*r[a-zA-Z]*f\s+/\s*$")),
    ("rm_rf_root2",       re.compile(r"\brm\b.*-rf\s+/")),
    ("mkfs",              re.compile(r"\bmkfs\b")),
    ("dd_block_device",   re.compile(r"\bdd\b.*\bof=/dev/")),
    ("fork_bomb",         re.compile(r":\s*\(\)\s*\{.*?\}\s*;?\s*:", re.DOTALL)),
    ("chmod_r_777_root",  re.compile(r"\bchmod\b.*-[rR].*\b777\b.*/")),
    ("format_volume",     re.compile(r"\bFormat-Volume\b", re.IGNORECASE)),
    ("diskpart_clean",    re.compile(r"\bdiskpart\b.*\bclean\b", re.IGNORECASE)),
    ("vssadmin_delete",   re.compile(r"\bvssadmin\b.*\bdelete\b.*\bshadows\b", re.IGNORECASE)),
    ("encoded_powershell",re.compile(r"\bpowershell\b.*-[eE]nco", re.IGNORECASE)),
    ("pipe_to_shell",     re.compile(r"\|\s*(bash|sh|python3?|powershell)\b", re.IGNORECASE)),
    ("iex_download",      re.compile(r"\bIEX\b.*\bDownloadString\b", re.IGNORECASE)),
    ("rm_rf_star",        re.compile(r"\brm\b.*-[rRfF]+.*\*")),
    ("truncate_dev",      re.compile(r"\btruncate\b.*/dev/")),
    ("shred_dev",         re.compile(r"\bshred\b.*/dev/")),
]

# ─── Dangerous patterns (Confirm) ────────────────────────────────────────────

_DANGEROUS: list[tuple[str, re.Pattern]] = [
    ("sudo_shell",       re.compile(r"\bsudo\b.*(-s|--shell)\b")),
    ("su_root",          re.compile(r"\bsu\b\s*(-\s*root|-l\s*root|root\s*$)")),
    ("chmod_recursive",  re.compile(r"\bchmod\b.*-[rR]")),
    ("chown_recursive",  re.compile(r"\bchown\b.*-[rR]")),
    ("redirect_dev_null",re.compile(r">\s*/dev/null\s+2>&1\s+&")),
    ("iptables_flush",   re.compile(r"\biptables\b.*-F")),
    ("kill_all",         re.compile(r"\bkillall\b|\bkill\b.*-9.*-1")),
    ("net_user_add",     re.compile(r"\bnet\s+user\b.*\/add\b", re.IGNORECASE)),
    ("reg_delete",       re.compile(r"\breg\s+delete\b", re.IGNORECASE)),
    ("wmic_delete",      re.compile(r"\bwmic\b.*\bdelete\b", re.IGNORECASE)),
]

# ─── Wrapper commands to strip ───────────────────────────────────────────────

_WRAPPERS = {"sudo", "env", "timeout", "nice", "ionice", "nohup", "strace", "ltrace"}

# ─── Shell split operators ───────────────────────────────────────────────────

_SHELL_SPLIT = re.compile(r"[;&|]+|\$\(|\`")


def _strip_wrappers(tokens: list[str]) -> list[str]:
    while tokens and tokens[0] in _WRAPPERS:
        # Also strip option args like --user=x
        while len(tokens) > 1 and tokens[1].startswith("-"):
            tokens = tokens[1:]
        tokens = tokens[1:]
    return tokens


def _segments(command: str) -> list[str]:
    """Split on shell operators, expand $() and backtick groups."""
    raw = _SHELL_SPLIT.split(command)
    return [s.strip() for s in raw if s.strip()]


def _analyse_segment(seg: str) -> GuardrailResult:
    # Hardline check
    for name, pat in _HARDLINE:
        if pat.search(seg):
            return GuardrailResult(
                decision=GuardrailDecision.DENY,
                reason=f"Hardline blocked pattern '{name}'",
                matched_pattern=name,
            )
    # Dangerous check
    for name, pat in _DANGEROUS:
        if pat.search(seg):
            return GuardrailResult(
                decision=GuardrailDecision.CONFIRM,
                reason=f"Dangerous pattern '{name}' requires confirmation",
                matched_pattern=name,
            )
    return GuardrailResult(decision=GuardrailDecision.PASS, reason="No match")


def analyse_command(command: str) -> GuardrailResult:
    """Analyse a command string for safety. Fail closed on parse error."""
    if not command or not command.strip():
        return GuardrailResult(decision=GuardrailDecision.PASS, reason="Empty command")

    # Check full raw command against hardline patterns BEFORE splitting.
    # This catches fork bombs and pipe-based patterns that splitting would destroy.
    for name, pat in _HARDLINE:
        if pat.search(command):
            return GuardrailResult(
                decision=GuardrailDecision.DENY,
                reason=f"Hardline blocked pattern '{name}'",
                matched_pattern=name,
            )

    # Try to parse; parse error → Confirm (fail closed)
    try:
        shlex.split(command)
    except ValueError as e:
        return GuardrailResult(
            decision=GuardrailDecision.CONFIRM,
            reason=f"Parse error (fail closed): {e}",
        )

    # Normalise and check each segment
    segs = _segments(command)
    worst = GuardrailResult(decision=GuardrailDecision.PASS, reason="All clear")
    _order = {GuardrailDecision.PASS: 0, GuardrailDecision.CONFIRM: 1, GuardrailDecision.DENY: 2}

    for seg in segs:
        result = _analyse_segment(seg)
        if _order[result.decision] > _order[worst.decision]:
            worst = result
        if worst.decision == GuardrailDecision.DENY:
            break

    return worst


def check_prompt_injection(text: str) -> bool:
    """Return True if text looks like a prompt injection attempt."""
    injection_patterns = [
        re.compile(r"ignore\s+(previous|all|above)\s+instructions", re.IGNORECASE),
        re.compile(r"you\s+are\s+now\s+(a|an)\s+", re.IGNORECASE),
        re.compile(r"act\s+as\s+if\s+you\s+(have\s+no|are\s+a)", re.IGNORECASE),
        re.compile(r"system\s*:\s*(you|ignore)", re.IGNORECASE),
        re.compile(r"<\s*system\s*>", re.IGNORECASE),
        re.compile(r"\[INST\].*ignore", re.IGNORECASE),
    ]
    for pat in injection_patterns:
        if pat.search(text):
            return True
    return False


def wrap_as_data(text: str, source: str = "tool_output") -> str:
    """Wrap external text as data to prevent prompt injection."""
    return f"<{source}_data>\n{text}\n</{source}_data>"
