"""Retrieval evaluation: gold-labelled questions -> Recall@5, MRR, nDCG@5.

Each question is labelled with the SOP that answers it. A retrieved chunk is
relevant only if it comes from that document, so generic words ("service",
"disk") cannot score a hit by accident. Hybrid (dense + FTS + RRF) is compared
with dense-only.

Run (PostgreSQL up, eval/kb indexed):
    D:\\Temp\\venv\\Scripts\\python eval/retrieval_eval.py
Results are printed and written to eval/results/retrieval_latest.json.
"""

from __future__ import annotations

import asyncio
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

K = 5
DISK, MEM, IIS, NGINX, STOPPED = (
    "sop_full_disk.md", "sop_high_memory.md", "sop_iis_restart.md",
    "sop_nginx_restart.md", "sop_stopped_service.md",
)

# (question, gold document) — 10 per SOP, paraphrased rather than copied headings.
EVAL_QUESTIONS: list[tuple[str, str]] = [
    # full disk
    ("a partition is almost out of space, what should I do", DISK),
    ("at what usage percentage does a storage warning fire", DISK),
    ("how can I free up space quickly on a server volume", DISK),
    ("where should I look for big temporary files to delete", DISK),
    ("old application log archives older than a month", DISK),
    ("apt-get clean package cache to reclaim space", DISK),
    ("core dump files and database transaction logs taking space", DISK),
    ("long term fix so the volume stops filling up", DISK),
    ("when to escalate if storage stays above 85 percent", DISK),
    ("request disk expansion from the infrastructure team", DISK),
    # high memory
    ("server is running out of RAM", MEM),
    ("RAM usage critical threshold 95 percent", MEM),
    ("which processes are eating the most memory", MEM),
    ("heavy swap usage indicates memory pressure", MEM),
    ("a rogue process is consuming memory, how to respond", MEM),
    ("memory keeps growing slowly, possible leak", MEM),
    ("confirm memory went down after the fix and monitor for 15 minutes", MEM),
    ("set up alerts at 85% memory to prevent incidents", MEM),
    ("review application memory limits in configuration", MEM),
    ("inspect details of the top memory consumer process", MEM),
    # IIS
    ("restart the Windows web server W3SVC", IIS),
    ("Internet Information Services restart procedure", IIS),
    ("what does event ID 7031 mean", IIS),
    ("website returns HTTP 503 service unavailable", IIS),
    ("application pool is stopped while the web service runs", IIS),
    ("event id 1000 application error on windows", IIS),
    ("prerequisites for restarting IIS over WinRM", IIS),
    ("how long does an IIS restart take", IIS),
    ("verify IIS after restart using port 443 and the application event log", IIS),
    ("escalate application pool issue to the Windows Server team", IIS),
    # nginx
    ("nginx is not answering web requests", NGINX),
    ("validate nginx configuration before restarting", NGINX),
    ("nginx -t configuration test failed", NGINX),
    ("checklist before restarting the reverse proxy", NGINX),
    ("nginx will not start after restart", NGINX),
    ("port 80 already in use by another process when starting nginx", NGINX),
    ("ssl certificate expired prevents web server from starting", NGINX),
    ("apply configuration changes to nginx", NGINX),
    ("how long does an nginx restart interrupt traffic", NGINX),
    ("escalate to web infrastructure team after 15 minutes", NGINX),
    # stopped service
    ("a system service has stopped unexpectedly", STOPPED),
    ("diagnose why a daemon is not running", STOPPED),
    ("service binary missing or configuration syntax error", STOPPED),
    ("service fails to come back after a restart", STOPPED),
    ("escalate to level 2 support", STOPPED),
    ("restore last known good configuration", STOPPED),
    ("services often fail when the disk is full", STOPPED),
    ("note the last error message and timestamp from the journal", STOPPED),
    ("need sudo access to recover a stopped unit", STOPPED),
    ("check for port conflicts when a service won't start", STOPPED),
]


