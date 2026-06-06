"""Stockage SQLite + recherche par similarité cosinus (embeddings sémantiques)."""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from memory_mcp.embeddings import cosine_similarity, embed

MIN_SIMILARITY = 0.01
_NOISE_MARKERS = re.compile(r"\b(bruit|hors-sujet|noise|football tennis météo)\b", re.IGNORECASE)
_FILLER_MARKERS = re.compile(r"précision contextuelle pour le tour|Message détaillé numéro", re.IGNORECASE)
_EMAIL = re.compile(r"[\w.+-]+@[\w.-]+\.\w+", re.IGNORECASE)
_CONTRACT = re.compile(r"CTR-\d{4}-\d+", re.IGNORECASE)
_AMOUNT = re.compile(r"\d+[,.]\d{2}\s*€")
_DATE = re.compile(
    r"\b\d{1,2}\s+(?:janvier|février|fevrier|mars|avril|mai|juin|juillet|août|aout|"
    r"septembre|octobre|novembre|décembre|decembre)\b",
    re.IGNORECASE,
)


@dataclass
class MemoryEntry:
    id: int
    content: str
    tags: list[str]
    session: str
    turn: int
    score: float = 0.0


def _rank_score(base_score: float, query: str, content: str, tags: list[str]) -> float:
    """Réordonne les résultats : favorise les faits, pénalise le bruit."""
    score = base_score
    if "noise" in tags or _NOISE_MARKERS.search(content):
        score *= 0.35
    if _FILLER_MARKERS.search(content):
        score *= 0.45
    if "fact" in tags or "client" in tags:
        score *= 1.12
    if "client" in tags and any(
        token in query.lower() for token in ("identité", "interlocut", "cliente", "client")
    ):
        score *= 1.25
    if "user" in tags and any(
        token in query.lower() for token in ("identité", "interlocut", "contact", "qui")
    ):
        score *= 1.1
    q = query.lower()
    if _EMAIL.search(content) and any(t in q for t in ("contact", "email", "coordonn", "électron", "mail")):
        score *= 1.35
    if _CONTRACT.search(content) and any(t in q for t in ("contrat", "référence", "reference", "dossier", "légal")):
        score *= 1.35
    if _AMOUNT.search(content) and any(t in q for t in ("facture", "tarif", "écart", "ecart", "prix", "montant")):
        score *= 1.35
    if _DATE.search(content) and any(t in q for t in ("incident", "bug", "mobile", "date", "signalé", "signale")):
        score *= 1.35
    return score


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
        emb = json.dumps(embed(content))
        cur = self._conn.execute(
            "INSERT INTO memories (content, tags, session, turn, embedding) VALUES (?, ?, ?, ?, ?)",
            (content, json.dumps(tags), session, turn, emb),
        )
        self._conn.commit()
        return int(cur.lastrowid)

    def search(self, query: str, top_k: int = 5, session: str | None = None) -> list[MemoryEntry]:
        q_vec = embed(query)
        rows = self._conn.execute(
            "SELECT * FROM memories" + (" WHERE session = ?" if session else ""),
            (session,) if session else (),
        ).fetchall()

        scored: list[tuple[float, sqlite3.Row]] = []
        for row in rows:
            vec = json.loads(row["embedding"])
            tags = json.loads(row["tags"])
            raw = cosine_similarity(q_vec, vec)
            score = _rank_score(raw, query, row["content"], tags)
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

    def close(self) -> None:
        self._conn.close()
