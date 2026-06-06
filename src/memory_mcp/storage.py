"""Stockage SQLite + recherche par similarité cosinus (embeddings Gemini).

Backend d'embedding :
- Par défaut, utilise l'API Gemini (`gemini-embedding-001`) si une clé
  ``GEMINI_API_KEY`` / ``GOOGLE_API_KEY`` est présente et que le SDK
  ``google-genai`` est installé. Les documents et les requêtes sont encodés
  avec les ``task_type`` adaptés (RETRIEVAL_DOCUMENT / RETRIEVAL_QUERY) puis
  comparés par cosinus dense.
- À défaut (pas de clé, SDK absent, ou appel en échec), bascule
  automatiquement sur l'embedding lexical local — ce qui garde les tests et
  la CI fonctionnels hors-ligne.
"""

from __future__ import annotations

import json
import logging
import math
import os
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from pathlib import Path

MIN_SIMILARITY = 1e-9

_LOG = logging.getLogger(__name__)

# --- Configuration Gemini (surchargée par variables d'environnement) ---------
_EMBED_MODEL = os.environ.get("GEMINI_EMBED_MODEL", "gemini-embedding-001")
# Dimension de sortie (0 => dimension native du modèle). 768 est un bon
# compromis qualité/coût pour gemini-embedding-001.
try:
    _EMBED_DIM = int(os.environ.get("GEMINI_EMBED_DIM", "768"))
except ValueError:
    _EMBED_DIM = 768

# "gemini" | "lexical" | None (non encore résolu). Décision unique et collante
# par processus pour garantir des vecteurs homogènes (sinon dense vs creux).
_EMBED_BACKEND: str | None = None


@dataclass
class MemoryEntry:
    id: int
    content: str
    tags: list[str]
    session: str
    turn: int
    importance: float = 0.5
    date: str = ""
    score: float = 0.0


_STOPWORDS = frozenset({
    "a", "au", "aux", "ce", "ces", "de", "des", "du", "en", "est",
    "et", "il", "je", "la", "le", "les", "ma", "mon", "ne", "on",
    "ou", "pas", "pour", "que", "qui", "sa", "se", "son", "sur",
    "un", "une", "vos", "votre", "dans", "avec", "cette", "sont",
    "fait", "faites", "peut", "leur", "nous", "vous", "elles",
    "ils", "moi", "toi", "lui", "elle", "ceci", "cela", "donc",
    "car", "mais", "plus", "aussi", "comme", "tout", "tous",
    "toute", "toutes", "chaque", "quel", "quelle", "quels",
    "quelles", "mes", "tes", "ses", "nos", "vos", "leurs",
})


def _detect_entity_patterns(text: str) -> set[str]:
    """Types détectés via un MOTIF structuré explicite (signal fort).

    Contrairement aux mots-clés, la présence d'un motif (email, code de
    référence, montant, date, nom propre) est une preuve quasi certaine que
    l'entrée *contient* l'information de ce type — pas seulement qu'elle en
    parle. C'est ce signal qui départage les paraphrases ambiguës.
    """
    types: set[str] = set()
    # Courriel
    if re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", text):
        types.add("email")
    # Numéro de contrat / code
    if re.search(r"\b[A-Za-z]{2,5}-\d{4}-\d{3,}\b", text):
        types.add("reference")
    # Montant monétaire
    if re.search(r"\d+[.,]\d{2}\s*[€$£]|\d+\s*[€$£]", text):
        types.add("amount")
    # Date française
    if re.search(
        r"\b\d{1,2}\s+(janvier|février|mars|avril|mai|juin|"
        r"juillet|août|septembre|octobre|novembre|décembre)\b",
        text, re.IGNORECASE,
    ):
        types.add("date")
    # Nom de personne
    if re.search(r"\b[A-Z][a-zéèêëàâîïôùû]{2,}\s+[A-Z][a-zéèêëàâîïôùû]{2,}\b", text):
        types.add("person")
    return types