async def _run_hybrid(query: str, top_k: int = K) -> list[str]:
    from agentica.rag.search import hybrid_search
    results = await hybrid_search(query, top_k=top_k)
    return [r.document for r in results]


async def _run_dense_only(query: str, top_k: int = K) -> list[str]:
    from sqlalchemy import text as sql_text
    from agentica.db.engine import get_session_factory
    from agentica.rag.embed import embed_query

    q_emb = embed_query(query)
    async with get_session_factory()() as session:
        rows = (await session.execute(sql_text("""
            SELECT d.file_name
            FROM kb_chunks c JOIN kb_documents d ON d.id = c.document_id
            WHERE d.status = 'ok'
            ORDER BY c.embedding <=> CAST(:emb AS vector)
            LIMIT :k
        """), {"emb": str(q_emb), "k": top_k})).fetchall()
    return [r[0] for r in rows]


def first_hit_rank(retrieved: list[str], gold: str) -> int | None:
    for i, doc in enumerate(retrieved, start=1):
        if doc == gold:
            return i
    return None


def recall_at_k(retrieved: list[str], gold: str, k: int = K) -> float:
    r = first_hit_rank(retrieved[:k], gold)
    return 1.0 if r else 0.0


def mrr(retrieved: list[str], gold: str) -> float:
    r = first_hit_rank(retrieved, gold)
    return 1.0 / r if r else 0.0


def ndcg_at_k(retrieved: list[str], gold: str, k: int = K) -> float:
    """Binary relevance per chunk (chunk from the gold doc = 1), normalised by the ideal ranking."""
    rels = [1.0 if d == gold else 0.0 for d in retrieved[:k]]
    dcg = sum(rel / math.log2(i + 2) for i, rel in enumerate(rels))
    ideal = sorted(rels, reverse=True)
    idcg = sum(rel / math.log2(i + 2) for i, rel in enumerate(ideal)) or 1.0
    # A query with no relevant chunk retrieved scores 0 (idcg would otherwise be 0).
    return dcg / idcg if any(rels) else 0.0


async def evaluate(mode: str = "hybrid") -> dict:
    run = _run_hybrid if mode == "hybrid" else _run_dense_only
    recalls, mrrs, ndcgs, misses = [], [], [], []
    for query, gold in EVAL_QUESTIONS:
        retrieved = await run(query)
        recalls.append(recall_at_k(retrieved, gold))
        mrrs.append(mrr(retrieved, gold))
        ndcgs.append(ndcg_at_k(retrieved, gold))
        if not recalls[-1]:
            misses.append({"query": query, "gold": gold, "top5": retrieved[:K]})
    n = len(EVAL_QUESTIONS)
    return {
        "mode": mode,
        "num_queries": n,
        "recall_at_5": round(sum(recalls) / n, 3),
        "mrr": round(sum(mrrs) / n, 3),
        "ndcg_at_5": round(sum(ndcgs) / n, 3),
        "misses": misses,
    }


async def main() -> int:
    print(f"=== Retrieval Evaluation ({len(EVAL_QUESTIONS)} gold-labelled questions) ===")
    hybrid = await evaluate("hybrid")
    dense = await evaluate("dense")
    for r in (hybrid, dense):
        print(f"{r['mode']:>7}: Recall@5={r['recall_at_5']:.3f}  MRR={r['mrr']:.3f}  nDCG@5={r['ndcg_at_5']:.3f}"
              f"  misses={len(r['misses'])}")
    for m in hybrid["misses"]:
        print(f"  hybrid miss: {m['query']!r} (gold {m['gold']}) -> {m['top5']}")

    out = Path(__file__).parent / "results" / "retrieval_latest.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "hybrid": hybrid, "dense": dense,
    }, indent=2), encoding="utf-8")
    print(f"\nWrote {out}")

    ok = hybrid["recall_at_5"] >= 0.85
    print("PASS: hybrid Recall@5 >= 0.85" if ok else f"FAIL: hybrid Recall@5 {hybrid['recall_at_5']} < 0.85")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
