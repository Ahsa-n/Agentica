# Agentica — Claude Code Rules

## Project
Agentica: governed AI agent over IT operations. Desktop app (React + FastAPI + LangGraph + PostgreSQL + Ollama).
Industry partner: ATCO Laboratories Limited.
Working directory: `D:\Temp\Agentica`

## Non-negotiable rules (Section 4 of FYP1_BUILD_PROMPT.md)
1. No direct OS access for the model — every call goes through route→agent→validate→policy→(approval)→execute→verify→report.
2. Policy engine is deterministic Python, loaded from `policy.yaml`, no LLM.
3. Confirm uses LangGraph `interrupt()` with PostgreSQL checkpointer; resume via `Command(resume=...)`.
4. Never pass model-generated strings into a shell. Never `shell=True`. Use argv lists.
5. Live-state grounding: system state claims always come from a tool call in the same turn.
6. Secrets live only in the OS keyring (`keyring`). Never in DB, config, logs, prompts.
7. Local mode = zero egress. `HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1`.
8. Every tool has: Pydantic input/output models (`extra="forbid"`), category+risk tier, `run()`, `verify()` for modify/destructive, unit tests.
9. Read-only tools before destructive. Modifying tools enabled only after policy+approval+guardrails are tested.
10. Agentless targets: OpenSSH (Linux), WinRM HTTPS (Windows).

## Technology
- Backend: Python 3.12, FastAPI, Pydantic v2, sse-starlette
- Agent: LangGraph + langgraph-checkpoint-postgres (psycopg3)
- DB: PostgreSQL 16 + pgvector (HNSW) + FTS; SQLAlchemy 2 + Alembic
- Embeddings: sentence-transformers, intfloat/multilingual-e5-base (768d), local path
- LLM: Ollama **qwen2.5:3b-instruct** — the only model installed and used (project decision 2026-11-24: the dev laptop is CPU-only, i7-8650U / 16 GB RAM, and 7B replies took minutes). Do not pull 7B or larger models. Cloud optional.
- Ollama stores models in `C:\Users\Pc world\.ollama\models` (the Ollama app's own setting; the `OLLAMA_MODELS` env var is not used).
- UI: React + TypeScript + Vite

## Virtualenv
All Python packages installed in `D:\Temp\venv` (C drive was full).
Activate: `D:\Temp\venv\Scripts\activate`

## Commands
```bash
# Backend
D:\Temp\venv\Scripts\activate
cd D:\Temp\Agentica\backend
pip install -e ".[dev]"
pytest tests/

# UI
cd D:\Temp\Agentica\ui
npm install && npm run dev

# DB
docker compose -f D:\Temp\Agentica\infra\docker-compose.dev.yml up -d
D:\Temp\venv\Scripts\python -m alembic -c D:\Temp\Agentica\backend\alembic.ini upgrade head
```
