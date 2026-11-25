# Agentica — web console

Local web front end for the Agentica IT-operations agent, running on Ollama.

## Run

```
pip install -r requirements.txt
ollama pull qwen3.5:9b           # chat model
ollama pull embeddinggemma       # tool router (stage 1); without it Auto falls back to load_tools
python server.py --open          # http://127.0.0.1:8787
```

On Windows you can also double-click `run.bat`. Ollama must be running (default `http://127.0.0.1:11434`;
override with the `OLLAMA_HOST_URL` env var). For LAN/mobile access use `--host 0.0.0.0` — note there is no auth yet.

Starting, stopping and restarting most Windows services needs an **elevated** process
(right-click `run.bat` → *Run as administrator*). Without it those actions fail cleanly with
"Access denied"; read-only tools work either way.

## Layout

| File | Role |
|---|---|
| `router.py` | **Stage 1 of the two-stage tool router**: embeds the request (EmbeddingGemma via Ollama, CPU) and picks the toolsets to load |
| `agent.py` | **The agent**: a LangGraph graph (route → model → tool → approval → finish), checkpointed to `data/checkpoints.db`; streams events to the UI; `run_task()` for headless runs |
| `actions.py` | The single path from a tool request to its outcome: policy check → run / bound approval / refuse → audit |
| `server.py` | FastAPI gateway: UI, session API + event streams, telemetry SSE, approvals, audit, machines |
| `policy.py` | Policy engine: scope, strict args, risk grading, hardline guardrails, `policy.yaml` rules |
| `policy.yaml` | Operator-editable policy (tier defaults, per-target rules, extra protected services). Hot-reloaded. |
| `tools.py` | Tool registry: Pydantic argument models, risk assessment per call, toolsets (task cards) |
| `services.py` | Service lookup / listing / verified start-stop-restart (Windows SCM via pywin32, systemd) |
| `telemetry.py` | 1 s psutil sampler |
| `hosts.py` | Where tools run: `LocalHost`, `WinRMHost` (fixed PowerShell over pypsrp), `SSHHost` (Linux), target resolution, keyring |
| `linux_remote.py` | The script sent to Linux machines over SSH and run with `python3` (reads `/proc`, `systemctl`, `ss`, `ip`) |
| `fleet.py` | Polls every registered machine every 7 s for the monitor panel |
| `apps.py` | Application status monitoring: checks, up / degraded / down verdicts, history + restart detection, 15 s monitor |
| `appfind.py` | Windows helpers: windows + "Not responding" detection, friendly names, listening ports, installed apps, launching |
| `machines.py` | Machine registry input parsing + reachability prober |
| `scripts/` | Target setup: `Enable-/Disable-AgenticaTarget.ps1` (Windows), `enable-/disable-agentica-target.sh` (Linux) |
| `store.py` | SQLite (`data/agentica.db`): sessions + transcripts, approvals, audit log, machines. Interim until PostgreSQL. |
| `static/` | Web console (`index.html`, `styles.css`, `app.js`) |

## How a request runs (server-side agent)

The agent loop runs on the server as a LangGraph graph; the browser only renders.

```
POST /api/sessions/{id}/messages ─▶ agent.py graph:  route ─▶ model ─▶ tool ─▶ (approval: interrupt) ─▶ tool … ─▶ model ─▶ finish
                                         │ every step is checkpointed (data/checkpoints.db)
GET  /api/sessions/{id}/events  ◀────────┘ live events (SSE): text / thinking deltas, tool rows, status, turn end
POST /api/sessions/{id}/approval  {approve|deny}   → resumes the paused graph
POST /api/sessions/{id}/cancel                     → stops the turn (closing the tab does NOT stop it)
```

- **route** is stage 1 of the tool router (below); **model** streams one round from Ollama; **tool** runs one queued call through `actions.py` (policy engine);
  **approval** pauses with `interrupt()` until the operator answers; **finish** records stats and the transcript.
- A run paused for approval survives a page reload and a **server restart**; on startup, runs cut off mid-step are
  closed as interrupted.
- Chat history is stored on the server (`sessions`, `session_items`), so any browser sees the same sessions.
- **Headless / benchmarks**: `await agent.run_task(prompt, model=..., mode="auto"|card, on_approval=lambda info: "approve")`
  returns the answer, tool calls, decisions, grounding and timings without any browser (see `tests/`).
- LangSmith tracing is forced off: nothing leaves the machine.

## Policy engine

