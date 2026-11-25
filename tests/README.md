# Tests

| Script | What it checks | Needs |
|---|---|---|
| `router_eval.py` | Stage-1 router accuracy on 83 labelled requests (dev / held-out test); `--tune` grid-searches the thresholds on dev only | Ollama + `embeddinggemma` |
| `agent_headless.py` | The LangGraph agent end to end without a browser: router (embed / llm / flat, multi-part, missing embedding model) / Auto / cards / hold-nudge-forced, approvals (approve, deny), hardline, cancel, **pause -> restart -> resume**, remote targets (loopback) | Ollama + `qwen3.5:9b` + `embeddinggemma` |
| `hallucination_eval.py` | Hallucination benchmark (39 tasks, think off / on): invented live numbers, "can't measure" honesty, non-existent entities, false action claims, follow-up recall, IT facts, invented tools / bad args. Approvals are denied, so nothing changes. Answers + tool results saved to `tests/results/` (git-ignored: they contain this PC's details). ~30–40 min | Ollama + `qwen3.5:9b` + `embeddinggemma` |
| `policy_api.py` | Policy engine over HTTP: every allow / confirm / deny path, double approve, rules + hot reload, invalid YAML, audit | running `server.py` |
| `apps_api.py` | Application status: up / down / degraded verdicts (process, service, port, URL), validation, `app_status`; `app_open` / `app_register` ask first and refuse unknown apps | running `server.py` |
| `linux_ssh.py` | Linux over SSH end to end: a real SSH server (`fake_ssh_server.py`) runs the exact script against recorded Linux data (`fixtures/linux`); results, shapes, sudo, sign-in / connection errors, reconnect | nothing |
| `remote_scripts.py` | Every WinRM PowerShell script, run locally, returns the same JSON shape as the local tools; real start/stop | Windows |

The tests toggle the harmless `wcncsvc` service and leave it stopped.
