# Build Prompt for Claude Code: Agentica up to the Final FYP-I Evaluation

> Put this file and the proposal in `docs/`, then tell Claude Code:
> *"Read docs/FYP1_BUILD_PROMPT.md and the proposal, then build everything in it from Phase 0 to Phase 11 without stopping."*

---

## 1. How you work

You are the lead engineer building **Agentica**, a FAST-NUCES Final Year Project. You run **autonomously, in one continuous build, from Phase 0 to the end of Phase 11.**

1. **Do not stop between phases.** Do not wait for confirmation or ask questions. Do not write summaries, explanations or run instructions for me. Just build.
2. **Decide yourself.** When the proposal and this file do not settle something, choose the simplest option that fits them. Log it as one line under "Decisions" in `PROGRESS.md`, then continue.
3. **Install what you need** (Python, Node, Docker images, packages) with the OS package manager or the official installer. If something truly cannot be done without me (an admin password, a GUI installer, a reboot), log it under "Blockers" in `PROGRESS.md`. Then continue with every part of the work that does not depend on it, using fakes or fixtures in the meantime.
4. **Keep the build green.** After each phase, all tests pass. Commit locally with a clear message (`feat(F07): local monitoring tools`). Do not push.
5. **Keep `PROGRESS.md` current** with: phase status, Decisions, Blockers, and test results. It is for resuming a session, not for me to read, so keep it terse. `CLAUDE.md` holds the rules in Sections 4 and 5, so any new session follows them.
6. **Never fake results.** If a test fails, fix it. If you cannot fix it, log it as a Blocker and move on.
7. **The only exception: stop and ask me if something is very critical.** That means:
   - an action that could delete or damage my data, files or system outside the project folder;
   - a change that cannot be undone;
   - something that blocks the whole build, with no way to keep working around it.

   Ask one short, clear question, then wait for my answer. For everything else, follow rules 1–3 and keep going.

**Inputs:**
- `docs/` contains the approved **proposal** (`Agentica_FYP_Proposal.pdf`/`.docx`) and this file.
- The proposal is the source of truth for scope, features and architecture. This file gives the build order and implementation details.
- If they conflict, the proposal wins.

---

## 2. What Agentica is

Agentica is an installable desktop application that puts a governed AI agent over routine IT operations. It works in five steps:

1. The administrator types a request in plain language.
2. The agent retrieves the organisation's procedures (RAG).
3. It gathers live state from:
   - the local machine,
   - a Linux server over SSH,
   - a Windows server over WinRM.
4. It picks a tool, runs it and verifies the result.
5. It reports back in plain language.

**The language model never touches the operating system directly.**
- Every tool call goes through a deterministic policy engine that decides **Allow / Confirm / Deny**.
- Confirm pauses the task, saves its state, and resumes after the administrator approves, even after an app restart.
- The system runs on a cloud model, or entirely on a local model (Ollama) with no data leaving the machine.

Industry partner: ATCO Laboratories Limited. It has on-premises servers, works in a regulated environment, needs privacy, and requires human approval before any change.

---

## 3. Build target: everything before the Final FYP-I evaluation

| # | Gantt item | Feature |
|---|---|---|
| 4 | Data layer: PostgreSQL, pgvector and schema | — |
| 5 | Orchestration core and two-stage tool router | — |
| 6 | Natural-language chat interface | F1 |
| 7 | Live tool calls | F3 |
| 8 | Multi-turn session history | F4 |
| 9 | Server monitoring (self) | F7 |
| 10 | Policy and permission engine with risk tiers | F19 |
| 11 | RAG retrieval and knowledge-base management | F5, F6 |
| 12 | GUI task cards | F2 |
| 13 | Application status monitoring | F10 |
| 14 | Service monitoring and control | F9 |
| 15 | Remote Linux server management (SSH) | F11 |
| 16 | Local / offline private model mode | F14 |
| 17 | Remote Windows server management (WinRM) | F12 |
| 18 | FYP-I integration and testing | — |
| + | Guardrails v1, required before any modifying tool is enabled | F18 |

**Not in this build (FYP-II).** Leave room for these in the design, but do not implement them:
- F8: file operations
- F13: guided troubleshooting
- F15: model selection UI (a backend switch in `settings.yaml` is fine)
- F16: monitoring dashboard
- F17: web interface and login
- Tauri packaging and installers
- the full evaluation benchmark

