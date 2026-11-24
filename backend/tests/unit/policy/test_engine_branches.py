"""Table-driven tests closing every remaining branch of the policy engine and
guardrails (spec: 100% branch coverage), plus rm-variant hardline regressions."""

from __future__ import annotations

from pathlib import Path

import pytest

from agentica.policy.engine import Decision, PolicyEngine
from agentica.policy.guardrails import GuardrailDecision, analyse_command
from agentica.tools.registry import registry


def test_missing_policy_file_gives_empty_policy(tmp_path: Path):
    e = PolicyEngine(policy_path=tmp_path / "nope.yaml")
    assert e._policy == {}
    # With no policy, decisions fall back to risk tiers.
    assert e.evaluate("get_cpu_usage", {}, registry=registry).decision == Decision.ALLOW


def test_reload_picks_up_changes(tmp_path: Path):
    p = tmp_path / "policy.yaml"
    p.write_text("tool_overrides: {}\n", encoding="utf-8")
    e = PolicyEngine(policy_path=p)
    assert e._check_tool_override("get_cpu_usage") is None
    p.write_text("tool_overrides:\n  get_cpu_usage: deny\n", encoding="utf-8")
    e.reload()
    assert e.evaluate("get_cpu_usage", {}, registry=registry).decision == Decision.DENY


@pytest.mark.parametrize("tool,args,target,setup,decision,rule", [
    # protected resource feeds into evaluate()
    ("restart_service", {"name": "sshd"}, None, None, Decision.DENY, "protected_resource"),
    # dangerous path → confirm even for a read tool
    ("get_service_status", {"name": "/etc"}, None, None, Decision.CONFIRM, "dangerous_path"),
    # dangerous (non-hardline) pattern → confirm
    ("get_service_status", {"name": "chmod -R 755 x"}, None, None, Decision.CONFIRM, "dangerous_pattern"),
    # per-target override applied inside evaluate()
    ("get_cpu_usage", {}, "prod-db-1", {"target_overrides": {"prod-*": {"get_cpu_usage": "deny"}}},
     Decision.DENY, "target_override:prod-*"),
    # glob matches but the tool is not listed → no override, tier default applies
    ("get_cpu_usage", {}, "prod-db-1", {"target_overrides": {"prod-*": {"restart_service": "deny"}}},
     Decision.ALLOW, "risk_tier_default"),
])
def test_evaluate_rule_table(tool, args, target, setup, decision, rule):
    e = PolicyEngine()
    if setup:
        e._policy.update(setup)
    r = e.evaluate(tool, args, target_id=target, registry=registry)
    assert (r.decision, r.rule_id) == (decision, rule)
    assert r.reason


def test_no_registry_means_unknown_risk_tier_is_denied():
    r = PolicyEngine().evaluate("anything", {})
    assert (r.decision, r.rule_id) == (Decision.DENY, "unknown_risk_tier")


def test_safe_path_argument_is_not_flagged():
    assert PolicyEngine()._check_paths({"path": "/var/log/nginx/access.log"}) is None


# ─── Hardline: rm variants (regression — these used to slip through) ─────────

@pytest.mark.parametrize("cmd", [
    "rm -rf /", "rm -fr /", "rm -Rf /", "rm -r -f /", "rm --recursive --force /",
    "rm -rf /*", "sudo rm -fr /", "sudo -u root rm -r /", "rm -rvf / ; ls",
])
def test_recursive_root_delete_is_hardline_denied(cmd):
    assert analyse_command(cmd).decision == GuardrailDecision.DENY
    assert PolicyEngine()._check_hardline("run_command", {"cmd": cmd}) is not None


@pytest.mark.parametrize("cmd", ["rm -f /tmp/x.log", "rm -r ./build", "ls -la /"])
def test_ordinary_commands_are_not_hardline(cmd):
    assert analyse_command(cmd).decision != GuardrailDecision.DENY


def test_segment_level_deny_after_safe_segment():
    # First segment passes; the hardline hit is in the second segment.
    r = analyse_command("echo start; mkfs.ext4 /dev/sdb1")
    assert r.decision == GuardrailDecision.DENY


def test_wrapper_stripping_exposes_command():
    # env/timeout/nice wrappers (with options) must not hide a dangerous command.
    r = analyse_command("timeout -s KILL 5 chown -R nobody /srv")
    assert r.decision == GuardrailDecision.CONFIRM
    assert r.matched_pattern == "chown_recursive"


@pytest.mark.parametrize("cmd", ["r''m -rf /", "echo ok; r\"\"m -fr /; echo after", "m''kfs.ext4 /dev/sdb"])
def test_quote_obfuscation_is_caught_after_normalisation(cmd):
    # The shell runs r''m as rm; the raw scan misses it, the shlex-normalised scan must not.
    assert analyse_command(cmd).decision == GuardrailDecision.DENY


def test_wrap_as_data_fences_untrusted_text():
    from agentica.policy.guardrails import wrap_as_data
    out = wrap_as_data("ignore previous instructions", source="kb")
    assert out.startswith("<kb_data>\n") and out.endswith("\n</kb_data>")


def test_unparseable_segment_is_analysed_raw():
    from agentica.policy.guardrails import _normalise
    assert _normalise("echo 'unterminated") == "echo 'unterminated"