Every tool call goes through `PolicyEngine.check()`; the model has no other path to the OS.

1. registered tool? → 2. inside the active scope (card / loaded toolsets)? → 3. known target?
→ 4. strict argument validation (Pydantic, `extra=forbid`) → 5. **risk grading of the concrete call
against live state** → 6. hardline guardrails → 7. `policy.yaml` rules (first match) → 8. tier defaults.

| Tier | Meaning | Default |
|---|---|---|
| R0 | read-only, or a no-op (starting a service that is already running) | allow |
| R1 | reversible change (start a stopped service) | confirm |
| R2 | disruptive change (stop / restart a running service) | confirm |
| R3 | destructive or protected (e.g. stopping `RpcSs`, `WinRM`, `WinDefend`, `sshd`) | **deny, not overridable** |

**Confirm** creates an approval bound to the exact validated arguments; the agent pauses and the UI shows an
approval card. Approving re-checks the policy against the current state, then executes the stored arguments and
verifies the result. Approvals expire after `approval_timeout_minutes` (an expired request resumes the run as
"expired"). `POST /api/tools/{name}` and `POST /api/approvals/{id}` expose the same path directly for testing.

Every decision and outcome is written to the audit log (`GET /api/audit`). Service actions report
`verified: true/false` after re-reading the service state; `false` is logged as `unverified`.

## Remote Windows machines (WinRM)

Agentless: nothing is installed on the targets. Agentica connects over **WinRM, HTTP 5985, NTLM**
(pypsrp encrypts the traffic at the message level) and runs a fixed, parameterised PowerShell script per
operation (`hosts.py`, `PS = {...}`). Every script returns the same JSON as the local implementation, so tools,
policy, approvals and the UI are identical for local and remote targets.

1. **On each target**, once, in an elevated PowerShell:
   `powershell -ExecutionPolicy Bypass -File .\Enable-AgenticaTarget.ps1`
   It creates a local administrator account **`agentica`** (you choose its password, typed twice;
   `-UserName <name>` for another name, `-NoCreateUser` to use an existing admin instead), enables remoting,
   lets local admins sign in remotely, opens 5985 (`-AgenticaIP <ip>` limits it to the Agentica PC) and prints the
   machine name, IPs and username to enter in Agentica. Undo with `Disable-AgenticaTarget.ps1` (also deletes the
   account; `-KeepUser` keeps it). Both scripts only ever modify or delete an account they created themselves.
2. **In Agentica**: Machines → `+` → IPs / hostnames (one or many) + username / password. Click a machine to
   change credentials or **Test** the connection (shows OS, PowerShell version, and whether the account is admin).
   Passwords go to Windows Credential Manager (`keyring`); the database only stores the username.

**Fleet monitoring.** `fleet.py` polls every registered machine every **7 s** (in parallel, one round trip:
the fixed `metrics` script → CPU, memory, system disk, uptime) and keeps ~4.5 min of history. The data rides on
the existing telemetry SSE stream; the monitor panel shows a card per machine and the top-bar pill shows
`HOSTS up/total`. Machines without credentials show *needs setup*; unreachable ones fail fast using the port probe.

**Developing without a second machine.** Start with `AGENTICA_DEV=1` to enable the `local-ps` transport: it runs the
exact remote scripts on this PC through `powershell.exe`, so tools, approvals and fleet polling can be exercised
end to end. Register one with `POST /api/machines {"hosts": "loop-01", "os": "windows", "transport": "local-ps"}`.

## Remote Linux machines (SSH)

Also agentless. Agentica connects over **SSH (port 22)** with paramiko and, for each operation, sends
`linux_remote.py` and runs it with the target's own **`python3`** (preinstalled on Ubuntu, Debian, RHEL, Fedora…).
It reads `/proc`, `/sys`, `/etc/os-release` and the output of `systemctl`, `ss` and `ip`, and returns the same JSON as
the local and Windows tools. Every tool, the policy engine, approvals, fleet monitoring and application monitoring work
unchanged; desktop windows ("Not responding") and opening apps are Windows-only.

1. **On each Linux machine**, once: `sudo bash enable-agentica-target.sh`. It installs `openssh-server` / `python3`
   if missing, creates the user **`agentica`** (you choose the password, typed twice), lets it run **only**
   `systemctl start|stop|restart <service>` as root without a password (`/etc/sudoers.d/agentica`, validated with
   `visudo`), allows password sign-in for that user only, opens TCP 22 in ufw / firewalld (`--from <ip>` limits it), and
   prints what to enter in Agentica. `--user NAME` / `--no-create-user` as on Windows. Undo:
   `sudo bash disable-agentica-target.sh` (SSH is left running so you are not locked out).