**Never build:**
- NL-to-SQL
- email or browser automation
- web search
- image input
- RBAC or multiple users
- application discovery, or start/stop of non-service apps
- autonomous root-cause analysis
- scheduled tasks
- an approval queue with session or permanent grants
- an audit-log viewer
- a database-backed machine registry
- a setup wizard

---

## 4. Non-negotiable engineering rules

1. **No direct OS access for the model.** The only path is `route → agent → validate → policy → (approval) → execute → verify → report`. `execute` refuses any call without an attached policy decision, and a unit test must prove it.
2. **Deterministic policy engine** in pure Python with no LLM, loaded from `policy.yaml`. The defaults are:

   | Case | Default |
   |---|---|
   | read | Allow |
   | modify | Confirm |
   | destructive | Confirm |
   | hardline-blocklisted | **always Deny; config cannot override this** |
   | unknown tool | Deny |
3. **Confirm uses a LangGraph `interrupt()`** in a dedicated approval node with **no side effects before the interrupt**. State is kept with the PostgreSQL checkpointer, and the run resumes via `Command(resume=...)`. Approval is approve-once only.
4. **Never pass a model-generated string into a shell.** Never use `shell=True`. Use argv lists, and quote validated arguments (`shlex.quote` or PowerShell single-quote escaping).
5. **Live-state grounding.** Any statement about current system state comes from a tool call in the same turn.
6. **Secrets live only in the OS keyring** (`keyring`). They never appear in the DB, config, logs, prompts or API responses. Redact them in logs and streamed events.
7. **Local mode means zero egress.** No cloud client is created. The only outbound HTTP allowed is Ollama on localhost and configured targets. Embeddings are always local.
8. **Tool contract.** Every tool has:
   - a Pydantic input model (`extra="forbid"`) and an output model,
   - a category and a risk tier,
   - `run()`, plus `verify()` for modify/destructive tools,
   - unit tests against a fake target.

   Tools return structured errors and never crash the graph.
9. **Read-only before destructive.** Modifying tools are enabled only after the policy engine, the approval flow and guardrails v1 are tested.
10. **Agentless targets.** Install nothing on servers beyond OpenSSH (Linux) or the one-time WinRM HTTPS setup script (Windows).

---

## 5. Technology

| Area | Technology |
|---|---|
| Backend | Python 3.12, FastAPI, Pydantic v2, `sse-starlette` |
| Agent | LangGraph (StateGraph, interrupts) + `langgraph-checkpoint-postgres` (`AsyncPostgresSaver`, psycopg 3) |
| Database | PostgreSQL 16 + pgvector (HNSW) + PostgreSQL full-text search; SQLAlchemy 2 + Alembic |
| Embeddings | `sentence-transformers`, `intfloat/multilingual-e5-base` (768 dims), loaded from a local path |
| Local LLM | Ollama (already installed). `qwen2.5:7b-instruct` by default; `qwen2.5:14b-instruct` if RAM ≥ 16 GB and it is fast enough; `llama3.1:8b` as the alternative. Always set `num_ctx` explicitly (8192–16384). |
| Cloud LLM | Optional, behind one OpenAI-compatible provider interface. Used only if an API key is configured. |
| System and services | `psutil`; `pystemd` on Linux hosts, `pywin32` on Windows hosts (installed conditionally) |
| Remote | Fabric/Paramiko (SSH); `pywinrm` (HTTPS 5986, NTLM, pinned certificate) |
| Documents | `pypdf`, `python-docx`, `beautifulsoup4`, `watchdog` |
| UI | React + TypeScript + Vite, `@microsoft/fetch-event-source`. Runs in the browser for FYP-I and stays ready for Tauri later. |
| Quality | `pytest`, `pytest-asyncio`, `ruff`, GitHub Actions (Ubuntu + Windows) |

Pin exact versions in `pyproject.toml` and `package.json`.

---

## 6. Build plan (run all phases back to back)

