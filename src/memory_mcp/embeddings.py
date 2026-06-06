"""Modèle d'embeddings sémantiques (sentence-transformers, chargement paresseux)."""

from __future__ import annotations

import math
import os
from functools import lru_cache

MODEL_NAME = os.environ.get(
    "MEMBRIDGE_EMBED_MODEL",
    "paraphrase-multilingual-MiniLM-L12-v2",
)


@lru_cache(maxsize=1)
def _get_model():
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(MODEL_NAME)


def embed_text(text: str) -> list[float]:
    """Vecteur dense normalisé pour une phrase."""
    model = _get_model()
    vector = model.encode(text, normalize_embeddings=True)
    return vector.tolist()


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)
