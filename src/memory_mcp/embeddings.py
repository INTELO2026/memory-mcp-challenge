"""Couche d'embeddings sémantiques avec cascade de fallback.

Sélection du backend (variable d'env ``MEMBRIDGE_EMBEDDER`` : ``auto`` par défaut) :

1. ``gemini``  -> API Google ``text-embedding-004`` (si ``GEMINI_API_KEY`` + lib dispo).
2. ``local``   -> ``sentence-transformers`` multilingue (si installé).
3. ``hashing`` -> repli déterministe hors-ligne (hashing bag-of-words), sans dépendance.

Le mode ``auto`` essaie 1, puis 2, puis 3. Le repli garantit que ``lint``/``smoke``
et l'import du serveur fonctionnent même sans réseau ni modèle.
"""

from __future__ import annotations

import hashlib
import math
import os
import re
from abc import ABC, abstractmethod

try:  # Charge GEMINI_API_KEY depuis un fichier .env si présent (best-effort).
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    pass

_TOKEN_RE = re.compile(r"\w+", re.UNICODE)

_STOPWORDS = frozenset(
    {
        "a",
        "au",
        "aux",
        "ce",
        "ces",
        "de",
        "des",
        "du",
        "en",
        "est",
        "et",
        "il",
        "je",
        "la",
        "le",
        "les",
        "ma",
        "mon",
        "ne",
        "on",
        "ou",
        "pas",
        "pour",
        "que",
        "qui",
        "sa",
        "se",
        "son",
        "sur",
        "un",
        "une",
        "vos",
        "votre",
    }
)


class Embedder(ABC):
    """Interface commune : transforme du texte en vecteur dense normalisé."""

    name: str = "base"
    dim: int = 0

    @abstractmethod
    def embed(self, text: str) -> list[float]:
        """Retourne le vecteur (normalisé L2) d'un texte."""

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [self.embed(t) for t in texts]


def _l2_normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in vec))
    if norm <= 0:
        return vec
    return [v / norm for v in vec]