### Phase 0: Environment
- Detect the OS, CPU, RAM and disk.
- Install anything missing: Git, Python 3.12, Node.js LTS (≥ 20), and Docker (or a native PostgreSQL 16 + pgvector).
- Make sure Ollama is running. Pull the model that fits the RAM and confirm that one tool-calling request works.
- **Repository:**
  - If the working folder is a clone of `https://github.com/Ahsa-n/Agentica`, use it.
  - Otherwise run `git init` in the working folder.

### Phase 1: Scaffold and foundations
1. Create the layout: `backend/`, `ui/`, `config/`, `eval/`, `infra/`, `.github/workflows/`, plus `CLAUDE.md` and `PROGRESS.md`.
2. Set up pyproject, ruff and pytest, and CI on Ubuntu and Windows.
3. Write the config loader:
   - Pydantic-validated YAML stored in the OS config dir via `platformdirs`.
   - Safe defaults are copied there on first run.
   - It rejects any key that looks like a secret.
   - Files: `settings.yaml`, `policy.yaml`, `targets.yaml`, `apps.yaml`.
4. Add the secrets module (keyring wrapper + redaction) and structured JSON logging with redaction.
5. Create the FastAPI app with `/api/health`, bound to 127.0.0.1, with a per-launch bearer token.
6. Scaffold React + Vite with an API client and an SSE helper.

### Phase 2: Data layer
1. Write `docker-compose.dev.yml` for PostgreSQL 16 + pgvector, bound to localhost only.
2. Write the Alembic migration with four tables:
   - `sessions`
   - `app_settings`
   - `kb_documents`
   - `kb_chunks`: a `vector(768)` column, a generated `tsvector` column, HNSW and GIN indexes, and `ON DELETE CASCADE` to its document.
3. Run the LangGraph checkpointer `.setup()`.
4. Test that migrations run up and down, and that a vector can be stored and found.

### Phase 3: Orchestration core, policy engine, router
1. **Tool framework.**
   - Add the ToolSpec and the registry, which exports JSON schemas and an enum of tool names.
   - Define a Target interface with two implementations:
     - `LocalTarget`: argv only, with timeouts and an output cap.
     - `FakeTarget`: for tests.
2. **Model provider.**
   - `OllamaProvider` handles tool calling, JSON-schema structured output and an explicit `num_ctx`. It records the model and its quantisation.
   - `CloudProvider` is optional.
   - The factory refuses to create a cloud client in local mode.
3. **LangGraph graph.**
   - Nodes: `route, gather_context, agent, validate, policy, approval, execute, verify, report`.
   - Limits: 10 steps; at most 2 validation retries; stop after 2 Denies in one turn.
   - Use `thread_id = session_id`.
