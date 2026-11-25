"""
Actions — the single path from "a tool call was requested" to "it ran (or didn't)".

Used by both the HTTP API (server.py) and the agent graph (agent.py), so the policy
check, approval binding, execution, verification and audit logic exist exactly once.
"""
from __future__ import annotations

import asyncio
import time

import services
from hosts import RemoteError
from policy import Verdict

EXEC_TIMEOUT_S = 90

DECLINED_MSG = "The operator declined this action."


def outcome_of(result, error) -> str:
    if error:
        return "error"
    if isinstance(result, dict) and result.get("verified") is False:
        return "unverified"
    return "ok"


class Actions:
    def __init__(self, store, policy) -> None:
        self.store = store
        self.policy = policy

    # ------------------------------------------------------------------ helpers

    async def execute(self, tool, args, host) -> tuple[dict | None, str | None, int]:
        t0 = time.perf_counter()
        try:
            result = await asyncio.wait_for(asyncio.to_thread(tool.run, args, host), EXEC_TIMEOUT_S)
            if isinstance(result, dict):
                result = {"machine": host.label, **result}   # the model always sees where it ran
            return result, None, round((time.perf_counter() - t0) * 1000)
        except (services.ServiceError, RemoteError) as e:
            return None, str(e), round((time.perf_counter() - t0) * 1000)
        except asyncio.TimeoutError:
            return None, f"Timed out after {EXEC_TIMEOUT_S}s.", EXEC_TIMEOUT_S * 1000
        except Exception as e:  # noqa: BLE001
            return None, f"{type(e).__name__}: {e}", round((time.perf_counter() - t0) * 1000)

    def _audit(self, session, name, v: Verdict, raw_args, outcome, detail=None, decision=None) -> int:
        return self.store.audit(session=session, tool=name, target=v.target,
                                args=v.args if v.args is not None else raw_args, risk=v.risk,
                                decision=decision or v.decision, reasons=v.reasons, outcome=outcome, detail=detail)

    # ------------------------------------------------------------------ request a tool call

    async def request(self, name: str, raw_args, scope, target, session) -> tuple[dict, int]:
        """Policy-check one tool call. ALLOW -> runs it; CONFIRM -> creates a bound approval; DENY -> refuses.
        `target` inside raw_args (chosen by the model) wins over the session target. Returns (payload, http status)."""
        if isinstance(raw_args, dict) and "target" in raw_args:
            raw_args = dict(raw_args)
            target = str(raw_args.pop("target") or "") or target
        verdict, tool, args, host = await asyncio.to_thread(self.policy.check, name, raw_args, scope, target)
        pub = verdict.public()

        if verdict.decision == "DENY":
            self._audit(session, name, verdict, raw_args, "refused", verdict.error)
            return pub, 403

        if verdict.decision == "CONFIRM":
            appr = self.store.create_approval(session=session, tool=name, target=verdict.target, args=verdict.args,
                                              risk=verdict.risk, reasons=verdict.reasons, summary=verdict.summary,
                                              ttl_s=self.policy.approval_ttl_s)
            self._audit(session, name, verdict, raw_args, "pending", f"approval {appr['id']}")
            return {**pub, "approval_id": appr["id"], "expires": appr["expires"]}, 202

        row = self._audit(session, name, verdict, raw_args, "running")
        result, error, ms = await self.execute(tool, args, host)
        self.store.audit_outcome(row, outcome_of(result, error), error)
        out = {**pub, "elapsed_ms": ms}
        if error:
            out["error"] = error
        else:
            out["result"] = result
        return out, (200 if not error else 500)

    # ------------------------------------------------------------------ decide an approval

    async def decide(self, aid: str, action: str) -> tuple[dict, int]:
        """action: approve | deny. Approval re-checks policy + live state, then executes the STORED arguments."""
        rec = self.store.get_approval(aid)
        if not rec:
            return {"error": "No such approval"}, 404
        base = {"approval_id": aid, "risk": rec["risk"], "summary": rec["summary"], "target": rec["target"]}

        if rec["status"] != "pending":
            out = {**base, "status": rec["status"], "decision": "ALLOW" if rec["status"] == "executed" else "DENY"}
            if rec["status"] == "executed":
                out["result"] = (rec["result"] or {}).get("result")
            else:
                out["error"] = {"expired": "The approval request expired.", "denied": DECLINED_MSG,
                                "failed": (rec["result"] or {}).get("error", "The action failed."),
                                "approved": "This approval is already being executed."}.get(rec["status"], rec["status"])
            return out, 409

        if action == "deny":
            if not self.store.transition(aid, "pending", "denied"):
                return {**base, "error": "Approval already decided"}, 409
            self.store.audit(session=rec["session"], tool=rec["tool"], target=rec["target"], args=rec["args"],
                             risk=rec["risk"], decision="DECLINED", reasons=rec["reasons"], outcome="declined",
                             detail=f"approval {aid}")
            return {**base, "status": "denied", "decision": "DENY", "error": DECLINED_MSG}, 200

        verdict, tool, args, host = await asyncio.to_thread(self.policy.check, rec["tool"], rec["args"], None, rec["target"])
        if verdict.decision == "DENY":
            self.store.transition(aid, "pending", "denied", {"error": verdict.error})
            self.store.audit(session=rec["session"], tool=rec["tool"], target=rec["target"], args=rec["args"],
                             risk=verdict.risk, decision="DENY", reasons=verdict.reasons, outcome="refused",
                             detail=f"approval {aid} re-check: {verdict.error}")
            return {**base, "status": "denied", "decision": "DENY", "error": f"Refused on re-check: {verdict.error}"}, 403
        if not self.store.transition(aid, "pending", "approved"):
            return {**base, "error": "Approval already decided"}, 409
        row = self.store.audit(session=rec["session"], tool=rec["tool"], target=rec["target"], args=rec["args"],
                               risk=verdict.risk, decision="APPROVED", reasons=verdict.reasons, outcome="running",
                               detail=f"approval {aid}")
        result, error, ms = await self.execute(tool, args, host)
        self.store.transition(aid, "approved", "failed" if error else "executed", {"result": result, "error": error})
        self.store.audit_outcome(row, outcome_of(result, error), error)
        out = {**base, "status": "failed" if error else "executed", "decision": "ALLOW", "approved": True,
               "risk": verdict.risk, "elapsed_ms": ms}
        if error:
            out["error"] = error
        else:
            out["result"] = result
        return out, 200

    # ------------------------------------------------------------------ approval outcome for the agent / UI

    def from_record(self, rec: dict) -> tuple[dict, str]:
        """Approval record -> (tool result for the model, approval state for the UI)."""
        res = rec.get("result") or {}
        st = rec["status"]
        if st == "executed":
            return {"decision": "ALLOW", "result": res.get("result"), "risk": rec["risk"], "target": rec["target"]}, "approved"
        if st == "failed":
            return {"decision": "ALLOW", "error": res.get("error") or "The action failed.", "risk": rec["risk"],
                    "target": rec["target"]}, "failed"
        if st == "expired":
            return {"decision": "DENY", "error": "The approval request expired before the operator answered."}, "expired"
        if st == "approved":
            return {"decision": "DENY", "error": "The action was approved but its outcome is unknown (interrupted)."}, "failed"
        if res.get("error"):
            return {"decision": "DENY", "error": f"Refused: {res['error']}", "blocked_by": "policy"}, "refused"
        return {"decision": "DENY", "error": DECLINED_MSG}, "declined"

    async def settle(self, aid: str, action: str) -> tuple[dict, str]:
        """approve | deny | expire | cancel -> (final tool result, approval state)."""
        if action == "expire":
            rec = self.store.get_approval(aid)
            return self.from_record(rec) if rec else ({"decision": "DENY", "error": "The approval request expired."}, "expired")
        res, code = await self.decide(aid, "deny" if action == "cancel" else action)
        if code == 409 or code == 404:
            rec = self.store.get_approval(aid)
            return self.from_record(rec) if rec else (res, "declined")
        if action in ("deny", "cancel"):
            return res, "declined"
        if res.get("status") == "denied":
            return {**res, "blocked_by": "policy"}, "refused"
        return res, ("failed" if res.get("status") == "failed" else "approved")
