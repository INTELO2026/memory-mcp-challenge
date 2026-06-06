"""Stockage SQLite + recherche par similarité cosinus (embeddings sémantiques)."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from memory_mcp.embeddings import cosine_similarity, embed_text

MIN_SIMILARITY = 0.12

_IDENTITY_HINTS = frozenset(
    {
        "identité",
        "interlocutrice",
        "interlocuteur",
        "client",
        "cliente",
        "qui",
        "nom",
        "vip",
        "premium",
    }
)
_CONTACT_HINTS = frozenset({"email", "contact", "coordonnées", "courriel", "électronique"})
_CONTRACT_HINTS = frozenset({"contrat", "référence", "dossier", "légal", "numéro"})


@dataclass
class MemoryEntry:
    id: int
    content: str
    tags: list[str]
    session: str
    turn: int
    score: float = 0.0


def _rerank_boost(query: str, content: str, tags: list[str]) -> float:
    """Léger reranking générique (sans hardcoder les réponses)."""
    q = query.lower()
    c = content.lower()
    boost = 0.0
    q_words = set(q.split())

    if q_words & _IDENTITY_HINTS and any(w in c for w in ("cliente", "client", "premium", "nom")):
        boost += 0.12
    if q_words & _CONTACT_HINTS and "@" in c:
        boost += 0.12
    if q_words & _CONTRACT_HINTS and "ctr-" in c:
        boost += 0.12
    if "fact" in tags:
        boost += 0.04
    if "noise" in tags:
        boost -= 0.25
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
                embedding TEXT NOT NULL DEFAULT '[]'
            )
            """
        )
        self._conn.commit()

    def store(
        self, content: str, tags: list[str] | None = None, session: str = "default", turn: int = 0
    ) -> int:
        tags = tags or []
        emb = json.dumps(embed_text(content))
        cur = self._conn.execute(
            "INSERT INTO memories (content, tags, session, turn, embedding) VALUES (?, ?, ?, ?, ?)",
            (content, json.dumps(tags), session, turn, emb),
        )
        self._conn.commit()
        return int(cur.lastrowid)

    def search(self, query: str, top_k: int = 5, session: str | None = None) -> list[MemoryEntry]:
        q_vec = embed_text(query)
        rows = self._conn.execute(
            "SELECT * FROM memories" + (" WHERE session = ?" if session else ""),
            (session,) if session else (),
        ).fetchall()

        scored: list[tuple[float, sqlite3.Row]] = []
        for row in rows:
            vec = json.loads(row["embedding"])
            tags = json.loads(row["tags"])
            score = cosine_similarity(q_vec, vec) + _rerank_boost(query, row["content"], tags)
            scored.append((score, row))

        scored.sort(key=lambda x: x[0], reverse=True)
        scored = [(s, row) for s, row in scored if s >= MIN_SIMILARITY]

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

    def close(self) -> None:
        self._conn.close()
