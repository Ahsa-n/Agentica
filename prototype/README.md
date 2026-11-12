# Host monitoring prototype

A working spike of **F7 (local system monitoring)** with **F1/F3 (chat with live tool calls)** on a
local Ollama model (**F14**). The agent answers IT questions from its own knowledge and calls
read-only monitoring tools only when asked about this host's performance or health.

This is a prototype to learn from, not the production layout. See [Gaps against the spec](#gaps-against-the-spec).

## Run it (Windows)

```powershell
pip install -r requirements.txt
ollama pull qwen3.8:27b          # or any tool-capable model, e.g. qwen2.5:7b
python main.py                   # then open http://127.0.0.1:8000
```

| Variable | Default | Purpose |
|---|---|---|
| `AGENTICA_MODEL` | `qwen3.8:27b` | Ollama model to use |
| `AGENTICA_KEEP_ALIVE` | `-1m` (never unload) | How long the model stays in VRAM when idle, e.g. `30m` |

The model is preloaded in the background when the server starts, so the first reply does not wait
for the load (about 30 s for the 27B model from a cold disk cache).

## Files

| File | What it does |
|---|---|
| `main.py` | FastAPI server, system prompt, agent loop (up to 5 tool rounds), model preload |
| `monitor.py` | The read-only tools and their JSON schemas |
| `index.html` | Chat UI: Markdown rendering (sanitized), welcome cards, code copy buttons, light/dark |
| `static/` | Vendored `marked`, `DOMPurify`, Inter and JetBrains Mono, so the UI works with no network |

## Tools

All tools are read-only and run on the local host.

| Tool | Returns | Spec §14.5 equivalent |
|---|---|---|
| `system_overview` | OS, uptime, CPU %, RAM, page file, disks, GPU (nvidia-smi), battery, top 3 processes | `get_cpu_usage`, `get_memory_usage`, `get_disk_usage` |
| `top_processes` | Processes grouped by name, sorted by CPU or memory, optional name filter | `list_top_processes` |
| `event_log` | System/Application log entries grouped by source + event ID, with counts | `get_logs` (Windows event log source) |
| `network_info` | Adapters, IPs, current throughput, connections per process, listening ports | `get_network_stats` |
| `services` | Auto-start services that are stopped, or services matching a name | `list_services`, `get_service_status` |

## Measured tool selection

Prompts that should and should not trigger a tool (greetings, general IT questions, scripting
requests vs. performance and health questions), each run several times:

| Model | Wrong tool decisions |
|---|---|
| `qwen3.8:27b` | 0 / 44 |
| `qwen2.5:7b` | 2 / 63 (both on "what does event ID 41 mean?", a defensible call) |

Two prompt details mattered: tool descriptions must not say "use for general questions" (small
models read that literally), and the system prompt should name which topics need tools.

## Gaps against the spec

- **No Policy and Permission Engine (§11, rule 3).** Tools are called directly. Acceptable only
  because every tool is read-only; production tools must go through the engine.
- **Not in the §27.2 layout.** Production code belongs in `backend/agentica/tools/monitoring.py`,
  `logs.py`, `network.py`, `services.py`, with the UI in `ui/` (React + TS + Vite).
- **Tool names and schemas are not canonical.** No Pydantic models, `ToolSpec` registry or `target`
  parameter yet.
- **No unit tests** (rule 9) and no benchmark tasks (§25).
- **Windows only.** Event logs are read through PowerShell `Get-WinEvent` (argv list with validated
  values, no `shell=True`).

## Third-party assets

`marked` (MIT), `DOMPurify` (Apache-2.0 / MPL-2.0), Inter and JetBrains Mono (SIL OFL 1.1), served
locally from `static/` so local mode needs no network access (rule 7).
