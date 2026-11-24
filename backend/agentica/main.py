"""FastAPI application entry point."""

from __future__ import annotations

import asyncio
import secrets
import sys
from contextlib import asynccontextmanager

# psycopg3 async requires SelectorEventLoop on Windows (ProactorEventLoop is the default)
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from agentica.config.loader import get_settings
from agentica.config.logging import configure_logging, get_logger
from agentica.config.secrets import SecretsManager

logger = get_logger(__name__)

# Generate a per-launch bearer token stored in keyring
def _init_token() -> str:
    token = SecretsManager.get("launch_token")
    if not token:
        token = secrets.token_urlsafe(32)
        SecretsManager.set("launch_token", token)
    return token


LAUNCH_TOKEN: str = ""


@asynccontextmanager
async def lifespan(app: FastAPI):
    global LAUNCH_TOKEN
    cfg = get_settings()
    configure_logging(cfg.app.log_level)
    if cfg.llm.mode == "local":
        # Zero egress: HF/transformers offline, tracing off; HTTP checks go through check_egress.
        from agentica.config.egress_guard import enforce_local_mode
        enforce_local_mode()
    LAUNCH_TOKEN = _init_token()
    logger.info("agentica_started", port=cfg.app.port, mode=cfg.llm.mode)

    # Resume the knowledge-base folder watcher + rescan without blocking startup.
    from agentica.api.knowledge import resume_knowledge_base, stop_watcher
    kb_task = asyncio.create_task(resume_knowledge_base())
    yield
    kb_task.cancel()
    stop_watcher()
    logger.info("agentica_stopped")


app = FastAPI(title="Agentica", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_bearer = HTTPBearer(auto_error=False)


async def require_auth(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> None:
    if not credentials or not secrets.compare_digest(credentials.credentials, LAUNCH_TOKEN):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")


# --- Routers (imported after app is created to avoid circular imports) ---
from agentica.api import knowledge, machines, sessions  # noqa: E402

app.include_router(sessions.router, prefix="/api", dependencies=[Depends(require_auth)])
app.include_router(knowledge.router, prefix="/api", dependencies=[Depends(require_auth)])
app.include_router(machines.router, prefix="/api", dependencies=[Depends(require_auth)])


@app.get("/api/health")
async def health() -> dict:
    cfg = get_settings().llm
    model = cfg.local_model if cfg.mode == "local" else (cfg.cloud_model or cfg.cloud_provider)
    return {"status": "ok", "version": "0.1.0", "mode": cfg.mode, "model": model}


@app.get("/api/token")
async def get_token() -> dict:
    """Return launch token (called once from the UI on startup)."""
    return {"token": LAUNCH_TOKEN}
