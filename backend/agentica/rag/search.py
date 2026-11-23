"""Hybrid search: dense (pgvector cosine) + keyword (FTS) → RRF fusion."""

from __future__ import annotations

from typing import TYPE_CHECKING

from agentica.config.loader import get_settings
from agentica.config.logging import get_logger
from agentica.tools.local.knowledge_tool import KBChunkResult

logger = get_logger(__name__)

RRF_K = 60


def _rrf_score(rank: int, k: int = RRF_K) -> float:
    return 1.0 / (k + rank)


async def hybrid_search(query: str, top_k: int = 5) -> list[KBChunkResult]:
    """Hybrid search combining dense and keyword retrieval with RRF."""
    from agentica.rag.embed import embed_query
    from agentica.db.engine import get_session_factory

    cfg = get_settings().rag
    threshold = cfg.similarity_threshold

    q_embedding = embed_query(query)

    async with get_session_factory()() as session:
        # 1. Dense retrieval (pgvector cosine similarity)
        dense_sql = """
            SELECT
                c.id::text,
                c.content,
                c.heading_path,
                d.file_name AS document,
                1 - (c.embedding <=> :embedding::vector) AS score
            FROM kb_chunks c
            JOIN kb_documents d ON d.id = c.document_id
            WHERE d.status = 'ok'
            ORDER BY c.embedding <=> :embedding::vector
            LIMIT :limit
        """
        from sqlalchemy import text as sql_text
        dense_rows = (await session.execute(
            sql_text(dense_sql),
            {"embedding": str(q_embedding), "limit": cfg.top_k_dense}
        )).fetchall()

        # 2. Keyword retrieval (FTS)
        keyword_sql = """
            SELECT
                c.id::text,
                c.content,
                c.heading_path,
                d.file_name AS document,
                ts_rank_cd(c.content_tsv, query) AS score
            FROM kb_chunks c
            JOIN kb_documents d ON d.id = c.document_id,
            websearch_to_tsquery('english', :query) query
            WHERE c.content_tsv @@ query
              AND d.status = 'ok'
            ORDER BY score DESC
            LIMIT :limit
        """
        keyword_rows = (await session.execute(
            sql_text(keyword_sql),
            {"query": query, "limit": cfg.top_k_keyword}
        )).fetchall()

    # 3. RRF fusion
    scores: dict[str, float] = {}
    data: dict[str, dict] = {}

    for rank, row in enumerate(dense_rows):
        rid = row[0]
        scores[rid] = scores.get(rid, 0.0) + _rrf_score(rank)
        data[rid] = {"content": row[1], "heading_path": row[2], "document": row[3], "dense_score": row[4]}

    for rank, row in enumerate(keyword_rows):
        rid = row[0]
        scores[rid] = scores.get(rid, 0.0) + _rrf_score(rank)
        if rid not in data:
            data[rid] = {"content": row[1], "heading_path": row[2], "document": row[3], "dense_score": 0.0}

    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top_k]

    results = []
    for rid, rrf_score in ranked:
        d = data[rid]
        if d["dense_score"] >= threshold or rrf_score > 0:
            results.append(KBChunkResult(
                document=d["document"],
                heading_path=d.get("heading_path"),
                content=d["content"][:1000],
                score=round(rrf_score, 4),
            ))

    if not results:
        logger.info("kb_search_not_found", query=query)

    return results
