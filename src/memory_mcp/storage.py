"""Stockage SQLite + recherche sémantique par embeddings réels.

Remplace l'ancien bag-of-words par de vrais embeddings (voir ``embeddings.py``). Chaque
souvenir porte aussi des métadonnées de *hiérarchie de pertinence* — importance, récence,
fréquence d'accès — qui alimentent le tri avancé et l'oubli intelligent.

La recherche reste **dominée par la similarité sémantique** (le bruit récent ne doit jamais
voler la première place d'un fait pertinent). La hiérarchie est un ré-ordonnancement *opt-in*.
"""

from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path

from memory_mcp.embeddings import Embedder, cosine, get_embedder
from memory_mcp.salience import importance_score

MIN_SIMILARITY = 1e-6


@dataclass
class MemoryEntry:
    id: int
    content: str
    tags: list[str]
    session: str
    turn: int
    score: float = 0.0
    importance: float = 0.0
    access_count: int = 0
    created_at: float = 0.0
    rank_score: float = 0.0
    embedding: list[float] = field(default_factory=list, repr=False)


class MemoryStore:
    def __init__(self, db_path: str | Path = ":memory:", embedder: Embedder | None = None) -> None:
        self.db_path = str(db_path)
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._embedder = embedder
        self._init_schema()

    # --- embedder paresseux (évite de charger le modèle si inutile) ---
    @property
    def embedder(self) -> Embedder:
        if self._embedder is None:
            self._embedder = get_embedder()
        return self._embedder

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
                access_count INTEGER NOT NULL DEFAULT 0,
                created_at REAL NOT NULL DEFAULT 0.0,
                last_access REAL NOT NULL DEFAULT 0.0
            )
            """
        )
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_session ON memories(session)")
        self._conn.commit()

    # ------------------------------------------------------------------ store
    def store(
        self,
        content: str,
        tags: list[str] | None = None,
        session: str = "default",
        turn: int = 0,
        importance: float | None = None,
    ) -> int:
        tags = tags or []
        vec = self.embedder.embed([content])[0]
        imp = importance_score(content) if importance is None else float(importance)
        now = time.time()
        cur = self._conn.execute(
            """
            INSERT INTO memories
                (content, tags, session, turn, embedding, importance, created_at, last_access)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (content, json.dumps(tags), session, turn, json.dumps(vec), imp, now, now),
        )
        self._conn.commit()
        return int(cur.lastrowid)

    # ----------------------------------------------------------------- search
    def search(
        self,
        query: str,
        top_k: int = 5,
        session: str | None = None,
        use_hierarchy: bool = False,
        touch: bool = True,
    ) -> list[MemoryEntry]:
        """Recherche sémantique. Si ``use_hierarchy`` : petit bonus récence/importance/fréquence
        ajouté au cosinus (sans jamais dominer la sémantique)."""
        q_vec = self.embedder.embed([query])[0]
        rows = self._conn.execute(
            "SELECT * FROM memories" + (" WHERE session = ?" if session else ""),
            (session,) if session else (),
        ).fetchall()
        if not rows:
            return []

        now = time.time()
        max_access = max((r["access_count"] for r in rows), default=1) or 1

        scored: list[tuple[float, float, sqlite3.Row, list[float]]] = []
        for row in rows:
            vec = json.loads(row["embedding"])
            sim = cosine(q_vec, vec)
            rank = sim
            if use_hierarchy:
                # Pour le *retrieval*, on privilégie l'importance factuelle et la fréquence
                # d'accès. On n'ajoute PAS de bonus de récence : il défavoriserait les faits
                # anciens (nom, contrat…) au profit du bavardage récent.
                freq = row["access_count"] / max_access
                rank = sim + 0.10 * row["importance"] + 0.03 * freq
            scored.append((rank, sim, row, vec))

        scored.sort(key=lambda x: x[0], reverse=True)
        scored = [s for s in scored if s[1] > MIN_SIMILARITY]

        results: list[MemoryEntry] = []
        hit_ids: list[int] = []
        for rank, sim, row, vec in scored[:top_k]:
            hit_ids.append(row["id"])
            results.append(
                MemoryEntry(
                    id=row["id"],
                    content=row["content"],
                    tags=json.loads(row["tags"]),
                    session=row["session"],
                    turn=row["turn"],
                    score=sim,
                    importance=row["importance"],
                    access_count=row["access_count"],
                    created_at=row["created_at"],
                    rank_score=rank,
                    embedding=vec,
                )
            )

        if touch and hit_ids:
            self._conn.executemany(
                "UPDATE memories SET access_count = access_count + 1, last_access = ? WHERE id = ?",
                [(now, mid) for mid in hit_ids],
            )
            self._conn.commit()
        return results

    # --------------------------------------------------------------- sessions
    def _row_to_entry(self, r: sqlite3.Row) -> MemoryEntry:
        return MemoryEntry(
            id=r["id"],
            content=r["content"],
            tags=json.loads(r["tags"]),
            session=r["session"],
            turn=r["turn"],
            importance=r["importance"],
            access_count=r["access_count"],
            created_at=r["created_at"],
        )

    def list_session(self, session: str) -> list[MemoryEntry]:
        rows = self._conn.execute(
            "SELECT * FROM memories WHERE session = ? ORDER BY turn ASC, id ASC",
            (session,),
        ).fetchall()
        return [self._row_to_entry(r) for r in rows]

    def ranked_session(self, session: str, top_k: int | None = None) -> list[MemoryEntry]:
        """Souvenirs triés par hiérarchie de pertinence (importance × récence × fréquence)."""
        entries = self.list_session(session)
        if not entries:
            return []
        max_turn = max(e.turn for e in entries) or 1
        max_access = max((e.access_count for e in entries), default=1) or 1
        for e in entries:
            recency = e.turn / max_turn
            freq = e.access_count / max_access
            e.rank_score = round(0.6 * e.importance + 0.25 * recency + 0.15 * freq, 4)
        entries.sort(key=lambda e: e.rank_score, reverse=True)
        return entries[:top_k] if top_k else entries

    def sessions(self) -> list[str]:
        rows = self._conn.execute(
            "SELECT DISTINCT session FROM memories ORDER BY session"
        ).fetchall()
        return [r["session"] for r in rows]

    # ------------------------------------------------------------- forgetting
    def forget_redundant(self, session: str, similarity_threshold: float = 0.93) -> int:
        """Oubli intelligent : supprime les souvenirs quasi-dupliqués (garde le plus important)."""
        entries = self._conn.execute(
            "SELECT * FROM memories WHERE session = ? ORDER BY importance DESC, turn ASC",
            (session,),
        ).fetchall()
        kept: list[list[float]] = []
        to_delete: list[int] = []
        for row in entries:
            vec = json.loads(row["embedding"])
            if any(cosine(vec, k) >= similarity_threshold for k in kept):
                to_delete.append(row["id"])
            else:
                kept.append(vec)
        if to_delete:
            self._conn.executemany("DELETE FROM memories WHERE id = ?", [(i,) for i in to_delete])
            self._conn.commit()
        return len(to_delete)

    def count(self, session: str | None = None) -> int:
        if session:
            row = self._conn.execute(
                "SELECT COUNT(*) AS c FROM memories WHERE session = ?", (session,)
            ).fetchone()
        else:
            row = self._conn.execute("SELECT COUNT(*) AS c FROM memories").fetchone()
        return int(row["c"])

    def close(self) -> None:
        self._conn.close()
