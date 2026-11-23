"""Embedding model loader — sentence-transformers, local path."""

from __future__ import annotations

from functools import lru_cache

from agentica.config.logging import get_logger

logger = get_logger(__name__)

MODEL_ID = "intfloat/multilingual-e5-base"
EMBEDDING_DIM = 768


@lru_cache(maxsize=1)
def get_embedding_model():
    from sentence_transformers import SentenceTransformer
    from agentica.config.loader import get_settings

    cfg = get_settings()
    model_path = cfg.rag.embedding_model_path or MODEL_ID

    # In local mode, force offline only after the model is already cached
    if cfg.llm.mode == "local":
        import os
        from pathlib import Path
        hf_home = Path(os.environ.get("HF_HOME", Path.home() / ".cache" / "huggingface"))
        model_slug = MODEL_ID.replace("/", "--")
        cached = (hf_home / "hub" / f"models--{model_slug}").exists()
        if cached:
            os.environ.setdefault("HF_HUB_OFFLINE", "1")
            os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

    logger.info("loading_embedding_model", path=model_path)
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
