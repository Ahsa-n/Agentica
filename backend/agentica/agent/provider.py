"""LLM provider factory — Ollama (local) and Cloud (optional)."""

from __future__ import annotations

from functools import lru_cache

from agentica.config.loader import get_settings
from agentica.config.logging import get_logger

logger = get_logger(__name__)


def get_provider():
    """Return configured LLM client. Refuses cloud in local mode."""
    cfg = get_settings().llm
    if cfg.mode == "local":
        return _make_ollama(cfg)
    elif cfg.mode == "cloud":
        return _make_cloud(cfg)
    raise ValueError(f"Unknown LLM mode: {cfg.mode}")


def _make_ollama(cfg):
    from langchain_ollama import ChatOllama
    logger.info("llm_provider", type="ollama", model=cfg.local_model)
    return ChatOllama(
        model=cfg.local_model,
        base_url=cfg.ollama_base_url,
        num_ctx=cfg.num_ctx,
        temperature=cfg.temperature,
        keep_alive=cfg.keep_alive,
        num_predict=cfg.num_predict,
        repeat_penalty=cfg.repeat_penalty,
    )


def _make_cloud(cfg):
    from agentica.config.secrets import SecretsManager
    if cfg.mode == "local":
        raise RuntimeError("Cannot create cloud client in local mode — zero egress policy.")
    api_key = SecretsManager.get(f"cloud_api_key_{cfg.cloud_provider}")
    if not api_key:
        raise RuntimeError(f"No API key for cloud provider '{cfg.cloud_provider}' in keyring.")

    if cfg.cloud_provider == "openai":
        from langchain_openai import ChatOpenAI
        logger.info("llm_provider", type="openai", model=cfg.cloud_model)
        return ChatOpenAI(model=cfg.cloud_model, api_key=api_key)
    raise ValueError(f"Unknown cloud provider: {cfg.cloud_provider}")
