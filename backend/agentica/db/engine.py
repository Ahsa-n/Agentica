"""SQLAlchemy engine factory — sync for Alembic, async for FastAPI."""

from __future__ import annotations

from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from agentica.config.loader import get_settings
from agentica.config.secrets import SecretsManager


def get_dsn(async_: bool = False) -> str:
    cfg = get_settings().db
    password = SecretsManager.get("db_password") or "agentica"
    driver = "postgresql+psycopg" if async_ else "postgresql+psycopg"
    return f"{driver}://{cfg.user}:{password}@{cfg.host}:{cfg.port}/{cfg.name}"


@lru_cache(maxsize=1)
def get_engine():
    return create_engine(get_dsn(async_=False), pool_pre_ping=True)


@lru_cache(maxsize=1)
def get_async_engine():
    return create_async_engine(get_dsn(async_=True), pool_pre_ping=True)


@lru_cache(maxsize=1)
def get_session_factory() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(get_async_engine(), expire_on_commit=False)
