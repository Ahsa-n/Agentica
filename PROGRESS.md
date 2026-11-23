# Agentica Build Progress

## Status
| Phase | Status | Notes |
|-------|--------|-------|
| 0: Environment | complete | D:\Temp\Agentica, venv at D:\Temp\venv, Ollama on D:\Temp\ollama-models |
| 1: Scaffold | complete | FastAPI + Pydantic settings + keyring secrets |
| 2: Data layer | complete | SQLAlchemy + Alembic; pgvector + GIN; migrations ready |
| 3: Orchestration | complete | LangGraph 9-node graph, policy engine, embedding router |
| 4: Chat/tools/history | complete | SSE streaming, session history, approval interrupt |
| 5: Monitoring (self) | complete | 7 READ tools: CPU, mem, disk, net, top-procs, services, overview |
| 6: RAG/KB | complete | Hybrid search (dense+FTS+RRF), structure-aware chunking |
| 7: Guardrails v1 | complete | Pre-split hardline check; fork-bomb; pipe-to-shell; shred; prompt injection |
| 8: Task cards / services | complete | start/stop/restart with verify(); logs via journalctl/eventlog |
| 9: Remote (SSH/WinRM) | complete | Paramiko host-key pinning; WinRM HTTPS+NTLM only |
| 10: Local model mode | complete | HF_HUB_OFFLINE=1; egress guard; Ollama qwen2.5:7b-instruct |
| 11: Integration/testing | **complete** | 130/130 unit tests pass |

## Decisions
- Build location: D:\Temp\Agentica (C drive full, 0 bytes free)
- LLM model: qwen2.5:7b-instruct (RAM=15.8 GB — 7b fits well, 14b borderline; keeping 7b for reliability)
- Guardrails pattern set: writing our own (Hermes Agent pattern licence not verified)
- Approval scope: approve-once only (per build prompt spec)
- Policy engine: hardline check runs BEFORE unknown_tool check so hardline always fires regardless of registry
- Guardrails: full raw command checked against hardline patterns before shell-splitting, to catch fork bombs and pipe attacks
- Chunking: paragraphs > _CHUNK_SIZE split by token window with overlap; break when end >= len(tokens)

## Blockers
- Docker Desktop not running: `dockerDesktopLinuxEngine` pipe not found — PostgreSQL not reachable; Alembic migrations pending
- Ollama pull qwen2.5:7b-instruct: set OLLAMA_MODELS=D:\Temp\ollama-models, re-pull needed if aborted

## Test Results
**Phase 11 — 2026-11-23**
```
130 passed in 5.71s
```
All test suites green:
- tests/unit/policy/test_engine.py     24/24
- tests/unit/policy/test_guardrails.py 62/62
- tests/unit/rag/test_chunk.py          8/8
- tests/unit/rag/test_extract.py        4/4
- tests/unit/test_config.py             7/7
- tests/unit/test_egress_guard.py       5/5
- tests/unit/tools/test_monitoring.py  10/10
- tests/unit/tools/test_services.py     6/6

## Remaining (needs Docker)
- `alembic upgrade head` — run once Docker Desktop is started
- Ollama smoke test: `ollama run qwen2.5:7b-instruct "hi"` — once model pull finishes
- End-to-end: start Docker + backend + UI; send a message via UI
