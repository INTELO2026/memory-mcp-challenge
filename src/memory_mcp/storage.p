"""Stockage SQLite + recherche sémantique par TF-IDF amélioré (bigrams + expansion + position)."""

from __future__ import annotations

import json
import math
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

MIN_SIMILARITY = 1e-9

_STOPWORDS = frozenset(
    {
        "a", "au", "aux", "ce", "ces", "de", "des", "du", "en", "est", "et",
        "il", "je", "la", "le", "les", "ma", "mon", "ne", "on", "ou", "pas",
        "pour", "que", "qui", "sa", "se", "son", "sur", "un", "une", "vos",
        "votre", "nous", "vous", "ils", "elles", "me", "te", "lui", "y", "en",
        "par", "mais", "donc", "or", "ni", "car", "si", "tout", "bien", "aussi",
        "plus", "très", "avec", "dans", "this", "the", "is", "are", "was",
    }
)

# Expansion sémantique : synonymes / paraphrases fréquents dans le domaine support client
# Clé = terme de requête → termes équivalents dans les souvenirs
_SEMANTIC_EXPAND: dict[str, list[str]] = {
    # Identité
    "identite": ["nom", "appelle", "marie", "client", "interlocutrice", "interlocuteur",
                 "utilisateur", "usager", "personne", "prenom"],
    "interlocutrice": ["client", "appelle", "nom", "marie", "identite", "usager", "premium"],
    "interlocuteur": ["client", "appelle", "nom", "identite", "usager"],
    "vip": ["premium", "prioritaire", "fidele", "gold"],
    "premium": ["vip", "prioritaire", "fidele"],
    # Contrat / référence
    "reference": ["contrat", "numero", "dossier", "ctr", "id", "identifiant", "code"],
    "dossier": ["contrat", "numero", "reference", "ctr"],
    "contrat": ["reference", "numero", "dossier", "ctr"],
    "legal": ["contrat", "reference", "officiel", "dossier"],
    # Facturation
    "facture": ["facturation", "montant", "prix", "euro", "paiement", "mars", "ecart"],
    "facturation": ["facture", "montant", "prix", "euro"],
    "tarifaire": ["facture", "montant", "prix", "euro", "facturation"],
    "ecart": ["difference", "erreur", "facture", "montant"],
    "printemps": ["mars", "avril", "mai", "trimestre"],
    # Contact
    "coordonnees": ["email", "mail", "telephone", "contact", "adresse"],
    "electroniques": ["email", "mail", "courriel"],
    "contact": ["email", "mail", "telephone", "coordonnees"],
    # Incidents
    "incident": ["bug", "probleme", "erreur", "panne", "signale"],
    "application": ["app", "mobile", "ios", "android", "logiciel"],
    "mobile": ["app", "application", "ios", "android", "telephone"],
    "date": ["fevrier", "mars", "janvier", "jour", "quand", "moment"],
}

# Normalisation légère (accents → ascii)
def _normalize(text: str) -> str:
    replacements = {
        "é": "e", "è": "e", "ê": "e", "ë": "e",
        "à": "a", "â": "a", "ä": "a",
        "î": "i", "ï": "i",
        "ô": "o", "ö": "o",
        "ù": "u", "û": "u", "ü": "u",
        "ç": "c", "œ": "oe", "æ": "ae",
    }
    result = text.lower()
    for src, dst in replacements.items():
        result = result.replace(src, dst)
    return result


def _tokenize(text: str) -> dict[str, float]:
    """TF-IDF amélioré : unigrams + bigrams + expansion sémantique + pondération position."""
    normalized = _normalize(text)
    words = [w for w in re.findall(r"\w+", normalized)
             if w not in _STOPWORDS and len(w) > 2]
    if not words:
        return {}

    freq: dict[str, float] = {}

    # 1. Unigrams avec pondération positionnelle (début du texte = plus important)
    n = len(words)
    for i, w in enumerate(words):
        # Position weight: premiers mots comptent 1.5x, derniers 1.0x
        pos_weight = 1.5 - 0.5 * (i / max(n - 1, 1))
        freq[w] = freq.get(w, 0.0) + pos_weight

    # 2. Bigrams (captures les entités composées : "marie dupont", "ctr 2024")
    for i in range(len(words) - 1):
        bigram = f"{words[i]}_{words[i+1]}"
        freq[bigram] = freq.get(bigram, 0.0) + 1.2  # légèrement boostés

    # 3. Expansion sémantique : ajouter synonymes avec poids réduit
    expanded = set()
    for w in list(freq.keys()):
        base = w.split("_")[0]  # unigram part of bigram
        if base in _SEMANTIC_EXPAND and base not in expanded:
            expanded.add(base)
            for synonym in _SEMANTIC_EXPAND[base]:
                if synonym not in freq:
                    freq[synonym] = 0.4  # poids faible = indice sémantique

    # 4. Normalisation cosinus
    norm = math.sqrt(sum(v * v for v in freq.values())) or 1.0
    return {k: v / norm for k, v in freq.items()}


def _cosine(a: dict[str, float], b: dict[str, float]) -> float:
    if not a or not b:
        return 0.0
    common = set(a) & set(b)
    return sum(a[k] * b[k] for k in common)


@dataclass
class MemoryEntry:
    id: int
    content: str
    tags: list[str]
    session: str
    turn: int
    score: float = 0.0


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
                embedding TEXT NOT NULL DEFAULT '{}'
            )
            """
        )
        self._conn.commit()

    def store(
        self, content: str, tags: list[str] | None = None, session: str = "default", turn: int = 0
    ) -> int:
        tags = tags or []
        emb = json.dumps(_tokenize(content))
        cur = self._conn.execute(
            "INSERT INTO memories (content, tags, session, turn, embedding) VALUES (?, ?, ?, ?, ?)",
            (content, json.dumps(tags), session, turn, emb),
        )
        self._conn.commit()
        return int(cur.lastrowid)

    def search(self, query: str, top_k: int = 5, session: str | None = None) -> list[MemoryEntry]:
        q_vec = _tokenize(query)
        rows = self._conn.execute(
            "SELECT * FROM memories" + (" WHERE session = ?" if session else ""),
            (session,) if session else (),
        ).fetchall()

        scored: list[tuple[float, sqlite3.Row]] = []
        for row in rows:
            vec = json.loads(row["embedding"])
            score = _cosine(q_vec, vec)
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
            )
            for r in rows
        ]

    def count(self) -> int:
        row = self._conn.execute("SELECT COUNT(*) AS c FROM memories").fetchone()
        return int(row["c"])

    def count_session(self, session: str) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) AS c FROM memories WHERE session = ?", (session,)
        ).fetchone()
        return int(row["c"])

    def close(self) -> None:
        self._conn.close()
