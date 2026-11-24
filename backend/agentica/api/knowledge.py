"""Knowledge Base API — folder management, documents, re-index, search."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import text

from agentica.config.logging import get_logger
from agentica.db.engine import get_session_factory
from agentica.rag.ingest import ingest_file, ingest_folder
from agentica.rag.search import hybrid_search

router = APIRouter()
logger = get_logger(__name__)

_watcher = None


class SetFolderRequest(BaseModel):
    folder: str


class SearchRequest(BaseModel):
    query: str
    top_k: int = 5


@router.get("/knowledge/documents")
async def list_documents() -> list[dict]:
    async with get_session_factory()() as session:
        rows = (await session.execute(
            text("""
                SELECT id, file_name, file_path, status, error_message, chunk_count, updated_at
                FROM kb_documents ORDER BY updated_at DESC
            """)
        )).fetchall()
        return [
            {
                "id": str(r[0]),
                "file_name": r[1],
                "file_path": r[2],
                "status": r[3],
                "error_message": r[4],
                "chunk_count": r[5],
                "updated_at": r[6].isoformat() if r[6] else None,
            }
            for r in rows
        ]


_KB_FOLDER_KEY = "kb_folder"


async def _get_setting(key: str) -> str | None:
    async with get_session_factory()() as session:
        row = (await session.execute(
            text("SELECT value FROM app_settings WHERE key = :k"), {"k": key}
        )).fetchone()
        return row[0] if row else None


async def _set_setting(key: str, value: str) -> None:
    async with get_session_factory()() as session:
        await session.execute(
            text(
                "INSERT INTO app_settings (key, value, updated_at) VALUES (:k, :v, now()) "
                "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()"
            ),
            {"k": key, "v": value},
        )
        await session.commit()


def _start_watcher(folder: Path) -> None:
    global _watcher
    from agentica.rag.ingest import FolderWatcher
    if _watcher:
        _watcher.stop()
    _watcher = FolderWatcher(folder)
    _watcher.start()


async def resume_knowledge_base() -> None:
    """On startup: re-attach the watcher to the saved KB folder and rescan it.

    The rescan picks up files changed while Agentica was not running and removes
    documents whose files were deleted (stale content is cleared automatically).
    """
    try:
        saved = await _get_setting(_KB_FOLDER_KEY)
    except Exception as e:
        logger.warning("kb_resume_failed", error=str(e))
        return
    if not saved or not Path(saved).is_dir():
        return
    folder = Path(saved)
    _start_watcher(folder)
    docs = await ingest_folder(folder)
    logger.info("kb_resumed", folder=saved, documents=len(docs))


def stop_watcher() -> None:
    global _watcher
    if _watcher:
        _watcher.stop()
        _watcher = None


@router.get("/knowledge/folder")
async def get_folder() -> dict:
    saved = await _get_setting(_KB_FOLDER_KEY)
    return {"folder": saved, "watching": _watcher is not None}


@router.post("/knowledge/folder")
async def set_folder(body: SetFolderRequest) -> dict:
    folder = Path(body.folder)
    if not folder.exists() or not folder.is_dir():
        raise HTTPException(status_code=400, detail=f"Folder not found: {body.folder}")
    folder = folder.resolve()

    docs = await ingest_folder(folder)
    _start_watcher(folder)
    await _set_setting(_KB_FOLDER_KEY, str(folder))

    return {"folder": str(folder), "documents": len(docs), "watching": True}


@router.post("/knowledge/documents/{doc_id}/reindex")
async def reindex_document(doc_id: str) -> dict:
    async with get_session_factory()() as session:
        row = (await session.execute(
            text("SELECT file_path FROM kb_documents WHERE id = :id"),
            {"id": doc_id}
        )).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Document not found")
        file_path = Path(row[0])

    doc = await ingest_file(file_path)
    return {"id": str(doc.id), "status": doc.status, "chunk_count": doc.chunk_count}


@router.delete("/knowledge/documents/{doc_id}")
async def remove_document(doc_id: str) -> dict:
    async with get_session_factory()() as session:
        await session.execute(
            text("DELETE FROM kb_documents WHERE id = :id"),
            {"id": doc_id}
        )
        await session.commit()
    return {"ok": True}


@router.post("/knowledge/search")
async def search_knowledge(body: SearchRequest) -> dict:
    results = await hybrid_search(body.query, top_k=body.top_k)
    return {
        "query": body.query,
        "results": [r.model_dump() for r in results],
        "found": bool(results),
    }
