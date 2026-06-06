"""Embeddings sémantiques via sentence-transformers (all-MiniLM-L6-v2)."""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer

_MODEL: SentenceTransformer | None = None
_LOCK = threading.Lock()
_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"


def get_model() -> SentenceTransformer:
    """Charge le modèle une seule fois (lazy singleton)."""
    global _MODEL
    if _MODEL is None:
        with _LOCK:
            if _MODEL is None:
                from sentence_transformers import SentenceTransformer

                _MODEL = SentenceTransformer(_MODEL_NAME)
    return _MODEL


def encode(text: str) -> np.ndarray:
    """Vecteur embedding normalisé ℝ^384."""
    import unicodedata

    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c)).lower().strip()
    vec = get_model().encode(text, normalize_embeddings=True, show_progress_bar=False)
    return np.asarray(vec, dtype=np.float32)


def serialize(vec: np.ndarray) -> bytes:
    return vec.astype(np.float32).tobytes()


def deserialize(data: bytes) -> np.ndarray:
    return np.frombuffer(data, dtype=np.float32).copy()


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    if a.size == 0 or b.size == 0:
        return 0.0
    return float(np.dot(a, b))
