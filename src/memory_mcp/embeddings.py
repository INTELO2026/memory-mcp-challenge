"""Couche d'embeddings pluggable pour MemBridge.

Stratégie hybride, choisie automatiquement :

1. **Gemini** (``text-embedding-004``) — le "turbo" qualité, si une clé API est présente.
2. **sentence-transformers** (``paraphrase-multilingual-MiniLM-L12-v2``) — local, hors-ligne,
   multilingue (FR), sans clé : c'est le moteur qui fait passer la CI.
3. **Hashing** — repli déterministe sans dépendance lourde, garantit que le système tourne
   même si rien d'autre n'est installé.

Tous les vecteurs sont L2-normalisés : la similarité cosinus se réduit alors à un produit
scalaire, ce qui simplifie et accélère la recherche.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import sqlite3
import time
from functools import lru_cache
from pathlib import Path
from typing import Protocol, runtime_checkable

_WORD_RE = re.compile(r"\w+", re.UNICODE)

# Ensemble local : un modèle multilingue généraliste + un modèle spécialisé français.
# La concaténation L2-normalisée des deux donne une similarité = moyenne des cosinus, nettement
# plus robuste sur les paraphrases françaises courtes (validé empiriquement : 6/6 vs 5/6).
DEFAULT_LOCAL_MODELS = (
    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
    "dangvantuan/sentence-camembert-base",
)
DEFAULT_GEMINI_MODEL = "gemini-embedding-001"
DEFAULT_GEMINI_DIM = 768
HASHING_DIM = 512


@runtime_checkable
class Embedder(Protocol):
    """Contrat minimal d'un fournisseur d'embeddings."""

    name: str

    @property
    def dim(self) -> int: ...

    def embed(self, texts: list[str]) -> list[list[float]]: ...


def _l2_normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def cosine(a: list[float], b: list[float]) -> float:
    """Cosinus entre deux vecteurs (robuste si non normalisés)."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


class LocalEmbeddings:
    """Embeddings locaux via sentence-transformers (chargement paresseux).

    Supporte un **ensemble** de modèles : leurs vecteurs sont concaténés puis L2-normalisés,
    ce qui rend la similarité = moyenne des cosinus de chaque modèle. Configurable via
    ``MEMBRIDGE_LOCAL_MODEL`` (un ou plusieurs noms séparés par des virgules).
    """

    def __init__(self, model_names: str | tuple[str, ...] | None = None) -> None:
        if model_names is None:
            env = os.getenv("MEMBRIDGE_LOCAL_MODEL")
            names = (
                tuple(m.strip() for m in env.split(",") if m.strip())
                if env
                else DEFAULT_LOCAL_MODELS
            )
        elif isinstance(model_names, str):
            names = tuple(m.strip() for m in model_names.split(",") if m.strip())
        else:
            names = tuple(model_names)
        self.model_names = names
        self.name = "local:" + "+".join(n.split("/")[-1] for n in names)
        self._models: list = []
        self._dim: int | None = None

    def _ensure(self) -> None:
        if not self._models:
            from sentence_transformers import SentenceTransformer

            self._models = [SentenceTransformer(n) for n in self.model_names]

            def _model_dim(m) -> int:
                getter = (
                    getattr(m, "get_embedding_dimension", None)
                    or m.get_sentence_embedding_dimension
                )
                return int(getter())

            self._dim = sum(_model_dim(m) for m in self._models)

    @property
    def dim(self) -> int:
        self._ensure()
        assert self._dim is not None
        return self._dim

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        self._ensure()
        import numpy as np

        parts = [
            m.encode(
                texts, normalize_embeddings=True, convert_to_numpy=True, show_progress_bar=False
            )
            for m in self._models
        ]
        combined = np.concatenate(parts, axis=1) if len(parts) > 1 else parts[0]
        norms = np.linalg.norm(combined, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        combined = combined / norms
        return [v.astype(float).tolist() for v in combined]


class GeminiEmbeddings:
    """Embeddings via l'API Google Gemini (turbo qualité)."""

    def __init__(self, model_name: str | None = None, api_key: str | None = None) -> None:
        self.model_name = model_name or os.getenv(
            "MEMBRIDGE_GEMINI_EMBED_MODEL", DEFAULT_GEMINI_MODEL
        )
        self.name = f"gemini:{self.model_name}"
        self._api_key = api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        self._client = None
        self._config = None
        self._dim = int(os.getenv("MEMBRIDGE_GEMINI_EMBED_DIM", str(DEFAULT_GEMINI_DIM)))

    def _ensure(self) -> None:
        if self._client is None:
            if not self._api_key:
                raise RuntimeError("GEMINI_API_KEY manquante pour GeminiEmbeddings")
            from google import genai
            from google.genai import types

            self._client = genai.Client(api_key=self._api_key)
            self._config = types.EmbedContentConfig(output_dimensionality=self._dim)

    @property
    def dim(self) -> int:
        return self._dim

    def embed(
        self, texts: list[str], batch_size: int = 100, max_retries: int = 4
    ) -> list[list[float]]:
        if not texts:
            return []
        self._ensure()
        assert self._client is not None
        import time

        out: list[list[float]] = []
        for start in range(0, len(texts), batch_size):
            batch = texts[start : start + batch_size]
            delay = 1.0
            for attempt in range(max_retries):
                try:
                    resp = self._client.models.embed_content(
                        model=self.model_name, contents=batch, config=self._config
                    )
                    out.extend(_l2_normalize(list(e.values)) for e in resp.embeddings)
                    break
                except Exception as exc:  # rate-limit / réseau : backoff exponentiel
                    msg = str(exc).lower()
                    transient = any(
                        k in msg for k in ("429", "rate", "quota", "503", "timeout", "unavailable")
                    )
                    if attempt == max_retries - 1 or not transient:
                        raise
                    time.sleep(delay)
                    delay *= 2
        if out:
            self._dim = len(out[0])
        return out


class HashingEmbeddings:
    """Repli déterministe : hashing trick sur unigrammes, bigrammes et 3-grammes de caractères.

    Ne capture pas de vraie sémantique (pas de paraphrases), mais reste lexicalement utile et
    ne nécessite aucune dépendance externe.
    """

    def __init__(self, dim: int = HASHING_DIM) -> None:
        self.name = "hashing"
        self._dim = dim

    @property
    def dim(self) -> int:
        return self._dim

    def _features(self, text: str) -> list[str]:
        tokens = _WORD_RE.findall(text.lower())
        feats: list[str] = list(tokens)
        feats += [f"{tokens[i]}_{tokens[i + 1]}" for i in range(len(tokens) - 1)]
        joined = "".join(tokens)
        feats += [joined[i : i + 3] for i in range(len(joined) - 2)]
        return feats

    def _embed_one(self, text: str) -> list[float]:
        vec = [0.0] * self._dim
        for feat in self._features(text):
            h = int(hashlib.md5(feat.encode("utf-8")).hexdigest(), 16)
            idx = h % self._dim
            sign = 1.0 if (h >> 16) & 1 else -1.0
            vec[idx] += sign
        return _l2_normalize(vec)

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(t) for t in texts]


