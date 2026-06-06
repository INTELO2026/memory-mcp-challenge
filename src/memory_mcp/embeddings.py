"""Chargement paresseux du modèle d'embeddings (singleton partagé)."""

from __future__ import annotations

from sentence_transformers import SentenceTransformer

MODEL_NAME = "all-MiniLM-L6-v2"
EMBEDDING_DIM = 384

_model: SentenceTransformer | None = None


def get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        _model = SentenceTransformer(MODEL_NAME)
    return _model


def embed_text(text: str):
    """Vecteur normalisé L2 (float32) pour recherche cosine via produit scalaire."""
    import numpy as np

    vec = get_model().encode(text, normalize_embeddings=True)
    return vec.astype(np.float32)
