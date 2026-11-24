"""Config loader — Pydantic-validated YAML, OS config dir, safe defaults."""

from __future__ import annotations

import re
import shutil
from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml
from platformdirs import user_config_dir
from pydantic import BaseModel, field_validator, model_validator

# Matches config keys that look like secrets — requires word-part boundaries
# (underscore or string start/end) so "chunk_size_tokens" is not flagged.
_SECRET_PATTERN = re.compile(
    r"(?:^|_)(?:password|secret|token|key|credential|private|passwd)(?:_|$)",
    re.IGNORECASE,
)

DEFAULTS_DIR = Path(__file__).parent.parent.parent.parent / "config" / "defaults"
CONFIG_DIR = Path(user_config_dir("agentica", "ATCO"))


class AppConfig(BaseModel):
    name: str = "Agentica"
    version: str = "0.1.0"
    host: str = "127.0.0.1"
    port: int = 8765
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"


class LLMConfig(BaseModel):
    mode: Literal["local", "cloud"] = "local"
    local_model: str = "qwen2.5:3b-instruct"  # project model; 7B is too slow on the CPU-only dev laptop
    ollama_base_url: str = "http://localhost:11434"
    num_ctx: int = 8192
    temperature: float = 0.1
    # How long Ollama keeps the model in RAM after a request. Reloading a model on a
    # memory-starved CPU-only machine took ~170 s, so keep it warm between chats.
    keep_alive: str = "30m"
    # Send the same full tool list on every call so Ollama can reuse its cached prompt
    # prefix (system prompt + tools). Routing then becomes a hint on the user turn.
    # On a CPU-only host this cuts each call from ~70 s to ~10-20 s.
    stable_tool_prompt: bool = True
    # Hard cap on tokens per model reply. Small models occasionally fall into a
    # repetition loop; without a cap one reply ran for 10+ minutes on this CPU.
    num_predict: int = 512
    repeat_penalty: float = 1.1
    cloud_provider: str | None = None
    cloud_model: str | None = None

    @model_validator(mode="after")
    def cloud_needs_provider(self) -> LLMConfig:
        if self.mode == "cloud" and not self.cloud_provider:
            raise ValueError("cloud_provider required when mode=cloud")
        return self


class AgentConfig(BaseModel):
    max_steps: int = 10
    max_validation_retries: int = 2
    max_denies_per_turn: int = 2
    routing_mode: Literal["routed", "flat"] = "routed"


class RAGConfig(BaseModel):
    kb_folder: str | None = None
    chunk_size_tokens: int = 400
    chunk_overlap_tokens: int = 50
    top_k_dense: int = 50
    top_k_keyword: int = 50
    rrf_k: int = 60
    similarity_threshold: float = 0.35
    embedding_model_path: str | None = None


class DBConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = 5432
    name: str = "agentica"
    user: str = "agentica"


class Settings(BaseModel):
    app: AppConfig = AppConfig()
    llm: LLMConfig = LLMConfig()
    agent: AgentConfig = AgentConfig()
    rag: RAGConfig = RAGConfig()
    db: DBConfig = DBConfig()

    @field_validator("*", mode="before")
    @classmethod
    def reject_secrets_at_top(cls, v: object, info: object) -> object:
        return v

    model_config = {"extra": "ignore"}


def _ensure_config_dir() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    for src in DEFAULTS_DIR.glob("*.yaml"):
        dst = CONFIG_DIR / src.name
        if not dst.exists():
            shutil.copy(src, dst)


def _check_no_secrets(data: dict, path: str = "") -> None:
    """Raise ValueError if any key looks like a secret."""
    for k, v in data.items():
        full = f"{path}.{k}" if path else k
        if _SECRET_PATTERN.search(str(k)):
            raise ValueError(
                f"Config key '{full}' looks like a secret. "
                "Store secrets in the OS keyring, not config files."
            )
        if isinstance(v, dict):
            _check_no_secrets(v, full)


def load_settings() -> Settings:
    _ensure_config_dir()
    settings_path = CONFIG_DIR / "settings.yaml"
    raw: dict = {}
    if settings_path.exists():
        raw = yaml.safe_load(settings_path.read_text(encoding="utf-8")) or {}
    _check_no_secrets(raw)
    return Settings.model_validate(raw)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return load_settings()
