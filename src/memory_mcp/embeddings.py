"""Embeddings sémantiques via sentence-transformers (multilingue)."""

from __future__ import annotations

from functools import lru_cache

_MODEL_NAME = "paraphrase-multilingual-mpnet-base-v2"


@lru_cache(maxsize=1)
def _get_model():
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(_MODEL_NAME)


def embed(text: str) -> list[float]:
    """Vecteur dense normalisé pour similarité cosinus."""
    if not text.strip():
        return []
    vector = _get_model().encode(text, normalize_embeddings=True)
    return vector.tolist()


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    return sum(x * y for x, y in zip(a, b, strict=True))


def is_near_duplicate(a: str, b: str, threshold: float = 0.92) -> bool:
    """Détecte deux contenus sémantiquement redondants."""
    if not a.strip() or not b.strip():
        return False
    if a.strip() == b.strip():
        return True
    return cosine_similarity(embed(a), embed(b)) >= threshold