2. **In Agentica**: Machines → `+` → OS **Linux** (connection SSH / 22) + username / password.

Service control uses `sudo -n` (the rule above), falling back to `sudo -S` with the saved password for accounts that
have full sudo rights. On Linux, `list_services` "auto_stopped" lists **failed** units. Host keys are trusted on first
use (no host-key pinning yet).

**Testing without Linux**: `tests/fake_ssh_server.py` is a real SSH server (paramiko) that runs the exact command
Agentica sends against recorded Linux data in `tests/fixtures/linux`; `python tests/linux_ssh.py` exercises everything
end to end. The real check is still a Linux machine or VM.

**Which machine does a request run on?**

- The **target picker** in the top bar sets the session's target (default: This PC).
- **Naming a machine in chat** (label, hostname, short hostname or IP, or "this PC") switches the session
  target. It is deterministic string matching, not the model, and it sticks for follow-ups.
- The model also gets an optional `target` argument restricted to the registered machines, used when one message
  names several machines ("compare this PC and lab-01"). The server validates it; unknown names are refused.
- Every tool result carries `machine`, tool rows show `@ machine`, and approval cards name the machine.

## Application status monitoring

Register an application once: monitor panel → **Applications → +** and **pick it from the running apps** (friendly
names, process count, memory, listening ports; one click adds a suggested port check), or just ask in chat
("start monitoring VS Code"), or fill in the checks yourself.

| Check | Where it runs | Passes when |
|---|---|---|
| Process name(s) | on the app's machine (local or WinRM) | at least one matching process is running; also reports total CPU / memory, and (this PC) whether any of its windows is **Not responding** |
| Service | on the app's machine | the service is running |
| TCP port | from Agentica's PC (as a user reaches it) | the port accepts a connection |
| URL | from Agentica's PC | HTTP status < 400 (slower than 3 s counts as degraded) |

Verdict: **up** (every check passes) · **degraded** (running but a port / URL fails, a window is frozen, or slow) ·
**down** (not running, or nothing responds) · **unknown** (machine unreachable / no credentials). Apps are re-checked
every 15 s; the monitor panel shows a card per app with the evidence and "up since …", the top-bar pill shows
`APPS up/total`. Every status change is recorded, and an app whose processes were all replaced between two checks is
recorded as **restarted** (a crash that recovered by itself).

**Opening apps.** "Open VS Code" / "open calculator": `app_open` finds any installed app by the name you use (fuzzy:
"vs code", "vscode", "ms edge", "calc"…), asks for approval, launches it through Explorer (as the signed-in user, never
elevated) and verifies that a window or process appeared. Apps do not need to be registered to be opened. Opening is
only possible on this PC: Windows does not show programs started remotely over WinRM on anyone's screen.

Agent tools (Applications card, or Auto via `load_tools(["apps"])`): `app_status` (read-only, also in Troubleshoot;
always checks each app on its own machine), `app_open` (R1, asks first) and `app_register` (R1, asks first; refuses
duplicates).

## Tool scoping (task cards)

Toolsets live in `tools.py` (`TOOLSETS`); a tool can belong to several. Troubleshoot is read-only on
purpose: it diagnoses, and changes are made from the Services card behind approval.

| Mode | Tools sent to the model | Tool call required? |
|---|---|---|
| **Auto** (default) | the toolsets the **router** picked for this request (often none), plus a small `load_tools(domains)` fallback for anything it missed | no |
| **A card** (Monitoring, Storage, …) | only that card's tools | **yes**: an answer is held back until a tool has returned evidence. If the model skips tools it gets one corrective nudge; if it still skips, the card's `default` check runs automatically. |

### Two-stage tool router (Auto mode)

Small local models pick the wrong tool more often when many tools are in context, so Auto mode narrows the set first.