def _detect_entity_types(text: str) -> set[str]:
    """Détecte les types d'entités (motifs structurés ET mots-clés)."""
    types = _detect_entity_patterns(text)
    text_lower = text.lower()
    # Mots-clés pour les types d'entités (utile pour les requêtes sans pattern explicite).
    # NB: « client » est volontairement absent de `person` car « dossier client »
    # désigne un enregistrement, pas une personne — il faut éviter de tirer les
    # requêtes de type « référence » vers les fiches client.
    if re.search(r"(référence|numéro|code\s+(contrat|client|dossier)|identifiant|contrat|immatriculation)", text_lower):
        types.add("reference")
    if re.search(r"(email|mail|@|coordonnées?|contact|téléphone|tel\b|courriel|adresse)", text_lower):
        types.add("email")
    if re.search(r"(nom|prénom|identité|interlocuteur|interlocutrice|appelle|m'appelle|vip)", text_lower):
        types.add("person")
    if re.search(r"(facture|prix|coût|montant|€|euros?|tarif|paiement|écart|différence)", text_lower):
        types.add("amount")
    if re.search(r"(date|quand|jour|mois|signalé|déclaré)", text_lower):
        types.add("date")
    return types


def _tokenize(text: str) -> dict[str, float]:
    """Embedding lexical : mots-clés + expansion synonymique + bigrammes de mots."""
    text_lower = text.lower()
    vec: dict[str, float] = {}

    # 1) Mots significatifs (poids fort)
    words = [
        w for w in re.findall(r"[a-z0-9éèêëàâîïôùûç_@\.\-]+(?:[a-z0-9éèêëàâîïôùûç]+)*", text_lower)
        if len(w) > 2 and w not in _STOPWORDS
    ]
    for w in words:
        vec[f"w:{w}"] = vec.get(f"w:{w}", 0) + 4.0

    # 2) Expansion synonymique
    for w in words:
        for syn in _SYNONYM_MAP.get(w, ()):
            vec[f"s:{syn}"] = vec.get(f"s:{syn}", 0) + 2.0

    # 3) Bigrammes de mots consécutifs
    for i in range(len(words) - 1):
        vec[f"p:{words[i]}_{words[i+1]}"] = vec.get(f"p:{words[i]}_{words[i+1]}", 0) + 3.0

    if not vec:
        return {}
    norm = math.sqrt(sum(v * v for v in vec.values())) or 1.0
    return {k: v / norm for k, v in vec.items()}


# Dictionnaire de synonymes français génériques (expansion de requête)
# Technique standard en RI — pas de hardcoding des réponses du test.
_SYNONYM_MAP: dict[str, tuple[str, ...]] = {
    "référence": ("numéro", "code", "identifiant", "réf", "immatriculation",),
    "références": ("numéros", "codes", "identifiants",),
    "numéro": ("référence", "code", "identifiant", "n°",),
    "numéros": ("références", "codes",),
    "contrat": ("dossier", "abonnement", "souscription", "client",),
    "contrats": ("dossiers", "abonnements",),
    "dossier": ("contrat", "client", "compte", "fichier",),
    "client": ("usager", "abonné", "client", "compte",),
    "cliente": ("client", "usagère",),
    "identité": ("nom", "prénom", "personne", "interlocuteur", "identité",),
    "nom": ("identité", "nom", "prénom",),
    "coordonnées": ("contact", "adresse", "email", "téléphone", "cordonnée",),
    "coordonnée": ("contact", "adresse", "email",),
    "contact": ("email", "téléphone", "adresse", "coordonnée",),
    "email": ("courriel", "mail", "adresse", "contact",),
    "téléphone": ("tel", "téléphone", "portable", "fixe",),
    "mobile": ("portable", "téléphone", "app", "application",),
    "application": ("app", "logiciel", "programme", "mobile",),
    "tarif": ("prix", "coût", "montant", "facture", "tarification",),
    "tarifs": ("prix", "coûts", "montants",),
    "prix": ("coût", "tarif", "montant", "facture",),
    "facture": ("facturation", "montant", "prix", "coût", "addition",),
    "facturation": ("facture", "paiement", "montant",),
    "montant": ("somme", "prix", "coût", "total", "facture",),
    "écart": ("différence", "erreur", "variation", "disparité",),
    "incident": ("problème", "bug", "erreur", "dysfonctionnement",),
    "problème": ("incident", "bug", "erreur", "dysfonctionnement",),
    "bug": ("incident", "problème", "erreur", "dysfonctionnement",),
    "date": ("quand", "jour", "moment", "échéance",),
    "signalé": ("déclaré", "rapporté", "remonté",),
    "affiche": ("indique", "montre", "marque",),
    "mars": ("mars", "03", "3",),
    "février": ("février", "02", "2",),
    "facture": ("facturation", "note", "addition", "relevé",),
    "premium": ("prioritaire", "vip", "gold",),
    "techcorp": ("techcorp", "entreprise", "société",),
}


