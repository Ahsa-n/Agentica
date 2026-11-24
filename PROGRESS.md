# Agentica Build Progress

Last verified: **2026-11-24** (local Windows 11 laptop, CPU-only, Ollama `qwen2.5:3b-instruct`, PostgreSQL 16 + pgvector in Docker).

## Proposal scope due at the Final FYP-1 evaluation (Table 5 / Fig. 3)

| # | Feature (proposal §7.1) | Status | How it was verified |
|---|---|---|---|
| F1 | Natural-language chat interface | ✅ Working | Browser test (headless Edge): "hi" → reply; streaming answer rendered |
| F2 | GUI task cards (bias routing) | ✅ Working | Browser test: card opens a session with its examples + forced categories; FYP-II cards removed |
| F3 | Live tool calls (tool, target, args, decision, result) | ✅ Working | Browser + API tests: ToolCallCard shows tool, `local`/`on <machine>`, policy badge, duration, result |
| F4 | Multi-turn session history | ✅ Working | 2nd turn in the same session calls live tools; history restored from checkpoint after reload |
| F5 | RAG knowledge retrieval (hybrid) | ✅ Working | 50 gold-labelled questions: hybrid MRR 1.000, nDCG@5 0.968 (see below) |
| F6 | Knowledge-base management | ✅ Working | Index folder, re-index, remove, test search in UI; watcher picks up new/changed/deleted files; folder resumes + rescans after restart |
| F7 | Local system monitoring | ✅ Working | CPU/memory/disk/network/processes via chat, grounded in same-turn tool results |
| F9 | Service monitoring and control | ✅ Working | status/list/start/stop/restart; Confirm → Approve/Deny; `verify()` polls ≤30 s |
| F10 | Application status monitoring | ✅ Working | `apps.yaml` now defines Agentica API, PostgreSQL, Ollama, nginx; process/service/port/HTTP checks |
| F11 | Remote Linux management (SSH) | ✅ Working | Live against `agentica-linux-target` container: all 15 tool paths, approved remote nginx restart (PID changed, verified) |
| F12 | Remote Windows management (WinRM) | ✅ Working (live) | This PC set up as a WinRM-HTTPS target (`win-local`): certificate pinned by thumbprint, all 15 tool paths over real WinRM, approved Spooler stop/start/restart verified by Windows itself, same flow driven from the browser |
| F14 | Local/offline private model mode | ✅ Working | Ollama local; HF/transformers offline; egress guard enforced at startup; model loads from local snapshot |
| F18 | Guardrails (established layer) | ✅ Working | Hardline/dangerous detection (100% branch coverage), strict Pydantic schema validation, prompt-injection fencing of tool/KB text, grounding system prompt |
| F19 | Policy & permission engine | ✅ Working | Deterministic, risk tiers, per-target/per-tool overrides, protected resources; 100% branch coverage |

Scheduled later by the proposal (not FYP-1): F8 file operations, F13 guided troubleshooting, F15 model switching, F16 dashboard, F17 web interface, evaluation benchmark (Mar–Apr 2027).

## Build-plan phases (docs/FYP1_BUILD_PROMPT.md)

