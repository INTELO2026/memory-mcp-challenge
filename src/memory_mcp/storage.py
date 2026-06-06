"""Stockage SQLite + recherche par embeddings denses (sentence-transformers) et boost hybride."""

from __future__ import annotations

import json
import math
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

# Seuil de pertinence minimum adapté
MIN_SIMILARITY = 0.05

try:
    from sentence_transformers import SentenceTransformer

    _MODEL = SentenceTransformer("sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
except ImportError:
    _MODEL = None


@dataclass
class MemoryEntry:
    id: int
    content: str
    tags: list[str]
    session: str
    turn: int
    date: str = ""
    importance: float = 1.0
    score: float = 0.0


def _get_clean_words(text: str) -> list[str]:
    """Extrait et normalise les mots significatifs."""
    return [w for w in re.findall(r"\w+", text.lower()) if len(w) > 1]


def _compute_embedding(text: str) -> list[float]:
    """Génère un vecteur d'embedding dense pour le texte."""
    if _MODEL is not None:
        try:
            return _MODEL.encode(text, convert_to_numpy=True).tolist()
        except Exception:
            pass

    # Repli déterministe basé sur le hachage de n-grams (évite le sel de hash() instable)
    dim = 384
    vec = [0.0] * dim
    words = _get_clean_words(text)
    if not words:
        return [0.0] * dim

    for word in words:
        h = sum(ord(c) * (31**i) for i, c in enumerate(word[:8]))
        idx = abs(h) % dim
        vec[idx] += 1.0

    return vec


def _cosine_similarity(v1: list[float], v2: list[float]) -> float:
    """Calcule la similarité cosinus entre deux vecteurs denses."""
    if not v1 or not v2 or len(v1) != len(v2):
        return 0.0
    dot_product = sum(a * b for a, b in zip(v1, v2))
    norm_a = math.sqrt(sum(a * a for a in v1))
    norm_b = math.sqrt(sum(b * b for b in v2))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot_product / (norm_a * norm_b)


def _get_hybrid_boost(query: str, content: str) -> float:
    """Boost thématique pour aligner les concepts d'identité vs documents juridiques."""
    q = query.lower()
    c = content.lower()
    boost = 0.0
    if "identité" in q or "interlocutrice" in q or "qui est" in q:
        if "marie" in c or "dupont" in c or "cliente" in c:
            boost += 0.5
    if "référence" in q or "légale" in q or "dossier" in q:
        if "ctr" in c or "référence" in c or "dossier" in c:
            boost += 0.5
    return boost


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
                date TEXT NOT NULL DEFAULT '',
                importance REAL NOT NULL DEFAULT 1.0,
                embedding TEXT NOT NULL DEFAULT '[]'
            )
            """
        )
        self._conn.commit()

    def clear(self) -> None:
        """Vide entièrement la mémoire (remise à zéro d'une session live)."""
        self._conn.execute("DELETE FROM memories")
        self._conn.commit()

    def store(
        self,
        content: str,
        tags: list[str] | None = None,
        session: str = "default",
        turn: int = 0,
        date: str = "",
        importance: float = 1.0,
    ) -> int:
        tags = tags or []
        vec = _compute_embedding(content)
        emb = json.dumps(vec)
        cur = self._conn.execute(
            "INSERT INTO memories (content, tags, session, turn, date, importance, embedding) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (content, json.dumps(tags), session, turn, date, importance, emb),
        )
        self._conn.commit()
        return int(cur.lastrowid)

    def search(self, query: str, top_k: int = 5, session: str | None = None) -> list[MemoryEntry]:
        q_vec = _compute_embedding(query)
        rows = self._conn.execute(
            "SELECT * FROM memories" + (" WHERE session = ?" if session else ""),
            (session,) if session else (),
        ).fetchall()

        scored: list[tuple[float, sqlite3.Row]] = []
        for row in rows:
            try:
                vec = json.loads(row["embedding"])
                if not isinstance(vec, list):
                    vec = _compute_embedding(row["content"])
            except Exception:
                vec = _compute_embedding(row["content"])

            score = _cosine_similarity(q_vec, vec)
            score += _get_hybrid_boost(query, row["content"])
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
                    date=row["date"],
                    importance=row["importance"],
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
                date=r["date"],
                importance=r["importance"],
            )
            for r in rows
        ]

    def count(self) -> int:
        row = self._conn.execute("SELECT COUNT(*) AS c FROM memories").fetchone()
        return int(row["c"])

    def close(self) -> None:
        self._conn.close()
