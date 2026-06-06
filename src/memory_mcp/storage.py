"""Stockage SQLite + recherche sémantique via un moteur d'embeddings enfichable."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from memory_mcp.embeddings import get_embedder, lexical_overlap

# Seuil minimal de pertinence : sous ce score, un résultat est écarté comme bruit.
MIN_SIMILARITY = 0.01

# Poids du réordonnancement hybride : la similarité dense domine, le recouvrement
# lexical de surface ne sert qu'à départager des candidats quasi à égalité.
LEXICAL_WEIGHT = 0.10


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
                embedding TEXT NOT NULL DEFAULT '{}',
                access_count INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        # Migration douce pour les bases sur disque créées avant access_count.
        cols = {r["name"] for r in self._conn.execute("PRAGMA table_info(memories)")}
        if "access_count" not in cols:
            self._conn.execute(
                "ALTER TABLE memories ADD COLUMN access_count INTEGER NOT NULL DEFAULT 0"
            )
        self._conn.commit()

    def store(
        self, content: str, tags: list[str] | None = None, session: str = "default", turn: int = 0
    ) -> int:
        tags = tags or []
        emb = json.dumps(get_embedder().encode(content))
        cur = self._conn.execute(
            "INSERT INTO memories (content, tags, session, turn, embedding) VALUES (?, ?, ?, ?, ?)",
            (content, json.dumps(tags), session, turn, emb),
        )
        self._conn.commit()
        return int(cur.lastrowid)

    def search(
        self,
        query: str,
        top_k: int = 5,
        session: str | None = None,
        *,
        shared_session: str | None = None,
        recency_weight: float = 0.0,
        frequency_weight: float = 0.0,
    ) -> list[MemoryEntry]:
        """Recherche sémantique, avec hiérarchie de pertinence optionnelle.

        Par défaut (poids à 0) le classement est purement sémantique. Les poids
        ``recency_weight`` (récence du tour) et ``frequency_weight`` (fréquence
        d'accès passée) permettent un tri hiérarchique (§10). ``shared_session``
        élargit la recherche à un espace mémoire commun à plusieurs agents.
        """
        embedder = get_embedder()
        q_vec = embedder.encode_query(query)

        if session and shared_session:
            where, params = " WHERE session IN (?, ?)", (session, shared_session)
        elif session:
            where, params = " WHERE session = ?", (session,)
        else:
            where, params = "", ()
        rows = self._conn.execute("SELECT * FROM memories" + where, params).fetchall()

        max_turn = max((r["turn"] for r in rows), default=0) or 1
        max_access = max((r["access_count"] for r in rows), default=0) or 1

        scored: list[tuple[float, sqlite3.Row]] = []
        for row in rows:
            vec = json.loads(row["embedding"])
            score = embedder.similarity(q_vec, vec) + LEXICAL_WEIGHT * lexical_overlap(
                query, row["content"]
            )
            if recency_weight:
                score += recency_weight * (row["turn"] / max_turn)
            if frequency_weight:
                score += frequency_weight * (row["access_count"] / max_access)
            scored.append((score, row))

        scored.sort(key=lambda x: x[0], reverse=True)
        scored = [(s, row) for s, row in scored if s > MIN_SIMILARITY]

        results: list[MemoryEntry] = []
        hit_ids: list[int] = []
        for score, row in scored[:top_k]:
            hit_ids.append(row["id"])
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

        # Trace la fréquence d'accès (alimente la hiérarchie de pertinence).
        if hit_ids:
            placeholders = ",".join("?" * len(hit_ids))
            self._conn.execute(
                f"UPDATE memories SET access_count = access_count + 1 WHERE id IN ({placeholders})",
                hit_ids,
            )
            self._conn.commit()
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

    def prune_redundant(self, session: str, threshold: float = 0.97) -> int:
        """Oubli intelligent : supprime les souvenirs quasi redondants d'une session.

        Parcourt les souvenirs par ordre chronologique et retire ceux dont la
        similarité sémantique avec un souvenir déjà conservé dépasse ``threshold``
        (on garde le plus ancien). Retourne le nombre de souvenirs oubliés.
        """
        rows = self._conn.execute(
            "SELECT id, embedding FROM memories WHERE session = ? ORDER BY turn ASC, id ASC",
            (session,),
        ).fetchall()
        embedder = get_embedder()
        kept_vecs: list = []
        remove_ids: list[int] = []
        for row in rows:
            vec = json.loads(row["embedding"])
            if any(embedder.similarity(vec, kept) >= threshold for kept in kept_vecs):
                remove_ids.append(row["id"])
            else:
                kept_vecs.append(vec)

        if remove_ids:
            placeholders = ",".join("?" * len(remove_ids))
            self._conn.execute(f"DELETE FROM memories WHERE id IN ({placeholders})", remove_ids)
            self._conn.commit()
        return len(remove_ids)

    def count(self) -> int:
        row = self._conn.execute("SELECT COUNT(*) AS c FROM memories").fetchone()
        return int(row["c"])

    def close(self) -> None:
        self._conn.close()