| Phase | Status | Notes |
|-------|--------|-------|
| 0: Environment | complete | Code at D:\Temp\Agentica, venv D:\Temp\venv. Only Ollama model: `qwen2.5:3b-instruct` in `C:\Users\Pc world\.ollama\models` (the Ollama app's model location) |
| 1: Scaffold | complete | FastAPI + Pydantic settings + keyring secrets; bearer token per launch |
| 2: Data layer | complete | Alembic schema; pgvector HNSW + FTS GIN; LangGraph checkpointer tables |
| 3: Orchestration | complete | 9-node graph; real schema validation; per-turn state reset; step limit; approval routing fixed |
| 4: Chat/tools/history | complete | SSE de-duplicated; history endpoint; session titles; approval returns tool result |
| 5: Monitoring (self) | complete | 7 psutil tools; top-processes CPU sampling fixed |
| 6: RAG/KB | complete | Embedding loader fixed; watcher handles delete/move; folder persisted and resumed |
| 7: Guardrails v1 | complete | rm flag-order bypass fixed; wrapper stripping applied; quote obfuscation caught |
| 8: Task cards / services | complete | Remote-aware services; verify() reports `verified` to the model and UI |
| 9: Remote (SSH/WinRM) | complete (Linux live, Windows fixtures) | Same tool names take `target`; Machines page add/credentials/fetch-fingerprint/trust/test/remove |
| 10: Local model mode | complete | Egress guard installed at startup (was defined but unused) |
| 11: Integration/testing | complete for FYP-1 scope | See test results; open items below |

## Fixed in the 2026-11-23 verification pass

Bugs found by testing the running app (each reproduced first, then fixed and re-tested):

1. **KB search broken** — `embed.py` picked a partial HF snapshot with no weights → every KB search returned HTTP 500 and the agent invented SOP answers. Now only snapshots with weights are used.
2. **Multi-turn chat broken** — `final_answer`/step counters persisted between turns, so turn 2 replayed turn 1's answer and never ran tools. Per-turn state is now reset.
3. **Every 2nd tool call in a turn failed** — `node_validate` raised on every call (`BaseTool has no __args__`), counted as a "retry". Replaced with real Pydantic validation (`extra="forbid"`).
4. **No grounding prompt** — the model reported a memory figure it never fetched. Added a system prompt enforcing same-turn tool grounding and data-fencing.
5. **Prompt-injection wrapping unused** — tool/KB output is now wrapped with `wrap_as_data` before reaching the model.
6. **Denial ran both branches** — static `approval → execute` edge plus `Command(goto="report")`. Edge removed.
7. **Policy deny left no tool result** — the model could retry a denied action until the step limit. Denials now return an error result.
8. **SSE retry loop** — `fetchEventSource.onerror` never threw, so a failed stream silently re-POSTed the message. Fixed; server error text is shown.
9. **History not loaded** when opening an old session; all sessions titled "New Session". Fixed.
10. **SSH command injection risk** — `SSHTarget` joined argv with spaces into a remote shell command. Now `shlex.join` (argv semantics).
11. **Remote execution not wired** — `ToolCall.target_id` was never set; tools ignored `target`. Implemented Linux (SSH) and Windows (WinRM) collectors.
12. **WinRM certificate not pinned** — thumbprint was stored but never checked. Now pinned via urllib3 `assert_fingerprint`; scripts sent with `-EncodedCommand`.
13. **SSH keys** — only RSA keys loaded (setup script creates ed25519). Now ed25519/ECDSA/RSA; SHA256 or MD5 fingerprints accepted.
14. **KB watcher** — ignored deletions; on Windows, short (8.3) vs long paths meant deleted files stayed searchable; folder not persisted. Fixed.
15. **Guardrail bypass** — `rm -fr /`, `rm -Rf /`, `rm -r -f /` were not hardline-denied. Fixed in guardrails and policy.yaml.
16. **Approval prompt** — showed no target/risk tier; destructive actions now need an explicit acknowledgement before Approve.
17. **Launcher** — `start.bat` created a stray empty `agentica-db` container and pointed at a non-existent Ollama path; now uses the compose `agentica-postgres`, Docker Desktop at D:\Docker, and the installed Ollama.
18. **Kill-and-resume test** — never ran (wrong API use, LLM-dependent, asserted `≤1`). Rewritten with a fake LLM; asserts exactly one execution after restart and none after a denial.
19. **Local commands failed on Windows** — `LocalTarget` used `asyncio.create_subprocess_exec`, which the Windows SelectorEventLoop (required by psycopg3) cannot run → local service status/list/start/stop/restart and event logs all raised `NotImplementedError`. Now `subprocess.run` in a worker thread (argv, no shell).
20. **pywin32 missing** — the spec says Windows services use pywin32, but it was not a dependency. Added (`sys_platform == 'win32'`) and installed.
24. **`windows-target-setup.ps1` was unsafe and broken** — it created a plain-HTTP listener path plus a firewall rule for *all* profiles (incl. Public Wi-Fi), never removed HTTP, used `Set-Item` on WinRM service settings (refused on Public networks) and a 64-char account description (Windows limit 48). Rewritten: HTTPS only, HTTP listeners removed, Basic/unencrypted off and verified, firewall Domain/Private only (none with `-LocalOnly`), optional dedicated account, `-Uninstall`. Found by actually running it.
25. **WinRM scripts** now get `$ProgressPreference='SilentlyContinue'` and UTF-8 output (no CLIXML noise, correct non-ASCII names); Windows perf-counter process names (`python#2`) shown without the suffix.
23. **Double-send race** — on the first message of a new chat, Send stayed clickable while the session was being created; a double-click could create two sessions and send twice. Send now locks immediately.
22. **Model picked a remote machine unasked** — with a machine registered, "Restart the service named demo-test-svc" was sent to `linux-test`. A target is now honoured only if the user named that machine in the session; otherwise the call runs locally.
21. **SOP questions answered from live tools** — "According to the SOPs, how should I handle a full disk?" called disk/process tools for 400 s. `search_knowledge_base` is now always offered and the prompt routes procedure questions to it first.

## Test results (2026-11-23)

- **Unit tests:** 208 passed (`pytest tests/unit`)
- **Integration:** 2 passed (`CI_INTEGRATION=1 pytest tests/integration`) — kill-and-resume executes exactly once; deny after restart never executes
- **Coverage:** `agentica/policy/engine.py` 100% branch, `agentica/policy/guardrails.py` 100% branch
- **Retrieval eval** (`eval/retrieval_eval.py`, 50 gold-labelled questions, 5 SOPs, 37 chunks):

  | Mode | Recall@5 | MRR | nDCG@5 |
  |---|---|---|---|
  | Hybrid (dense + FTS + RRF) | 1.000 | **1.000** | **0.968** |
  | Dense only | 1.000 | 0.987 | 0.962 |

  With only 5 documents Recall@5 is near-trivial; MRR/nDCG are the informative numbers. The old 20-question eval counted any keyword match as a hit and has been replaced.
- **API end-to-end** (through the Vite proxy): 23/23 — health, auth, sessions, KB list/search/re-index/folder, machines, chat (greeting, multi-turn tools, SOP question answered from the KB with citation), history, titles, protected-service deny, approval deny + approve-and-execute.
- **Browser end-to-end** (Playwright + Edge, headless): Dashboard, task cards, Knowledge Base (list/search/re-index/bad folder), Machines (fetch fingerprint/test/add/remove), Chat (reply, live tool card, history after reload, approval → Deny), no horizontal scroll at 390 px on every page, zero console errors.
- **KB watcher end-to-end:** new file indexed and searchable, modified file re-indexed with old text gone, deleted file removed; after a restart the saved folder is watched again and files added/deleted while the backend was down are indexed/removed by the startup rescan.
- **Remote Windows (WinRM HTTPS, 2026-11-24):** certificate fingerprint fetched from the server equals the one the setup script printed before it was trusted; all 15 tool paths over real WinRM (overview, CPU, memory, disk, network, processes, services, app status, ports, event log, wrong-OS log source refused cleanly, PowerShell quote-injection treated as a literal name). Service control with Print Spooler, each action approved and then confirmed by an independent `Get-Service`: local (elevated backend) stop/start/restart and remote `win-local` stop/start/restart = **25/25 checks**, restarts created new processes, Spooler left Running. Same restart driven from the browser: approval card shows target `win-local`, "Approved by you", `verified: true`.
- **Full regression after the Windows work:** API 23/23, browser pages 13/13 (incl. Windows machine fetch + test), browser chat/approval/Windows-service 5/5, Linux remote 13/13.
- **Launcher:** from a cold state (Docker Desktop stopped) `start.bat` started Docker, PostgreSQL, Ollama, backend and UI in ~60 s.
- **Local Windows tools** (backend event loop): service status (Spooler active, unknown service reported), service list, event log, application status all work; restarting a service without Administrator rights fails cleanly with "Access is denied."
- **Remote Linux end-to-end** (dev container, `127.0.0.1:2222`): add machine, credentials in keyring (never returned), fetched fingerprint equals the server's ED25519 key, wrong fingerprint refused, test connection, chat on `linux-test` (CPU+memory, nginx status), approved remote restart (nginx PID 3978 → 4452, `verified: true`).

## Decisions
- Build location: D:\Temp\Agentica (C drive was full).
- LLM: **qwen2.5:3b-instruct is the only model installed and used** (decision 2026-11-24). The laptop has no usable GPU (Intel UHD 620, i7-8650U, 15.8 GB RAM); the 7B ran on CPU at ~6 tok/s, re-read its ~2,000-token prompt at ~14 tok/s, and left 0.4 GB RAM free, so replies took 2–7 minutes and often looked like "chat not replying". Measured 3B: model load 3.7 s (7B: 172 s), prompt 28 tok/s cold / 236 tok/s cached, generation ~10 tok/s, 6.7 GB RAM freed. The 7B was deleted from both `C:\Users\Pc world\.ollama\models` and the unused copy in `D:\Temp\ollama-models`; the stale `OLLAMA_MODELS` user variable was removed.
- Speed settings (`settings.yaml` → `llm`): `keep_alive: 30m` (no reload between chats), `stable_tool_prompt: true` (identical tool list on every call so Ollama reuses its cached prompt; routing becomes a hint on the user turn), `num_predict: 512` + `repeat_penalty: 1.1` (a 3B reply once looped for 10+ minutes without a cap). Typical replies on this laptop: 10–30 s for knowledge/approval turns, ~70 s for turns with a live tool call; the first message after a restart takes ~1–2 min while the model warms up.
- Chat shows a live elapsed-time counter while the agent works.
- Targets: a machine is used only if the user named it in the session; if the user names exactly one registered machine and the model omits `target`, that machine is used (small-model slip).
- Remote execution: the same tool names accept an optional `target` (enum of registered machines, injected into the tool schema only when machines exist). `target_id` goes through policy (per-target overrides) before execution.
- Linux collectors read `/proc`, `df -kPT`, `ps`, `systemctl` (SysV `service` fallback when there is no systemd, as in the dev container). Control actions use `sudo -n` unless the user is root.
- Windows collectors use `Get-CimInstance`/`Get-Service`/`Get-WinEvent` with `ConvertTo-Json`; every model-supplied value goes through `ps_quote`.
- WinRM trust = SHA-1 certificate thumbprint pinned per target (self-signed certs cannot pass CA validation).
- Guardrails pattern set: our own (Hermes licence not verified).
- Approval scope: approve-once.

## Open items / blockers
- **Administrator rights:** local Windows service start/stop/restart needs an elevated backend. `start.bat` now asks for UAC (click Yes); declining still starts Agentica, without service control. `stop.bat` also asks for UAC (the elevated backend can only be stopped elevated) — this one was changed but not exercised, to avoid cutting the running servers.
- **This PC is now a WinRM target (local-only):** WinRM service Automatic; HTTPS listener bound to 127.0.0.1:5986 (a connection through the Wi-Fi address is reset before any certificate is presented, no firewall port opened); self-signed cert "Agentica WinRM"; local admin account `agentica` (random 32-char password, only in the OS keyring); `LocalAccountTokenFilterPolicy=1`. Undo everything with `infra\setup-this-pc-as-windows-target.bat /uninstall` (UAC).
- **Real remote Windows servers:** run `infra\windows-target-setup.ps1 -CreateUser agentica` (without `-LocalOnly`) as Administrator on the server; it opens 5986 for Domain/Private profiles only. Prefer a domain account where one exists.
- `expand_scope` tool (Phase 3.6) not implemented; routed mode force-includes monitoring/services/apps when "remote" is routed.
- Context summarisation for long sessions (Phase 4.4): only the last 20 messages are sent.
- Model comparison (Phase 10.3) and the 31 `eval/tasks` run in routed vs flat mode have not been executed/recorded.
- **CI (GitHub Actions, Ubuntu + Windows):** the first run, on PR #79 of the team repo, failed at the `ruff check` step: 99 style findings (import order, unused imports, old-style annotations) in code that had never been linted. Fixed (93 automatically, 3 by hand, the enum/Generic modernisation rules deliberately ignored in `pyproject.toml` because `StrEnum` would change how enum members serialise). The second CI round then failed on environment problems: `pyproject.toml` declared `sqlalchemy` without `[asyncio]` (so `greenlet` was missing on a clean machine) and the Windows workflow installed a hand-picked package list that omitted `sqlalchemy`, `langgraph-checkpoint-postgres` and others. Both fixed (`sqlalchemy[asyncio]`; the Windows job now uses the same `pip install -e ".[dev]"` as Ubuntu). Verified in a brand-new venv built only from `pyproject.toml`: lint, 208 unit tests and the 90% policy-coverage gate pass.
- Dev Linux target uses `root / test1234` (compose file, dev only) — never use for real servers; use `infra/linux-target-setup.sh` (key-based `agentica` user, scoped sudoers).

## Left for FYP-II (per proposal)
File operations, guided troubleshooting, flexible model selection, built-in monitoring dashboard, web/mobile interface, evaluation benchmark & metrics, desktop packaging.