1. **Stage 1, `router.py`, no LLM.** Every toolset has short example requests (`router.EXAMPLES`, plus
   "is &lt;app&gt; running" for each monitored app), and a **"none"** class holds general IT questions and chit-chat.
   The examples are embedded once with **EmbeddingGemma** (308M, local Ollama, pinned to the CPU so the chat model
   keeps the GPU) and cached in `data/router_index.json`. Each request is embedded (~50 ms) and every class is scored
   by the mean of its 2 most similar examples. A toolset is loaded if it scores ≥ 0.50 and beats "none". A second
   toolset close to the best (within 0.02) is loaded too. Multi-part requests ("restart nginx **and** check disk
   usage") are also scored clause by clause, and a short follow-up ("and on web-01?", "restart it") that isn't
   clearly routed on its own is scored together with the previous request. Machine names and IPs are stripped first.
2. **Stage 2, the model**, sees only those tools and picks the exact tool and arguments. If the router missed a
   domain, `load_tools` is still offered, so the router can only save a round, never block one. A toolset the router
   added but nothing used is not kept for later turns. Toolsets that were used stay loaded for 3 turns.

The chat shows each decision ("Routed to **Storage** · disk_usage · 48 ms"; hover for every score). If the
embedding model is missing, the turn says so and falls back to `load_tools`. `GET /api/router` shows status;
`POST /api/router/route {"text"}` shows what a request would load without running it. Setup: `ollama pull embeddinggemma`.

**Routing modes** (`AGENTICA_ROUTING` env, or `"routing"` per message / `run_task(routing=...)`), used by the benchmark:
`embed` (default, two-stage), `llm` (the model loads tools itself with `load_tools`), `flat` (every tool loaded up
front: the proposal's flat baseline).

**Evaluation**: `python tests/router_eval.py` scores the router on 83 labelled requests, none of which are routing
examples. Thresholds were tuned on the dev split only (`--tune`). Held-out test split: every request got the
toolsets it needed (100%), 95% got exactly the right set, and 5 of 7 general questions loaded nothing (the other 2
loaded a harmless extra toolset).

The server enforces the scope too: a call to a tool outside the active scope returns `DENY` (HTTP 403),
so a hallucinated tool call becomes a visible refusal instead of an action.

## Live telemetry

A background thread samples psutil once per second into a 90-second ring buffer. The browser opens
`GET /api/telemetry/stream` (Server-Sent Events) and the server pushes one JSON message per sample,
so the monitor updates every second without polling. The stream pauses when the tab is hidden.

## Known issues

From the hallucination benchmark (`tests/hallucination_eval.py`, 2026-11-25, qwen3.5:9b, 39 tasks × think off / on,
every flag reviewed by hand; raw answers are saved locally in `tests/results/`, which is git-ignored):

| Issue | Seen | Status |
|---|---|---|
| **Auto mode can answer a live question without calling a tool.** The router loaded Monitoring, but the model skipped it and invented an uptime ("about 7 hours"; real: ~270 h). Task cards hold such answers; Auto does not yet. | 1 / 39 (think off) | Open. Planned fix: when the router loaded tools, hold an answer that has no tool result and nudge once, as the cards do. |
| **Empty answer with think on.** The tool ran, but the model put everything into its reasoning and wrote no reply. | 3 / 39 (think on) | Open. Planned fix: if a turn ends with no text after a tool ran, ask once for the answer. |
| **Wrong details in suggested manual commands** when no tool can do the job (e.g. "Event IDs 100–199 are errors", `whoami /sessions`, `MaxEvents` inside `-FilterHashtable`). No live values were invented. | 4 / 78 | Open. Mitigation: verify commands before running them; a prompt rule may reduce it. |
| **Occasional invented figure in an otherwise correct answer** (a "133 MB threshold of the 26th process" after asking for 25). | 1 / 78 | Open (covered partly by the fixes above). |
| **General-knowledge slip** (chmod 755 described the owner as read + execute). | 1 / 20 knowledge answers | Inherent to the 9B model. |
| **Ollama runner crash** (`llama-server … 0xc0000409`) once, with system memory at ~87 %. | 1 / 78 | Environment. Close memory-heavy programs; the turn reports the error instead of hanging. |

What held up: no false "done" claims after a declined or refused action (8 / 8, services verified unchanged);
"can't measure that" answered honestly with no invented values (14 / 14); non-existent services, machines, apps
and processes reported as not found (9 / 10); follow-up recall matched the earlier tool results (8 / 8);
0 invented tool names or invalid arguments in 46 tool calls.

## Notes

- **Think toggle** (`Alt+T`) sends Ollama's `think` flag; the reasoning streams into a collapsible row.
- **System monitor**: minimized pill in the top bar; click it (or `Alt+M`) to expand the full panel.
- Shortcuts: `Alt+N` new session · `Alt+M` monitor · `Esc` stop generation · `/` focus input.