class CachedEmbedder:
    """Décorateur : cache persistant (SQLite) + throttle débit autour d'un embedder.

    Indispensable pour Gemini : on n'appelle l'API qu'**une fois par texte** (résultats
    réutilisés d'un run à l'autre → démo instantanée après un premier passage), et on limite
    le débit sous le quota free tier (≈100 req/min) pour éviter les 429.
    """

    def __init__(self, inner: Embedder, max_per_min: int | None = None) -> None:
        self.inner = inner
        self.name = inner.name
        self._namespace = inner.name
        self._max_per_min = int(os.getenv("MEMBRIDGE_MAX_RPM", str(max_per_min or 80)))
        self._calls: list[float] = []
        cache_dir = Path(os.getenv("MEMBRIDGE_CACHE_DIR", ".cache/membridge"))
        cache_dir.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(cache_dir / "emb_cache.db"), check_same_thread=False)
        self._conn.execute("CREATE TABLE IF NOT EXISTS emb (k TEXT PRIMARY KEY, v TEXT)")
        self._conn.commit()

    @property
    def dim(self) -> int:
        return self.inner.dim

    def _key(self, text: str) -> str:
        return hashlib.sha256(f"{self._namespace}|{text}".encode()).hexdigest()

    def _throttle(self, n: int) -> None:
        now = time.time()
        self._calls = [t for t in self._calls if now - t < 60]
        while self._calls and len(self._calls) + n > self._max_per_min:
            sleep_for = 60 - (now - self._calls[0]) + 0.1
            time.sleep(max(sleep_for, 0.1))
            now = time.time()
            self._calls = [t for t in self._calls if now - t < 60]
        self._calls.extend([now] * n)

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        keys = [self._key(t) for t in texts]
        found: dict[str, list[float]] = {}
        for i in range(0, len(keys), 500):
            chunk = keys[i : i + 500]
            placeholders = ",".join("?" * len(chunk))
            rows = self._conn.execute(
                f"SELECT k, v FROM emb WHERE k IN ({placeholders})", chunk
            ).fetchall()
            found.update({k: json.loads(v) for k, v in rows})

        results: list[list[float] | None] = [found.get(k) for k in keys]
        miss_idx = [i for i, r in enumerate(results) if r is None]
        if miss_idx:
            miss_texts = [texts[i] for i in miss_idx]
            self._throttle(len(miss_texts))
            vecs = self.inner.embed(miss_texts)
            items = []
            for j, i in enumerate(miss_idx):
                results[i] = vecs[j]
                items.append((keys[i], json.dumps(vecs[j])))
            self._conn.executemany("INSERT OR REPLACE INTO emb (k, v) VALUES (?, ?)", items)
            self._conn.commit()
        return [r for r in results if r is not None]


def _has_gemini_key() -> bool:
    return bool(os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"))


@lru_cache(maxsize=4)
def get_embedder(kind: str | None = None) -> Embedder:
    """Retourne (et met en cache) le fournisseur d'embeddings.

    ``kind`` ∈ {"auto", "gemini", "local", "hashing"} ; par défaut la variable
    d'environnement ``MEMBRIDGE_EMBEDDINGS`` ou "auto".
    """
    kind = (kind or os.getenv("MEMBRIDGE_EMBEDDINGS", "auto")).lower()

    if kind == "gemini":
        return CachedEmbedder(GeminiEmbeddings())
    if kind == "local":
        return LocalEmbeddings()
    if kind == "hashing":
        return HashingEmbeddings()

    # auto : Gemini (caché) si clé dispo, sinon local, sinon hashing.
    if _has_gemini_key():
        try:
            embedder = CachedEmbedder(GeminiEmbeddings())
            embedder.embed(["ping"])  # validation immédiate
            return embedder
        except Exception:
            pass
    try:
        import sentence_transformers  # noqa: F401

        return LocalEmbeddings()
    except Exception:
        return HashingEmbeddings()


def reset_embedder_cache() -> None:
    get_embedder.cache_clear()
