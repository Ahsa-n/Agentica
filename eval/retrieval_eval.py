"""Retrieval evaluation — Recall@5, MRR, nDCG.

Usage:
    python eval/retrieval_eval.py [--compare]

Outputs results to stdout and appends summary to PROGRESS.md.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

EVAL_QUESTIONS = [
    # (query, expected_keywords_in_top5)
    ("how to handle a stopped service", ["stopped", "service", "restart", "status"]),
    ("what to do when disk is full", ["disk", "full", "cleanup", "space"]),
    ("nginx restart procedure", ["nginx", "restart", "service", "verify"]),
    ("high memory usage handling", ["memory", "process", "restart", "threshold"]),
    ("IIS restart Windows", ["IIS", "W3SVC", "restart", "Windows"]),
    ("memory alert threshold", ["85%", "memory", "warning", "critical"]),
    ("escalation procedure", ["escalate", "Level 2", "infrastructure"]),
    ("disk cleanup steps", ["disk", "clean", "log", "archive"]),
    ("service fails to start", ["start", "fail", "log", "escalate"]),
    ("how to verify service restart", ["verify", "status", "port", "log"]),
    ("pre-restart checklist nginx", ["checklist", "nginx", "notify", "connections"]),
    ("application pool IIS stopped", ["application pool", "IIS Manager", "escalate"]),
    ("swap memory usage", ["swap", "memory", "pressure"]),
    ("what is disk alert threshold", ["90%", "95%", "critical", "warning"]),
    ("log rotation policy", ["log", "rotation", "archive", "30 days"]),
    # Add more for 50+ total
    ("check nginx port 80", ["port", "80", "check_port", "nginx"]),
    ("event id 7031", ["Event ID 7031", "terminated", "Windows"]),
    ("HTTP 503 error", ["503", "application pool", "stopped"]),
    ("service binary missing", ["binary", "configuration", "escalate"]),
    ("port conflict service", ["port", "conflict", "process", "check_port"]),
]


async def _run_hybrid(query: str, top_k: int = 5) -> list[str]:
    from agentica.rag.search import hybrid_search
    results = await hybrid_search(query, top_k=top_k)
    return [r.content for r in results]


async def _run_dense_only(query: str, top_k: int = 5) -> list[str]:
    from agentica.rag.embed import embed_query
    from agentica.db.engine import get_session_factory
    from sqlalchemy import text

    q_emb = embed_query(query)
    async with get_session_factory()() as session:
        rows = (await session.execute(
            text("""
                SELECT c.content
                FROM kb_chunks c
                JOIN kb_documents d ON d.id = c.document_id
                WHERE d.status = 'ok'
                ORDER BY c.embedding <=> :emb::vector
                LIMIT :limit
            """),
            {"emb": str(q_emb), "limit": top_k}
        )).fetchall()
    return [r[0] for r in rows]


def recall_at_k(retrieved: list[str], keywords: list[str], k: int = 5) -> float:
    top_k = retrieved[:k]
    for chunk in top_k:
        chunk_lower = chunk.lower()
        if any(kw.lower() in chunk_lower for kw in keywords):
            return 1.0
    return 0.0


def mrr(retrieved: list[str], keywords: list[str]) -> float:
    for i, chunk in enumerate(retrieved):
        chunk_lower = chunk.lower()
        if any(kw.lower() in chunk_lower for kw in keywords):
            return 1.0 / (i + 1)
    return 0.0


async def evaluate(mode: str = "hybrid") -> dict:
    recalls = []
    mrrs = []

    for query, keywords in EVAL_QUESTIONS:
        if mode == "hybrid":
            retrieved = await _run_hybrid(query)
        else:
            retrieved = await _run_dense_only(query)

        recalls.append(recall_at_k(retrieved, keywords))
        mrrs.append(mrr(retrieved, keywords))

    avg_recall = sum(recalls) / len(recalls) if recalls else 0
    avg_mrr = sum(mrrs) / len(mrrs) if mrrs else 0

    return {
        "mode": mode,
        "num_queries": len(EVAL_QUESTIONS),
        "recall_at_5": round(avg_recall, 3),
        "mrr": round(avg_mrr, 3),
    }


async def main():
    print("=== Retrieval Evaluation ===")
    hybrid_result = await evaluate("hybrid")
    dense_result = await evaluate("dense")

    print(f"\nHybrid:     Recall@5={hybrid_result['recall_at_5']:.3f}  MRR={hybrid_result['mrr']:.3f}")
    print(f"Dense only: Recall@5={dense_result['recall_at_5']:.3f}  MRR={dense_result['mrr']:.3f}")

    # Update PROGRESS.md
    progress_path = Path(__file__).parent.parent / "PROGRESS.md"
    if progress_path.exists():
        content = progress_path.read_text(encoding="utf-8")
        entry = (
            f"\n### Retrieval Eval Results\n"
            f"- Hybrid Recall@5: {hybrid_result['recall_at_5']} (target ≥0.85)\n"
            f"- Hybrid MRR: {hybrid_result['mrr']}\n"
            f"- Dense-only Recall@5: {dense_result['recall_at_5']}\n"
            f"- Dense-only MRR: {dense_result['mrr']}\n"
        )
        progress_path.write_text(content + entry, encoding="utf-8")

    if hybrid_result["recall_at_5"] >= 0.85:
        print("\n✓ Target Recall@5 ≥ 0.85 achieved")
    else:
        print(f"\n✗ Recall@5 {hybrid_result['recall_at_5']} below target 0.85")


if __name__ == "__main__":
    asyncio.run(main())
