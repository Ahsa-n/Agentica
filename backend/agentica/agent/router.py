"""Two-stage embedding router.

Stage 1: embed the user query and compute cosine similarity against
         category prototype embeddings.
Stage 2: select top category + any within a margin (up to 3 total).
         If best score is below no_tool_threshold → conversational, no tools.
"""

from __future__ import annotations

from pathlib import Path
from typing import NamedTuple

import numpy as np
import yaml

from agentica.config.logging import get_logger
from agentica.tools.base import ToolCategory

logger = get_logger(__name__)

_CATEGORIES_PATH = Path(__file__).parents[3] / "config" / "router" / "categories.yaml"
_MARGIN = 0.08
_NO_TOOL_THRESHOLD = 0.30
_MAX_CATEGORIES = 3

# Always available regardless of routing
_ALWAYS_AVAILABLE = {"get_system_overview"}


class RoutingResult(NamedTuple):
    categories: list[ToolCategory]
    scores: dict[str, float]
    conversational: bool


class EmbeddingRouter:
    def __init__(self) -> None:
        self._model = None
        self._category_embeddings: dict[str, np.ndarray] = {}
        self._loaded = False

    def _load(self) -> None:
        if self._loaded:
            return
        from sentence_transformers import SentenceTransformer

        from agentica.config.loader import get_settings
        cfg = get_settings().rag
        model_path = cfg.embedding_model_path or "intfloat/multilingual-e5-base"
        self._model = SentenceTransformer(model_path)

        data = yaml.safe_load(_CATEGORIES_PATH.read_text(encoding="utf-8"))
        cats = data.get("categories", {})
        for cat_name, cat_data in cats.items():
            examples = cat_data.get("examples", [])
            if examples:
                embeddings = self._model.encode(
                    [f"query: {e}" for e in examples],
                    normalize_embeddings=True,
                )
                self._category_embeddings[cat_name] = embeddings.mean(axis=0)
        self._loaded = True
        logger.info("router_loaded", categories=list(self._category_embeddings.keys()))

    def route(
        self, query: str, force_categories: list[str] | None = None
    ) -> RoutingResult:
        self._load()
        q_emb = self._model.encode(f"query: {query}", normalize_embeddings=True)

        scores: dict[str, float] = {}
        for cat, emb in self._category_embeddings.items():
            scores[cat] = float(np.dot(q_emb, emb))

        sorted_cats = sorted(scores, key=lambda c: scores[c], reverse=True)
        best_score = scores[sorted_cats[0]] if sorted_cats else 0.0

        if best_score < _NO_TOOL_THRESHOLD and not force_categories:
            return RoutingResult(categories=[], scores=scores, conversational=True)

        selected = [sorted_cats[0]]
        for c in sorted_cats[1:_MAX_CATEGORIES]:
            if scores[c] >= best_score - _MARGIN:
                selected.append(c)
            else:
                break

        if force_categories:
            for fc in force_categories:
                if fc not in selected:
                    selected.append(fc)

        cats = []
        for c in selected:
            try:
                cats.append(ToolCategory(c))
            except ValueError:
                pass

        return RoutingResult(categories=cats, scores=scores, conversational=False)


_router_instance: EmbeddingRouter | None = None


def get_router() -> EmbeddingRouter:
    global _router_instance
    if _router_instance is None:
        _router_instance = EmbeddingRouter()
    return _router_instance
