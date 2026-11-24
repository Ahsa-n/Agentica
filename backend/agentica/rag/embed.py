"""Embedding model loader — sentence-transformers, local path."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from agentica.config.logging import get_logger

logger = get_logger(__name__)

MODEL_ID = "intfloat/multilingual-e5-base"
EMBEDDING_DIM = 768

_WEIGHT_FILES = ("model.safetensors", "pytorch_model.bin")


def _has_weights(snap_dir: Path) -> bool:
    """A snapshot is only usable if it actually contains model weights.

    An interrupted download can leave a snapshot with config/tokenizer files
    but no weights; loading that fails with "no file named model.safetensors".
    """
    return any((snap_dir / f).is_file() for f in _WEIGHT_FILES)


def _find_local_snapshot(model_id: str) -> Path | None:
    """
    Locate the cached snapshot directory for a HuggingFace model ID.
    Searches both HF_HOME/hub and SENTENCE_TRANSFORMERS_HOME since
    sentence-transformers uses a separate cache root. Snapshots without
    weight files (partial downloads) are skipped.
    """
    model_slug = "models--" + model_id.replace("/", "--")

    roots: list[Path] = []
    if hf_home := os.environ.get("HF_HOME"):
        roots.append(Path(hf_home) / "hub")
        roots.append(Path(hf_home) / "sentence-transformers")
    if st_home := os.environ.get("SENTENCE_TRANSFORMERS_HOME"):
        roots.append(Path(st_home))
    # Default HF cache
    roots.append(Path.home() / ".cache" / "huggingface" / "hub")

    for root in roots:
        model_dir = root / model_slug
        if not model_dir.exists():
            continue
        # Prefer the pinned ref (refs/main)
        refs_main = model_dir / "refs" / "main"
        if refs_main.exists():
            snap_hash = refs_main.read_text(encoding="utf-8").strip()
            snap_dir = model_dir / "snapshots" / snap_hash
            if snap_dir.is_dir() and _has_weights(snap_dir):
                return snap_dir
        # Fallback: take any snapshot that has weights
        snapshots_dir = model_dir / "snapshots"
        if snapshots_dir.exists():
            for snap in sorted(snapshots_dir.iterdir()):
                if snap.is_dir() and _has_weights(snap):
                    return snap

    return None


@lru_cache(maxsize=1)
def get_embedding_model():
    from sentence_transformers import SentenceTransformer

    from agentica.config.loader import get_settings

    cfg = get_settings()
    model_path: str = cfg.rag.embedding_model_path or MODEL_ID

    # Resolve to a local snapshot path so we never need a network call
    if model_path == MODEL_ID:
        local = _find_local_snapshot(MODEL_ID)
        if local:
            os.environ["HF_HUB_OFFLINE"] = "1"
            os.environ["TRANSFORMERS_OFFLINE"] = "1"
            model_path = str(local)
            logger.info("embedding_model_local", path=model_path)
        else:
            logger.warning("embedding_model_not_cached", model=MODEL_ID)

    model = SentenceTransformer(model_path)
    return model


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed a list of texts. Prefix with 'passage: ' for e5 models."""
    model = get_embedding_model()
    prefixed = [f"passage: {t}" for t in texts]
    embeddings = model.encode(prefixed, normalize_embeddings=True)
    return embeddings.tolist()


def embed_query(query: str) -> list[float]:
    """Embed a query. Prefix with 'query: ' for e5 models."""
    model = get_embedding_model()
    embedding = model.encode(f"query: {query}", normalize_embeddings=True)
    return embedding.tolist()
