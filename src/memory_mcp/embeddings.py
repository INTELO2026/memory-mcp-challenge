"""Moteur d'embeddings enfichable pour la recherche sémantique.

Stratégie : un vrai modèle de phrases multilingue (sentence-transformers) capable
de comprendre les paraphrases — y compris quand la requête ne partage aucun mot
avec la mémoire cible — avec repli bag-of-words si la dépendance est absente.

Le backend est choisi par variable d'environnement ``MEMORY_EMBEDDER`` :

* ``auto`` (défaut) : sentence-transformers si disponible, sinon bag-of-words.
* ``st`` : force sentence-transformers (erreur si absent).
* ``bow`` : force le repli lexical (tests rapides, sans téléchargement de modèle).

Le modèle est chargé paresseusement et mis en cache (singleton), car le premier
chargement est coûteux.
"""

from __future__ import annotations

import math
import os
import re
from typing import Any, Protocol, runtime_checkable

# Modèle de retrieval multilingue. BGE-M3 sépare nettement les paraphrases
# proches (marges larges) et ne requiert pas de préfixe requête/document ; les
# préfixes E5 restent gérés automatiquement si l'on bascule sur un modèle e5.
DEFAULT_MODEL = "BAAI/bge-m3"

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


@runtime_checkable
class Embedder(Protocol):
    """Contrat minimal d'un moteur d'embeddings.

    ``encode`` (document stocké) et ``encode_query`` (requête de recherche)
    renvoient une représentation JSON-sérialisable (stockée en base) ;
    ``similarity`` compare une représentation de requête à une de document.

    La distinction requête/document permet aux modèles de retrieval asymétrique
    (famille E5) d'appliquer les préfixes ``query:`` / ``passage:`` attendus.
    """

    name: str

    def encode(self, text: str) -> Any: ...

    def encode_query(self, text: str) -> Any: ...

    def similarity(self, query_emb: Any, doc_emb: Any) -> float: ...


# --- Outils lexicaux partagés (repli + bonus hybride) ----------------------


def _token_set(text: str) -> set[str]:
    return {w for w in re.findall(r"\w+", text.lower()) if w not in _STOPWORDS and len(w) > 2}


def _char_ngrams(text: str, n: int = 4) -> set[str]:
    """Tri-/quadrigrammes de caractères : capte les racines (factur≈facture)."""
    cleaned = re.sub(r"\s+", " ", text.lower())
    return {cleaned[i : i + n] for i in range(max(0, len(cleaned) - n + 1))}


def lexical_overlap(query: str, doc: str) -> float:
    """Recouvrement lexical normalisé (Jaccard mots + n-grammes), borné [0, 1].

    Sert de léger signal de réordonnancement hybride ; ne contient aucune
    réponse codée en dur, c'est une pure mesure de similarité de surface.
    """
    qw, dw = _token_set(query), _token_set(doc)
    word_j = len(qw & dw) / len(qw | dw) if (qw or dw) else 0.0
    qn, dn = _char_ngrams(query), _char_ngrams(doc)
    ngram_j = len(qn & dn) / len(qn | dn) if (qn or dn) else 0.0
    return 0.5 * word_j + 0.5 * ngram_j


def _tokenize(text: str) -> dict[str, float]:
    words = [w for w in re.findall(r"\w+", text.lower()) if w not in _STOPWORDS and len(w) > 2]
    if not words:
        return {}
    freq: dict[str, float] = {}
    for w in words:
        freq[w] = freq.get(w, 0.0) + 1.0
    norm = math.sqrt(sum(v * v for v in freq.values())) or 1.0
    return {k: v / norm for k, v in freq.items()}


def _sparse_cosine(a: dict[str, float], b: dict[str, float]) -> float:
    if not a or not b:
        return 0.0
    common = set(a) & set(b)
    return sum(a[k] * b[k] for k in common)


# --- Repli lexical (bag-of-words normalisé) -------------------------------


class BagOfWordsEmbedder:
    """Repli sans dépendance : ne comprend pas les paraphrases, mais déterministe."""

    name = "bow"

    def encode(self, text: str) -> dict[str, float]:
        return _tokenize(text)

    def encode_query(self, text: str) -> dict[str, float]:
        return _tokenize(text)

    def similarity(self, query_emb: Any, doc_emb: Any) -> float:
        return _sparse_cosine(query_emb, doc_emb)


# --- Embeddings sémantiques (sentence-transformers) -----------------------


class SentenceTransformerEmbedder:
    """Vecteurs denses normalisés ; la similarité est un simple produit scalaire."""

    def __init__(self, model_name: str = DEFAULT_MODEL) -> None:
        from sentence_transformers import SentenceTransformer  # import paresseux

        self._model = SentenceTransformer(model_name)
        self.name = f"st:{model_name}"
        # Les modèles E5 exigent des préfixes distincts requête/document.
        self._use_e5_prefix = "e5" in model_name.lower()

    def _embed(self, text: str, is_query: bool) -> list[float]:
        prepared = text
        if self._use_e5_prefix:
            prepared = ("query: " if is_query else "passage: ") + text
        vec = self._model.encode(prepared, normalize_embeddings=True)
        return [float(x) for x in vec]

    def encode(self, text: str) -> list[float]:
        return self._embed(text, is_query=False)

    def encode_query(self, text: str) -> list[float]:
        return self._embed(text, is_query=True)

    def similarity(self, query_emb: Any, doc_emb: Any) -> float:
        # Vecteurs déjà normalisés -> cosinus = produit scalaire.
        return float(sum(a * b for a, b in zip(query_emb, doc_emb)))


# --- Fabrique singleton ----------------------------------------------------

_EMBEDDER: Embedder | None = None


def get_embedder() -> Embedder:
    """Retourne le moteur d'embeddings actif (chargé une seule fois)."""
    global _EMBEDDER
    if _EMBEDDER is not None:
        return _EMBEDDER

    backend = os.getenv("MEMORY_EMBEDDER", "auto").lower()
    model = os.getenv("MEMORY_EMBEDDER_MODEL", DEFAULT_MODEL)

    if backend == "bow":
        _EMBEDDER = BagOfWordsEmbedder()
    elif backend == "st":
        _EMBEDDER = SentenceTransformerEmbedder(model)
    else:  # auto
        try:
            _EMBEDDER = SentenceTransformerEmbedder(model)
        except Exception:
            _EMBEDDER = BagOfWordsEmbedder()

    return _EMBEDDER


def reset_embedder() -> None:
    """Réinitialise le singleton (utile pour les tests)."""
    global _EMBEDDER
    _EMBEDDER = None