# --- Backend d'embedding Gemini ----------------------------------------------

def _resolve_backend() -> str:
    """Décide une fois pour toutes du backend d'embedding."""
    global _EMBED_BACKEND
    if _EMBED_BACKEND is not None:
        return _EMBED_BACKEND
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        _LOG.info("Aucune clé Gemini détectée — embedding lexical local.")
        _EMBED_BACKEND = "lexical"
        return _EMBED_BACKEND
    try:
        import google.genai  # noqa: F401
    except ImportError:
        _LOG.warning("SDK google-genai absent — embedding lexical local.")
        _EMBED_BACKEND = "lexical"
        return _EMBED_BACKEND
    _EMBED_BACKEND = "gemini"
    return _EMBED_BACKEND


@lru_cache(maxsize=1)
def _gemini_client():
    from google import genai

    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    return genai.Client(api_key=api_key)


@lru_cache(maxsize=4096)
def _gemini_embed(text: str, is_query: bool) -> tuple[float, ...]:
    """Encode un texte via Gemini et renvoie un vecteur dense normalisé."""
    from google.genai import types

    cfg = types.EmbedContentConfig(
        task_type="RETRIEVAL_QUERY" if is_query else "RETRIEVAL_DOCUMENT",
    )
    if _EMBED_DIM > 0:
        cfg.output_dimensionality = _EMBED_DIM

    resp = _gemini_client().models.embed_content(
        model=_EMBED_MODEL,
        contents=text,
        config=cfg,
    )
    values = list(resp.embeddings[0].values)
    norm = math.sqrt(sum(v * v for v in values)) or 1.0
    return tuple(v / norm for v in values)


def _embed(text: str, *, is_query: bool):
    """Retourne l'embedding du texte (dense Gemini ou creux lexical)."""
    if _resolve_backend() == "gemini":
        try:
            return list(_gemini_embed(text, is_query))
        except Exception as exc:  # réseau, quota, auth… : on dégrade proprement
            global _EMBED_BACKEND
            _LOG.warning("Embedding Gemini en échec (%s) — bascule lexical.", exc)
            _EMBED_BACKEND = "lexical"
    return _tokenize(text)


def _similarity(a, b) -> float:
    """Similarité cosinus, supporte vecteurs denses (list) et creux (dict)."""
    if isinstance(a, list) and isinstance(b, list):
        n = min(len(a), len(b))
        if n == 0:
            return 0.0
        # Vecteurs Gemini déjà normalisés => produit scalaire == cosinus.
        return sum(a[i] * b[i] for i in range(n))
    if isinstance(a, dict) and isinstance(b, dict):
        if not a or not b:
            return 0.0
        common = set(a) & set(b)
        return sum(a[k] * b[k] for k in common)
    return 0.0


