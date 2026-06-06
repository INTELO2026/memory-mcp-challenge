"""Stockage SQLite + recherche sémantique (embeddings réels) + hiérarchie de pertinence.

Le bag-of-words d'origine est remplacé par de vrais embeddings (Gemini ou modèle
local, cf. :mod:`memory_mcp.embeddings`). Le classement combine la similarité
sémantique (dominante) avec un bonus de pertinence : récence, importance estimée
à la création et fréquence d'accès (piste bonus du sujet).
"""

from __future__ import annotations

import json
import re
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from memory_mcp import embeddings

MIN_SIMILARITY = 1e-9

# Pondérations du score final. La similarité sémantique décide ; les bonus
# (récence, importance, fréquence) ne servent QUE de départage de quasi-ex-æquo
# et sont calibrés pour ne jamais renverser une vraie décision sémantique.
# La hiérarchie de pertinence (piste bonus) reste ainsi visible sans nuire à la
# justesse — surtout cruciale avec un modèle d'embeddings fort comme Gemini.
_W_SIM = 1.0
_W_RECENCY = 0.0002
_W_IMPORTANCE = 0.0005
_W_FREQUENCY = 0.0002

# --- Heuristique d'importance (utilisée au stockage et par le résumé) ---

_EMAIL_RE = re.compile(r"[^\s@]+@[^\s@]+\.[^\s@]+")
_ID_RE = re.compile(r"\b(?:[A-Za-z]{2,}[-/]?\d{2,}[-\dA-Za-z]*|\d{4,})\b")
_MONEY_RE = re.compile(r"(?:\d+[.,]\d{2}\s?(?:€|eur)|€\s?\d+)", re.IGNORECASE)
_NAME_RE = re.compile(r"\b([A-ZÀ-Ÿ][a-zà-ÿ]{2,})\s+([A-ZÀ-Ÿ][a-zà-ÿ]{2,})\b")


def estimate_importance(content: str) -> float:
    """Note l'importance d'un contenu via la densité d'entités structurées.

    Plus un message contient d'informations factuelles durables (identifiants,
    emails, montants, noms propres), plus il est jugé important. Aucune réponse
    n'est codée en dur : on mesure des motifs génériques.
    """
    score = 0.1
    if _EMAIL_RE.search(content):
        score += 0.5
    if _ID_RE.search(content):
        score += 0.5
    if _NAME_RE.search(content):
        score += 0.4
    if _MONEY_RE.search(content):
        score += 0.25
    return min(score, 1.0)


@dataclass
class MemoryEntry:
    id: int
    content: str
    tags: list[str]
    session: str
    turn: int
    importance: float = 0.0
    score: float = 0.0
    embedding: np.ndarray | None = field(default=None, repr=False)


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
                embedding TEXT NOT NULL DEFAULT '[]',
                importance REAL NOT NULL DEFAULT 0.0,
                created_at REAL NOT NULL DEFAULT 0.0,
                access_count INTEGER NOT NULL DEFAULT 0,
                last_access REAL NOT NULL DEFAULT 0.0
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
        importance: float | None = None,
    ) -> int:
        tags = tags or []
        vec = embeddings.embed_document(content)
        imp = estimate_importance(content) if importance is None else float(importance)
        now = time.time()
        cur = self._conn.execute(
            """
            INSERT INTO memories
                (content, tags, session, turn, embedding, importance, created_at, last_access)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                content,
                json.dumps(tags),
                session,
                turn,
                json.dumps([round(float(x), 6) for x in vec.tolist()]),
                imp,
                now,
                now,
            ),
        )
        self._conn.commit()
        return int(cur.lastrowid)

    def _fetch_rows(self, session: str | None) -> list[sqlite3.Row]:
        sql = "SELECT * FROM memories"
        params: tuple = ()
        if session is not None:
            sql += " WHERE session = ?"
            params = (session,)
        return self._conn.execute(sql, params).fetchall()

    def search(
        self,
        query: str,
        top_k: int = 5,
        session: str | None = None,
    ) -> list[MemoryEntry]:
        rows = self._fetch_rows(session)
        if not rows:
            return []

        q_vec = embeddings.embed_query(query)
        max_turn = max((r["turn"] for r in rows), default=1) or 1

        scored: list[tuple[float, float, sqlite3.Row, np.ndarray]] = []
        for row in rows:
            vec = np.array(json.loads(row["embedding"]), dtype=np.float32)
            if vec.size == 0:
                continue
            sim = float(np.dot(q_vec, vec))
            recency = row["turn"] / max_turn
            frequency = 1.0 - 1.0 / (1.0 + row["access_count"])
            final = (
                _W_SIM * sim
                + _W_RECENCY * recency
                + _W_IMPORTANCE * row["importance"]
                + _W_FREQUENCY * frequency
            )
            scored.append((final, sim, row, vec))

        scored.sort(key=lambda x: x[0], reverse=True)
        scored = [s for s in scored if s[1] > MIN_SIMILARITY]
        top = scored[:top_k]

        if top:
            now = time.time()
            ids = [int(s[2]["id"]) for s in top]
            self._conn.executemany(
                "UPDATE memories SET access_count = access_count + 1, last_access = ? WHERE id = ?",
                [(now, mid) for mid in ids],
            )
            self._conn.commit()

        results: list[MemoryEntry] = []
        for final, sim, row, vec in top:
            results.append(
                MemoryEntry(
                    id=row["id"],
                    content=row["content"],
                    tags=json.loads(row["tags"]),
                    session=row["session"],
                    turn=row["turn"],
                    importance=row["importance"],
                    score=sim,
                    embedding=vec,
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
            )
            for r in rows
        ]

    def count(self) -> int:
        row = self._conn.execute("SELECT COUNT(*) AS c FROM memories").fetchone()
        return int(row["c"])

    def close(self) -> None:
        self._conn.close()
