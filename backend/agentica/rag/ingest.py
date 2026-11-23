"""Document ingestion — SHA-256 dedup, atomic replace, folder watcher."""

from __future__ import annotations

import asyncio
import hashlib
import uuid
from pathlib import Path

from sqlalchemy import text as sql_text

from agentica.config.logging import get_logger
from agentica.db.engine import get_session_factory
from agentica.db.models import KBDocument, KBChunk
from agentica.rag.chunk import chunk_document
from agentica.rag.embed import embed_texts
from agentica.rag.extract import extract_text, ExtractionError

logger = get_logger(__name__)

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".doc", ".html", ".htm", ".md", ".markdown", ".txt"}


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(65536), b""):
            h.update(block)
    return h.hexdigest()


async def ingest_file(path: Path) -> KBDocument:
    """Ingest or re-index a single file. Atomic: delete old chunks before inserting new."""
    factory = get_session_factory()

    sha = _sha256(path)
    file_path_str = str(path.resolve())

    async with factory() as session:
        # Check if already indexed with same SHA
        existing = (await session.execute(
            sql_text("SELECT id, sha256, status FROM kb_documents WHERE file_path = :fp"),
            {"fp": file_path_str}
        )).fetchone()

        if existing and existing[1] == sha and existing[2] == "ok":
            logger.info("kb_skip_unchanged", file=path.name)
            # Return existing document
            doc = await session.get(KBDocument, uuid.UUID(str(existing[0])))
            return doc

        # Extract text
        try:
            text = extract_text(path)
            status = "ok"
            error_msg = None
        except ExtractionError as e:
            text = ""
            status = "failed"
            error_msg = str(e)

        # Chunk and embed
        chunks = []
        embeddings = []
        if text:
            chunks = chunk_document(text)
            if chunks:
                texts = [c.content for c in chunks]
                embeddings = embed_texts(texts)

        # Atomic replace in one transaction
        if existing:
            doc_id = uuid.UUID(str(existing[0]))
            await session.execute(
                sql_text("DELETE FROM kb_chunks WHERE document_id = :id"),
                {"id": str(doc_id)}
            )
            await session.execute(
                sql_text("""
                    UPDATE kb_documents
                    SET sha256=:sha, status=:status, error_message=:err,
                        chunk_count=:cc, file_name=:fn, mime_type=:mt, updated_at=NOW()
                    WHERE id=:id
                """),
                {"sha": sha, "status": status, "err": error_msg,
                 "cc": len(chunks), "fn": path.name, "mt": _mime(path), "id": str(doc_id)}
            )
        else:
            doc_id = uuid.uuid4()
            await session.execute(
                sql_text("""
                    INSERT INTO kb_documents (id, file_path, file_name, sha256, mime_type, status, error_message, chunk_count)
                    VALUES (:id, :fp, :fn, :sha, :mt, :status, :err, :cc)
                """),
                {"id": str(doc_id), "fp": file_path_str, "fn": path.name, "sha": sha,
                 "mt": _mime(path), "status": status, "err": error_msg, "cc": len(chunks)}
            )

        for i, (chunk, emb) in enumerate(zip(chunks, embeddings)):
            await session.execute(
                sql_text("""
                    INSERT INTO kb_chunks (id, document_id, chunk_index, heading_path, content, token_count, embedding)
                    VALUES (:id, :doc_id, :idx, :hp, :content, :tc, :emb::vector)
                """),
                {
                    "id": str(uuid.uuid4()),
                    "doc_id": str(doc_id),
                    "idx": i,
                    "hp": chunk.heading_path,
                    "content": chunk.content,
                    "tc": chunk.token_count,
                    "emb": str(emb),
                }
            )

        await session.commit()
        logger.info("kb_ingested", file=path.name, chunks=len(chunks), status=status)

        result = await session.get(KBDocument, doc_id)
        return result


async def ingest_folder(folder: Path) -> list[KBDocument]:
    """Ingest all supported files in a folder."""
    docs = []
    for path in sorted(folder.rglob("*")):
        if path.suffix.lower() in SUPPORTED_EXTENSIONS and path.is_file():
            # Skip temp files
            if path.name.startswith(".") or path.name.startswith("~"):
                continue
            try:
                doc = await ingest_file(path)
                docs.append(doc)
            except Exception as e:
                logger.error("kb_ingest_error", file=str(path), error=str(e))
    return docs


def _mime(path: Path) -> str:
    ext_map = {
        ".pdf": "application/pdf",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".doc": "application/msword",
        ".html": "text/html",
        ".htm": "text/html",
        ".md": "text/markdown",
        ".txt": "text/plain",
    }
    return ext_map.get(path.suffix.lower(), "application/octet-stream")


class FolderWatcher:
    """Watch a folder for changes and re-index on modifications."""

    def __init__(self, folder: Path) -> None:
        self.folder = folder
        self._observer = None

    def start(self) -> None:
        from watchdog.observers import Observer
        from watchdog.events import FileSystemEventHandler

        class Handler(FileSystemEventHandler):
            def __init__(self, loop):
                self._loop = loop
                self._pending: set[Path] = set()
                self._task = None

            def _schedule(self, path: str) -> None:
                p = Path(path)
                if p.suffix.lower() not in SUPPORTED_EXTENSIONS:
                    return
                if p.name.startswith(".") or p.name.startswith("~"):
                    return
                self._pending.add(p)
                if self._task is None or self._task.done():
                    self._task = asyncio.run_coroutine_threadsafe(self._debounce(), self._loop)

            async def _debounce(self) -> None:
                await asyncio.sleep(2.0)  # 2s debounce
                for p in list(self._pending):
                    self._pending.discard(p)
                    try:
                        await ingest_file(p)
                    except Exception as e:
                        logger.error("watcher_ingest_error", file=str(p), error=str(e))

            def on_created(self, event):
                if not event.is_directory:
                    self._schedule(event.src_path)

            def on_modified(self, event):
                if not event.is_directory:
                    self._schedule(event.src_path)

        loop = asyncio.get_event_loop()
        self._observer = Observer()
        self._observer.schedule(Handler(loop), str(self.folder), recursive=True)
        self._observer.start()
        logger.info("folder_watcher_started", folder=str(self.folder))

    def stop(self) -> None:
        if self._observer:
            self._observer.stop()
            self._observer.join()
