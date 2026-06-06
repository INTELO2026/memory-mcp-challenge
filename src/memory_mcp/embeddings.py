"""Couche d'embeddings sémantiques.

Trois backends, choisis automatiquement dans cet ordre :

1. **Gemini** (``gemini-embedding-001``) — backend principal demandé pour la démo.
   Activé dès qu'une clé ``GEMINI_API_KEY`` / ``GOOGLE_API_KEY`` est disponible.
2. **Local** (``sentence-transformers`` / ``intfloat/multilingual-e5-small``) —
   fallback hors-ligne pour la CI (régression + finale) qui ne possède pas la clé.
3. **Lexical de secours** — hachage de tokens, déterministe, sans dépendance ;
   évite tout crash si ni clé ni modèle local ne sont présents.

Les vecteurs sont toujours L2-normalisés : la similarité cosinus se réduit donc à
un simple produit scalaire.
"""

from __future__ import annotations

import hashlib
import os
import re
import threading
from pathlib import Path

import numpy as np

# Dimension du backend lexical de secours (sans modèle).
_FALLBACK_DIM = 384

_ROOT = Path(__file__).resolve().parents[2]
_TOKEN_RE = re.compile(r"\w+", re.UNICODE)


def _load_dotenv() -> None:
    """Charge un éventuel fichier .env à la racine (sans dépendance externe)."""
    env_path = _ROOT / ".env"
    if not env_path.exists():
        return
    # utf-8-sig : tolère un éventuel BOM en tête de fichier (.env écrit sous Windows).
    for raw in env_path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _api_key() -> str | None:
    return os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")


def _l2_normalize(matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return matrix / norms


class _Backend:
    name = "base"
    dim = _FALLBACK_DIM

    def embed(self, texts: list[str], *, is_query: bool) -> np.ndarray:  # pragma: no cover
        raise NotImplementedError


class GeminiBackend(_Backend):
    """Embeddings via l'API Google Gemini.

    Modèle par défaut : ``text-embedding-004`` (768 dims, quota gratuit généreux).
    ``gemini-embedding-001`` est également supporté (et permet alors de réduire la
    dimension via ``output_dimensionality``).
    """

    name = "gemini"
    dim = 768
    _MAX_RETRIES = 5

    def __init__(self, api_key: str) -> None:
        import time as _time

        from google import genai  # import paresseux

        self._time = _time
        self._genai = genai
        self._client = genai.Client(api_key=api_key)
        self._model = os.environ.get("GEMINI_EMBED_MODEL", "gemini-embedding-2")

    def embed(self, texts: list[str], *, is_query: bool) -> np.ndarray:
        from google.genai import types
        from google.genai.errors import ClientError, ServerError

        task = "RETRIEVAL_QUERY" if is_query else "RETRIEVAL_DOCUMENT"
        config_kwargs: dict = {"task_type": task}
        # output_dimensionality n'est réglable que sur gemini-embedding-*.
        if "gemini-embedding" in self._model:
            config_kwargs["output_dimensionality"] = self.dim

        last_exc: Exception | None = None
        for attempt in range(self._MAX_RETRIES):
            try:
                resp = self._client.models.embed_content(
                    model=self._model,
                    contents=texts,
                    config=types.EmbedContentConfig(**config_kwargs),
                )
                vectors = np.array([e.values for e in resp.embeddings], dtype=np.float32)
                return _l2_normalize(vectors)
            except (ClientError, ServerError) as exc:
                status = getattr(exc, "code", None) or getattr(exc, "status_code", None)
                if status not in (429, 500, 503):
                    raise
                last_exc = exc
                self._time.sleep(min(2**attempt, 30))
        raise RuntimeError(f"Gemini embed: quota/erreur persistante après retries: {last_exc}")


class LocalBackend(_Backend):
    """Embeddings locaux via sentence-transformers (multilingue, hors-ligne)."""

    name = "local"
    dim = 384

    def __init__(self) -> None:
        from sentence_transformers import SentenceTransformer  # import paresseux

        model_name = os.environ.get("LOCAL_EMBED_MODEL", "intfloat/multilingual-e5-base")
        self._model = SentenceTransformer(model_name)

    def embed(self, texts: list[str], *, is_query: bool) -> np.ndarray:
        prefix = "query: " if is_query else "passage: "
        vectors = self._model.encode(
            [prefix + t for t in texts],
            normalize_embeddings=True,
            convert_to_numpy=True,
        )
        return np.asarray(vectors, dtype=np.float32)


class HashingBackend(_Backend):
    """Secours déterministe sans modèle : hachage de tokens + n-grammes.

    Ne capture pas la sémantique profonde mais évite tout crash et offre un
    signal lexical quand aucun vrai modèle n'est disponible.
    """

    name = "hashing"
    dim = _FALLBACK_DIM

    def _vectorize(self, text: str) -> np.ndarray:
        vec = np.zeros(self.dim, dtype=np.float32)
        tokens = _TOKEN_RE.findall(text.lower())
        for tok in tokens:
            features = [tok]
            for n in (3, 4):
                if len(tok) > n:
                    features.extend(tok[i : i + n] for i in range(len(tok) - n + 1))
            for feat in features:
                h = int(hashlib.md5(feat.encode("utf-8")).hexdigest(), 16)
                vec[h % self.dim] += 1.0
        norm = float(np.linalg.norm(vec))
        if norm:
            vec /= norm
        return vec

    def embed(self, texts: list[str], *, is_query: bool) -> np.ndarray:
        return np.vstack([self._vectorize(t) for t in texts])


_backend: _Backend | None = None
_backend_lock = threading.Lock()
_cache: dict[tuple[str, bool], np.ndarray] = {}


def _select_backend() -> _Backend:
    _load_dotenv()
    key = _api_key()
    if key:
        try:
            return GeminiBackend(key)
        except Exception as exc:  # pragma: no cover - dépend de l'environnement
            print(f"[embeddings] Gemini indisponible ({exc}); fallback local.")
    try:
        return LocalBackend()
    except Exception as exc:  # pragma: no cover - dépend de l'environnement
        print(f"[embeddings] Modèle local indisponible ({exc}); secours lexical.")
    return HashingBackend()


def get_backend() -> _Backend:
    global _backend
    if _backend is None:
        with _backend_lock:
            if _backend is None:
                _backend = _select_backend()
    return _backend


def backend_name() -> str:
    return get_backend().name


def embedding_dim() -> int:
    return get_backend().dim


def _embed_one(text: str, *, is_query: bool) -> np.ndarray:
    cache_key = (text, is_query)
    cached = _cache.get(cache_key)
    if cached is not None:
        return cached
    vec = get_backend().embed([text], is_query=is_query)[0]
    _cache[cache_key] = vec
    return vec


def embed_query(text: str) -> np.ndarray:
    return _embed_one(text, is_query=True)


def embed_document(text: str) -> np.ndarray:
    return _embed_one(text, is_query=False)


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    """Similarité cosinus (les vecteurs sont déjà normalisés)."""
    denom = (np.linalg.norm(a) * np.linalg.norm(b)) or 1.0
    return float(np.dot(a, b) / denom)


def reset_backend() -> None:
    """Réinitialise le backend (utile pour les tests)."""
    global _backend
    with _backend_lock:
        _backend = None
        _cache.clear()


__all__ = [
    "backend_name",
    "cosine",
    "embed_document",
    "embed_query",
    "embedding_dim",
    "get_backend",
    "reset_backend",
]
