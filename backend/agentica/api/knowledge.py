"""Knowledge Base API — folder management, documents, re-index, search."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import text

from agentica.config.logging import get_logger
from agentica.db.engine import get_session_factory
from agentica.rag.ingest import ingest_file, ingest_folder, SUPPORTED_EXTENSIONS
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


@router.post("/knowledge/folder")
async def set_folder(body: SetFolderRequest) -> dict:
    global _watcher
    folder = Path(body.folder)
    if not folder.exists() or not folder.is_dir():
        raise HTTPException(status_code=400, detail=f"Folder not found: {body.folder}")

    # Update settings
    from agentica.config.loader import get_settings
    cfg = get_settings()

    # Stop previous watcher
    if _watcher:
        _watcher.stop()

    # Rescan
    docs = await ingest_folder(folder)

    # Start new watcher
    from agentica.rag.ingest import FolderWatcher
    _watcher = FolderWatcher(folder)
    _watcher.start()

    return {"folder": str(folder), "documents": len(docs)}


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