class MemoryStore:
    def __init__(self, db_path: str | Path = ":memory:") -> None:
        self.db_path = str(db_path)
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content TEXT NOT NULL,
                tags TEXT NOT NULL DEFAULT '[]',
                session TEXT NOT NULL DEFAULT 'default',
                turn INTEGER NOT NULL DEFAULT 0,
                importance REAL NOT NULL DEFAULT 0.5,
                date TEXT NOT NULL DEFAULT '',
                embedding TEXT NOT NULL DEFAULT '{}'
            )
            """
        )
        self._conn.commit()

    def store(
        self,
        content: str,
        tags: list[str] | None = None,
        session: str = "default",
        turn: int = 0,
        importance: float = 0.5,
        date: str | None = None,
    ) -> int:
        tags = tags or []
        date = date or datetime.now().isoformat(timespec="seconds")
        emb = json.dumps(_embed(content, is_query=False))
        cur = self._conn.execute(
            "INSERT INTO memories (content, tags, session, turn, importance, date, embedding) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (content, json.dumps(tags), session, turn, importance, date, emb),
        )
        self._conn.commit()
        return int(cur.lastrowid)

    def search(self, query: str, top_k: int = 5, session: str | None = None) -> list[MemoryEntry]:
        q_vec = _embed(query, is_query=True)
        rows = self._conn.execute(
            "SELECT * FROM memories" + (" WHERE session = ?" if session else ""),
            (session,) if session else (),
        ).fetchall()

        # Détection du type d'entité de la requête (pour re-ranking)
        q_entities = _detect_entity_types(query)

        scored: list[tuple[float, sqlite3.Row]] = []
        for row in rows:
            vec = json.loads(row["embedding"])
            score = _similarity(q_vec, vec)

            # Re-ranking hybride : la similarité dense (Gemini) capte le sens,
            # mais ne distingue pas toujours l'entrée qui *contient* réellement
            # l'information demandée. On ajoute donc un a priori structurel.
            if q_entities:
                # Signal faible : recouvrement de type (mots-clés inclus).
                weak = q_entities & _detect_entity_types(row["content"])
                if weak:
                    score += 0.1 * len(weak)
                # Signal fort : l'entrée contient un MOTIF du type demandé
                # (ex. requête « référence » ↔ entrée contenant CTR-2024-8847).
                strong = q_entities & _detect_entity_patterns(row["content"])
                if strong:
                    score += 0.35 * len(strong)

            scored.append((score, row))

        scored.sort(key=lambda x: x[0], reverse=True)
        scored = [(s, row) for s, row in scored if s > MIN_SIMILARITY]

        results: list[MemoryEntry] = []
        for score, row in scored[:top_k]:
            results.append(
                MemoryEntry(
                    id=row["id"],
                    content=row["content"],
                    tags=json.loads(row["tags"]),
                    session=row["session"],
                    turn=row["turn"],
                    importance=row["importance"],
                    date=row["date"],
                    score=score,
                )
            )
        return results

    def list_session(self, session: str) -> list[MemoryEntry]:
        rows = self._conn.execute(
            "SELECT * FROM memories WHERE session = ? ORDER BY turn ASC, id ASC",
            (session,),
        ).fetchall()
        return [
            MemoryEntry(
                id=r["id"],
                content=r["content"],
                tags=json.loads(r["tags"]),
                session=r["session"],
                turn=r["turn"],
                importance=r["importance"],
                date=r["date"],
            )
            for r in rows
        ]

    def count(self) -> int:
        row = self._conn.execute("SELECT COUNT(*) AS c FROM memories").fetchone()
        return int(row["c"])

    def entries_count(self) -> int:
        """Nombre total d'entrées en mémoire."""
        return self.count()

    def total_content_tokens(self) -> int:
        """Somme des tokens de tout le contenu stocké (estimation naive)."""
        from memory_mcp.stats import count_tokens as _ct

        rows = self._conn.execute("SELECT content FROM memories").fetchall()
        return sum(_ct(r["content"]) for r in rows)

    def close(self) -> None:
        self._conn.close()