class HashingEmbedder(Embedder):
    """Repli déterministe et hors-ligne (hashing de mots dans un espace fixe).

    Ne capture pas la sémantique profonde (paraphrases pures), mais reste
    déterministe, sans dépendance, et suffisant pour que l'API ne casse jamais.
    """

    name = "hashing"

    def __init__(self, dim: int = 512) -> None:
        self.dim = dim

    def embed(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        words = [w for w in _TOKEN_RE.findall(text.lower()) if w not in _STOPWORDS and len(w) > 2]
        for w in words:
            h = int(hashlib.md5(w.encode("utf-8")).hexdigest(), 16)
            idx = h % self.dim
            sign = 1.0 if (h >> 8) % 2 == 0 else -1.0
            vec[idx] += sign
        return _l2_normalize(vec)


class LocalEmbedder(Embedder):
    """Embeddings locaux via sentence-transformers (modèle multilingue)."""

    name = "local"
    # Modèle léger (~0,5 Go) adapté aux PC modestes ; surchargeable via MEMBRIDGE_LOCAL_MODEL.
    _DEFAULT_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"

    def __init__(self, model_name: str | None = None) -> None:
        from sentence_transformers import SentenceTransformer  # import paresseux

        self.model_name = model_name or os.getenv("MEMBRIDGE_LOCAL_MODEL") or self._DEFAULT_MODEL
        self._model = SentenceTransformer(self.model_name)
        get_dim = getattr(self._model, "get_embedding_dimension", None) or (
            self._model.get_sentence_embedding_dimension
        )
        self.dim = int(get_dim())

    def embed(self, text: str) -> list[float]:
        vec = self._model.encode(text, normalize_embeddings=True)
        return [float(x) for x in vec]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        vecs = self._model.encode(texts, normalize_embeddings=True)
        return [[float(x) for x in v] for v in vecs]


class GeminiEmbedder(Embedder):
    """Embeddings via l'API Google Gemini (text-embedding-004)."""

    name = "gemini"
    _MODEL = os.getenv("MEMBRIDGE_GEMINI_EMBED_MODEL", "models/gemini-embedding-001")

    def __init__(self, api_key: str | None = None) -> None:
        import google.generativeai as genai  # import paresseux

        self._genai = genai
        key = api_key or os.getenv("GEMINI_API_KEY")
        if not key:
            raise RuntimeError("GEMINI_API_KEY manquante")
        genai.configure(api_key=key)
        # Sonde la dimension réelle du modèle (échoue tôt si la clé/modèle est invalide).
        self.dim = len(self.embed("ping"))

    def embed(self, text: str) -> list[float]:
        import time

        last_exc: Exception | None = None
        for attempt in range(4):
            try:
                resp = self._genai.embed_content(model=self._MODEL, content=text)
                return _l2_normalize([float(x) for x in resp["embedding"]])
            except Exception as exc:  # backoff simple sur quota / réseau
                last_exc = exc
                if attempt < 3:
                    time.sleep(1.5 * (attempt + 1))
        raise RuntimeError(f"Gemini embed_content a échoué: {last_exc}")


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Cosinus entre deux vecteurs (suppose une longueur identique)."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y
    if na <= 0 or nb <= 0:
        return 0.0
    return dot / (math.sqrt(na) * math.sqrt(nb))


class CachedEmbedder(Embedder):
    """Enveloppe un embedder avec un cache mémoire + persistant (SQLite).

    Évite de recalculer (ou de rappeler l'API) le vecteur d'un texte déjà vu.
    Indispensable pour rester dans le tier gratuit et accélérer les tests.
    """

    def __init__(self, base: Embedder, cache_path: str | None = None) -> None:
        import sqlite3

        self.base = base
        self.name = base.name
        self.dim = base.dim
        self._mem: dict[str, list[float]] = {}
        path = cache_path or os.getenv(
            "MEMBRIDGE_CACHE",
            os.path.join(os.path.expanduser("~"), ".cache", "membridge_embeddings.db"),
        )
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            self._conn: sqlite3.Connection | None = sqlite3.connect(path, check_same_thread=False)
            self._conn.execute(
                "CREATE TABLE IF NOT EXISTS emb (k TEXT PRIMARY KEY, v TEXT NOT NULL)"
            )
            self._conn.commit()
        except Exception:
            self._conn = None  # cache désactivé si non inscriptible

    def _key(self, text: str) -> str:
        return hashlib.sha256(f"{self.base.name}:{self.dim}:{text}".encode("utf-8")).hexdigest()

    def embed(self, text: str) -> list[float]:
        import json

        if text in self._mem:
            return self._mem[text]
        key = self._key(text)
        if self._conn is not None:
            row = self._conn.execute("SELECT v FROM emb WHERE k = ?", (key,)).fetchone()
            if row is not None:
                vec = json.loads(row[0])
                self._mem[text] = vec
                return vec
        vec = self.base.embed(text)
        self._mem[text] = vec
        if self._conn is not None:
            try:
                self._conn.execute(
                    "INSERT OR REPLACE INTO emb (k, v) VALUES (?, ?)", (key, json.dumps(vec))
                )
                self._conn.commit()
            except Exception:
                pass
        return vec


_EMBEDDER: Embedder | None = None


def _build_embedder() -> Embedder:
    choice = os.getenv("MEMBRIDGE_EMBEDDER", "auto").strip().lower()

    def try_gemini() -> Embedder | None:
        try:
            return CachedEmbedder(GeminiEmbedder())
        except Exception:
            return None

    def try_local() -> Embedder | None:
        try:
            return CachedEmbedder(LocalEmbedder())
        except Exception:
            return None

    if choice == "gemini":
        return try_gemini() or try_local() or HashingEmbedder()
    if choice == "local":
        return try_local() or HashingEmbedder()
    if choice == "hashing":
        return HashingEmbedder()

    # auto : Gemini si clé, sinon local, sinon repli déterministe.
    if os.getenv("GEMINI_API_KEY"):
        emb = try_gemini()
        if emb is not None:
            return emb
    return try_local() or HashingEmbedder()


def get_embedder() -> Embedder:
    """Singleton paresseux (le modèle n'est chargé qu'une fois)."""
    global _EMBEDDER
    if _EMBEDDER is None:
        _EMBEDDER = _build_embedder()
    return _EMBEDDER


def reset_embedder() -> None:
    """Réinitialise le singleton (utile pour les tests / changement de backend)."""
    global _EMBEDDER
    _EMBEDDER = None