4. **Policy engine.**
   - Decision order, applied in sequence:
     1. unknown tool
     2. schema invalid
     3. hardline
     4. protected resources (`sshd`, `ssh`, `WinRM`, Agentica's own DB)
     5. path rules
     6. dangerous patterns
     7. per-target override (the most specific glob)
     8. per-tool override
     9. risk-tier default
   - When more than one rule applies, the most restrictive result wins.
   - Every decision returns a reason and a rule ID.
   - Use table-driven tests with **100% branch coverage**.
5. **Approval flow.**
   - Sequence: interrupt → `approval_required` event → `POST /api/sessions/{id}/approvals/{call_id}` → resume.
   - Write a **kill-and-resume test**: the backend restarts while a run waits for approval, and after approval the call executes exactly once.
6. **Embedding service + two-stage router.**
   - `config/router/categories.yaml` holds 15–30 example requests for each category: `monitoring, services, applications, logs, network, knowledge, remote`.
   - The router takes the top category plus any within a margin, up to 3 categories.
   - A no-tool threshold handles conversational requests.
   - `get_system_overview` and `expand_scope` are always available; `expand_scope` can be called at most 2 times per turn.
   - A `routing_mode: routed | flat` setting switches between routed and flat tool selection.

### Phase 4: Chat, live tool calls, session history (F1, F3, F4)
1. **Streaming endpoint.** `POST /api/sessions/{id}/messages` streams SSE events:
   `run_start, route, retrieval, tool_start, policy_decision, tool_end, approval_required, verify, token, final, error`.
2. **Run control.** Add a cancel endpoint, and allow only one active run per session (return 409 otherwise).
3. **UI:**
   - chat with streaming, sanitised Markdown and a Stop button;
   - **ToolCallCard**: tool, target, args, decision badge, duration, result, and expandable raw output;
   - **ApprovalPrompt** inside the card: target, action, risk tier and rule. Approve is not the default for destructive actions.
   - session sidebar: list, open and delete sessions. History is restored from checkpoints after a restart.
4. **Context budget for small models.** Keep recent turns, summarise older ones, and use compact tool summaries in the prompt.

### Phase 5: Server monitoring, self (F7)
1. Add the psutil read tools:
   - `get_system_overview`
   - `get_cpu_usage`
   - `get_memory_usage`
   - `get_disk_usage`
   - `get_network_stats`
   - `list_top_processes`
   - `get_process_details`
2. Define shared result models that the remote parsers will reuse.
3. Start `eval/tasks/` in YAML. Each task has a prompt, the gold tool, gold args, whether confirmation is expected, and a success check.
4. Add a grounding test: a state question always triggers a tool call.

### Phase 6: RAG and knowledge-base management (F5, F6)
1. **Extraction.** Support PDF, DOCX, HTML, Markdown and TXT. A scanned PDF is marked "failed: no extractable text".
2. **Chunking.** Chunks are structure-aware, about 300–500 tokens, with about 50 tokens of overlap. Numbered procedures stay together, and each chunk gets a heading-path prefix.
3. **Ingestion.** Skip unchanged files by SHA-256. Replace atomically: old chunks are deleted and new ones inserted in one transaction.
4. **Hybrid search.**
   - Dense: top 50 by pgvector cosine.
   - Keyword: top 50 with `websearch_to_tsquery` and `ts_rank_cd`.
   - Fuse the two lists with RRF (k = 60).
5. **`search_knowledge_base` tool.** Returns results with citations. It returns "not found" when the best similarity is below a calibrated threshold, and never invents a procedure.
6. **Folder watcher.** Debounced, rescans on startup, and ignores temp files.
7. **Knowledge Base page.** Folder picker, a document list with status and chunk count, add, remove from the index, re-index, and test search.
8. **Corpus and evaluation.**
   - Write sample SOPs in `eval/kb/`: stopped service, full disk, high memory, nginx/IIS restart, and similar.
   - Write at least 50 retrieval questions and a script for Recall@5, MRR and nDCG.
   - Compare hybrid against dense-only. The target is Recall@5 ≥ 0.85. Record the numbers in `PROGRESS.md`.

### Phase 7: Guardrails v1 (F18)
1. **Command analysis.**
   - Normalise and `shlex`-parse. A parse error gives at least Confirm (fail closed).
   - Split on `; && || | &`, and inside `$( )` and backticks.
   - Strip `sudo`, `env`, `timeout` and similar wrappers.
2. **Hardline blocklist (always Deny):**
   - `rm -rf /`
   - `mkfs`
   - `dd` to a block device
   - fork bomb
   - `chmod -R 777 /`
   - `Format-Volume`
   - `diskpart clean`
   - `vssadmin delete shadows`
   - encoded PowerShell
   - download-and-run pipes
   - and similar commands
3. **Dangerous patterns.** Use the Hermes Agent pattern set if its licence allows; otherwise write our own. Record the choice in `PROGRESS.md`.
4. **Test corpus.** At least 60 positive and negative cases, including `sudo`, chained and `$( )` variants.
5. **Prompt injection.** Tool and document text is wrapped as data, never as instructions.

### Phase 8: Task cards, application status, service control (F2, F10, F9)
1. **Task cards.**
   - Enabled cards: System Monitoring, Services & Applications, Remote Servers, Knowledge Base.
   - Files and Troubleshooting appear as disabled cards labelled "coming in FYP-II".
   - Selecting a card force-includes its categories in routing and shows example prompts.
2. **Application status.**
   - Apps come from `apps.yaml`: a process and/or a service, a TCP port, and an optional HTTP check.
   - Each app is reported as UP, DEGRADED, DOWN or UNKNOWN, with the result of each check.
3. **Services.**
   - Read tools: `get_service_status`, `list_services`.
   - Modify tools: `start_service`, `restart_service`. Destructive tool: `stop_service`.
   - All three need Confirm by default, and each `verify()` polls status for up to 30 s.
   - Protected services are always denied.
   - Linux uses pystemd, with a fallback to `systemctl` via argv. Windows uses pywin32.

### Phase 9: Remote Linux, then remote Windows (F11, F12)
1. **Test targets (set these up yourself).**
   - Linux:
     - Use a Docker container with systemd and `openssh-server` (e.g. a systemd-enabled Ubuntu image) and a sample service such as nginx.
     - Add it to `docker-compose.dev.yml`.
   - Windows:
     - If the host is Windows, run `infra/windows-target-setup.ps1` on localhost (needs admin).
     - Otherwise, test with recorded PowerShell JSON fixtures, and log the live Windows test as a Blocker.
2. **SSHTarget.**
   - Fabric connection pool with key-based auth; the passphrase lives in the keyring.
   - Timeouts and a 256 KB output cap.
   - Host-key pinning: the fingerprint is trusted once, and a changed key is rejected.
   - Use `sudo -n` for control actions.
   - Linux parsers with fixture tests, mapped to the shared result models: `/proc/stat`, `/proc/meminfo`, `df -kP`, `ps`, `systemctl show`, `journalctl`, `ss -tlnH`.
3. **WinRMTarget.**
   - `pywinrm` to `https://host:5986/wsman` with NTLM and `server_cert_validation="validate"` against the pinned certificate. Never use "ignore" and never use HTTP 5985.
   - Always pipe PowerShell output through `ConvertTo-Json`, and handle the single-object vs array case.
   - Add a PowerShell escaping helper with injection tests.
4. **Setup scripts (both idempotent).**
   - `infra/linux-target-setup.sh`: creates the user and key, adds scoped sudoers for `systemctl`, and checks it with `visudo -c`.
   - `infra/windows-target-setup.ps1`: enables remoting, creates a self-signed certificate, adds the HTTPS listener, opens firewall port 5986, exports the certificate and prints the thumbprint.
5. **Machines page.**
   - Lists targets from `targets.yaml`, with a Reload button.
   - Actions: Set credentials (writes to the keyring), Trust (fingerprint or certificate), Test connection.
   - An untrusted target cannot be used.
6. **Remote support for existing tools.**
   - The same tool names take a `target` argument: monitoring, services and app status.
   - Add `get_logs` (`journal:<unit>` or `eventlog:<LogName>`, filtered in Python, never in a shell).
   - Add `check_port`.

### Phase 10: Local / offline private model mode (F14)
1. **Egress guard.**
   - All outbound HTTP goes through one client factory. In local mode it allows only localhost Ollama and configured targets.
   - Set `HF_HUB_OFFLINE=1` and `TRANSFORMERS_OFFLINE=1`.
   - Load the embedding model from a local path.
   - Keep LangSmith tracing off.
2. **Offline test.** An automated test runs the smoke tasks with outbound network blocked and asserts that there is no external traffic.
3. **Model choice.**
   - Compare `qwen2.5:7b-instruct`, `llama3.1:8b` and, if RAM allows, `qwen2.5:14b-instruct` on the eval tasks.
   - Measure top-1 tool accuracy, schema-valid rate and median latency.
   - Set the best one as the default and record the numbers in `PROGRESS.md`.

### Phase 11: FYP-I integration and testing
1. Run the full test suite on Linux and Windows (CI), and fix all integration bugs.
2. Grow `eval/tasks/` to at least 30 labelled tasks across the built features. Run them in routed and flat mode with the local model, and record the numbers in `PROGRESS.md`.
3. Run a final end-to-end check for each feature in Section 3: request → tool → policy → approval where needed → verify → report.
4. Update `PROGRESS.md` with final status, Decisions, Blockers and what is left for FYP-II.

---

## 7. Definition of done

- [ ] All items in Section 3 work end to end with the local Ollama model.
- [ ] No tool can execute without a policy decision. Modify and destructive actions ask for approval by default. Hardline commands are always denied.
- [ ] A run waiting for approval survives a backend restart and executes exactly once after approval.
- [ ] State claims come from same-turn tool calls, and KB answers cite the document and section.
- [ ] Credentials exist only in the OS keyring.
- [ ] Local mode works with no internet access.
- [ ] CI is green on Ubuntu and Windows. Every tool has unit tests, and the policy engine has 100% branch coverage.
- [ ] `PROGRESS.md` is complete.

**Start Phase 0 now and keep going until every item above is checked.**
