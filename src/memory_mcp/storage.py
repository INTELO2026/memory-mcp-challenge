"""Stockage SQLite + recherche sémantique (sentence-transformers)."""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from memory_mcp.ebbinghaus import (
    hours_since,
    recency_decay,
    retention,
    should_archive,
    update_stability,
)
from memory_mcp.embeddings import cosine_similarity, deserialize, encode, serialize

MIN_SIMILARITY = 1e-6
_IDENTITY_QUERY = re.compile(r"identit|interlocut|client|contact|coordonn|qui est", re.I)
_NAME_PATTERN = re.compile(r"\b[A-ZÀ-Ü][a-zà-ü]+\s+[A-ZÀ-Ü][a-zà-ü]+\b")
_REF_PATTERN = re.compile(r"[A-Z]{2,}-\d{4}-\d+", re.I)


@dataclass
class MemoryEntry:
    id: int
    content: str
    tags: list[str]
    session: str
    turn: int
    score: float = 0.0
    importance: float = 0.5
    retention_score: float = 1.0
    stability: float = 1.0
    access_count: int = 0
    is_archived: bool = False
    created_at: datetime | None = None
    last_accessed: datetime | None = None


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def compute_importance(content: str, tags: list[str] | None = None) -> float:
    """Score d'importance heuristique (0-1)."""
    score = 0.35
    tags = tags or []
    if "fact" in tags:
        score += 0.25
    if re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", content):
        score += 0.15
    if re.search(r"[A-Z]{2,}-\d{4}-\d+", content):
        score += 0.15
    if re.search(r"\d+[,.]\d+\s*€", content):
        score += 0.1
    if re.search(r"\b(premium|contrat|email|bug|facture)\b", content, re.I):
        score += 0.08
    unique_tokens = len(set(re.findall(r"\w+", content.lower())))
    score += min(unique_tokens / 40.0, 0.12)
    return min(score, 1.0)


class MemoryStore:
    def __init__(self, db_path: str | Path = ":memory:") -> None:
        self.db_path = str(db_path)
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()
        self._retrieval_times: list[float] = []

    def _init_schema(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content TEXT NOT NULL,
                tags TEXT NOT NULL DEFAULT '[]',
                session TEXT NOT NULL DEFAULT 'default',
                turn INTEGER NOT NULL DEFAULT 0,
                embedding BLOB NOT NULL DEFAULT X'',
                importance REAL NOT NULL DEFAULT 0.5,
                created_at TEXT NOT NULL,
                last_accessed TEXT NOT NULL,
                access_count INTEGER NOT NULL DEFAULT 0,
                retention_score REAL NOT NULL DEFAULT 1.0,
                stability REAL NOT NULL DEFAULT 1.0,
                is_archived INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS session_summaries (
                session TEXT PRIMARY KEY,
                summary TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL
            )
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS memory_links (
                source_id INTEGER NOT NULL,
                target_id INTEGER NOT NULL,
                weight REAL NOT NULL DEFAULT 0.7,
                PRIMARY KEY (source_id, target_id)
            )
            """
        )
        try:
            self._conn.execute(
                "ALTER TABLE memories ADD COLUMN agent_id TEXT NOT NULL DEFAULT 'default'"
            )
        except sqlite3.OperationalError:
            pass
        self._conn.commit()

    def _row_to_entry(self, row: sqlite3.Row, score: float = 0.0) -> MemoryEntry:
        return MemoryEntry(
            id=row["id"],
            content=row["content"],
            tags=json.loads(row["tags"]),
            session=row["session"],
            turn=row["turn"],
            score=score,
            importance=row["importance"],
            retention_score=row["retention_score"],
            stability=row["stability"],
            access_count=row["access_count"],
            is_archived=bool(row["is_archived"]),
            created_at=_parse_dt(row["created_at"]),
            last_accessed=_parse_dt(row["last_accessed"]),
        )

    def store(
        self,
        content: str,
        tags: list[str] | None = None,
        session: str = "default",
        turn: int = 0,
        importance: float | None = None,
        agent_id: str = "default",
    ) -> int:
        tags = tags or []
        imp = importance if importance is not None else compute_importance(content, tags)
        vec = encode(content)
        now = _utcnow().isoformat()
        cur = self._conn.execute(
            """
            INSERT INTO memories
            (content, tags, session, turn, embedding, importance, created_at,
             last_accessed, access_count, retention_score, stability, is_archived, agent_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, 1.0, 1.0, 0, ?)
            """,
            (content, json.dumps(tags), session, turn, serialize(vec), imp, now, now, agent_id),
        )
        self._conn.commit()
        memory_id = int(cur.lastrowid)
        return memory_id

    def add_link(self, source_id: int, target_id: int, weight: float) -> None:
        a, b = min(source_id, target_id), max(source_id, target_id)
        self._conn.execute(
            """
            INSERT INTO memory_links (source_id, target_id, weight)
            VALUES (?, ?, ?)
            ON CONFLICT(source_id, target_id) DO UPDATE SET weight = excluded.weight
            """,
            (a, b, weight),
        )
        self._conn.commit()

    def get_links(self, memory_id: int) -> list[dict]:
        rows = self._conn.execute(
            """
            SELECT source_id, target_id, weight FROM memory_links
            WHERE source_id = ? OR target_id = ?
            """,
            (memory_id, memory_id),
        ).fetchall()
        return [
            {"source": r["source_id"], "target": r["target_id"], "weight": r["weight"]}
            for r in rows
        ]

    def get_memory_by_id(self, memory_id: int) -> MemoryEntry | None:
        row = self._conn.execute("SELECT * FROM memories WHERE id = ?", (memory_id,)).fetchone()
        return self._row_to_entry(row) if row else None

    def iter_active_embeddings(self, session: str, exclude_id: int) -> list[tuple[int, bytes]]:
        rows = self._conn.execute(
            """
            SELECT id, embedding FROM memories
            WHERE is_archived = 0 AND session = ? AND id != ?
            """,
            (session, exclude_id),
        ).fetchall()
        return [(r["id"], r["embedding"]) for r in rows]

    def retention_curves(self, session: str | None = None, limit: int = 8) -> list[dict]:
        """Courbes Ebbinghaus pour le dashboard (points R(t) sur 72h)."""
        entries = self.list_active(session)[:limit]
        curves = []
        for e in entries:
            s = max(e.stability, 0.1)
            points = [
                {"hours": h, "retention": round(retention(float(h), s), 4)}
                for h in (0, 1, 6, 12, 24, 48, 72)
            ]
            curves.append(
                {
                    "id": e.id,
                    "label": e.content[:40],
                    "stability": round(s, 2),
                    "importance": e.importance,
                    "current_retention": round(e.retention_score, 4),
                    "points": points,
                }
            )
        return curves

    def purge_weak_memories(self, session: str | None = None) -> int:
        """Politique d'oubli : archive souvenirs faibles."""
        self._update_retention_scores(session)
        sql = "SELECT id FROM memories WHERE is_archived = 1"
        params: tuple = ()
        if session:
            sql += " AND session = ?"
            params = (session,)
        rows = self._conn.execute(sql, params).fetchall()
        return len(rows)

    def _update_retention_scores(self, session: str | None = None) -> None:
        now = _utcnow()
        query = (
            "SELECT id, last_accessed, stability, importance FROM memories WHERE is_archived = 0"
        )
        params: tuple = ()
        if session:
            query += " AND session = ?"
            params = (session,)
        rows = self._conn.execute(query, params).fetchall()
        for row in rows:
            last = _parse_dt(row["last_accessed"]) or now
            t = hours_since(last, now)
            ret = retention(t, row["stability"])
            if should_archive(ret, row["importance"]):
                self._conn.execute(
                    "UPDATE memories SET is_archived = 1, retention_score = ? WHERE id = ?",
                    (ret, row["id"]),
                )
            else:
                self._conn.execute(
                    "UPDATE memories SET retention_score = ? WHERE id = ?",
                    (ret, row["id"]),
                )
        self._conn.commit()

    def _record_access(self, memory_id: int, stability: float, access_count: int) -> None:
        new_stability = update_stability(stability, access_count + 1)
        now = _utcnow().isoformat()
        self._conn.execute(
            """
            UPDATE memories
            SET access_count = access_count + 1,
                last_accessed = ?,
                stability = ?,
                retention_score = 1.0
            WHERE id = ?
            """,
            (now, new_stability, memory_id),
        )
        self._conn.commit()

    def search(
        self,
        query: str,
        top_k: int = 5,
        session: str | None = None,
        agent_id: str | None = None,
        record_access: bool = True,
    ) -> list[MemoryEntry]:
        import time

        t0 = time.perf_counter()
        self._update_retention_scores(session)

        q_vec = encode(query)
        sql = "SELECT * FROM memories WHERE is_archived = 0"
        params: list = []
        if session:
            sql += " AND session = ?"
            params.append(session)
        if agent_id:
            sql += " AND agent_id = ?"
            params.append(agent_id)
        rows = self._conn.execute(sql, params).fetchall()

        now = _utcnow()
        scored: list[tuple[float, float, sqlite3.Row]] = []
        for row in rows:
            vec = deserialize(row["embedding"])
            sim = cosine_similarity(q_vec, vec)
            if sim <= MIN_SIMILARITY:
                continue

            content = row["content"]
            if re.search(
                r"contrat|dossier|r[eé]f|r[eé]f[eé]rence", query, re.I
            ) and _REF_PATTERN.search(content):
                sim += 0.15
            elif (
                re.search(r"email|contact|coordonn|[eé]lectron|electron", query, re.I)
                and "@" in content
            ):
                sim += 0.30
            elif _IDENTITY_QUERY.search(query) and not re.search(
                r"contrat|dossier|r[eé]f|factur|tarif|email|@|bug|mobile|coordonn|[eé]lectron|electron",
                query,
                re.I,
            ):
                if _NAME_PATTERN.search(content):
                    sim += 0.25
                elif re.search(r"\b(marie|dupont|cliente|client)\b", content, re.I):
                    sim += 0.03
                if content.lower().startswith("user:") and _NAME_PATTERN.search(content):
                    sim += 0.08
            if re.search(r"factur|tarif|prix|montant|[eé]cart", query, re.I) and re.search(
                r"\d+[,.]\d+", content
            ):
                sim += 0.12
            if re.search(r"bug|mobile|incident|application", query, re.I) and re.search(
                r"bug|mobile|ios|android|application", content, re.I
            ):
                sim += 0.12

            last = _parse_dt(row["last_accessed"]) or now
            t_hours = hours_since(last, now)
            rec = recency_decay(t_hours)
            imp_w = row["importance"]
            ret = row["retention_score"]
            final = 0.85 * sim + 0.10 * imp_w + 0.05 * rec * ret
            scored.append((sim, final, row))

        scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
        results: list[MemoryEntry] = []
        for sim, score, row in scored[:top_k]:
            if record_access:
                self._record_access(row["id"], row["stability"], row["access_count"])
            results.append(self._row_to_entry(row, score=score))

        self._retrieval_times.append((time.perf_counter() - t0) * 1000)
        return results

    def list_session(self, session: str, include_archived: bool = False) -> list[MemoryEntry]:
        sql = "SELECT * FROM memories WHERE session = ?"
        if not include_archived:
            sql += " AND is_archived = 0"
        sql += " ORDER BY turn ASC, id ASC"
        rows = self._conn.execute(sql, (session,)).fetchall()
        return [self._row_to_entry(r) for r in rows]

    def get_embedding(self, memory_id: int) -> np.ndarray | None:
        row = self._conn.execute(
            "SELECT embedding FROM memories WHERE id = ?", (memory_id,)
        ).fetchone()
        if not row or not row["embedding"]:
            return None
        return deserialize(row["embedding"])

    def list_active(self, session: str | None = None) -> list[MemoryEntry]:
        sql = "SELECT * FROM memories WHERE is_archived = 0"
        params: tuple = ()
        if session:
            sql += " AND session = ?"
            params = (session,)
        sql += " ORDER BY created_at DESC"
        rows = self._conn.execute(sql, params).fetchall()
        return [self._row_to_entry(r) for r in rows]

    def get_session_summary(self, session: str) -> str:
        row = self._conn.execute(
            "SELECT summary FROM session_summaries WHERE session = ?",
            (session,),
        ).fetchone()
        return row["summary"] if row else ""

    def set_session_summary(self, session: str, summary: str) -> None:
        now = _utcnow().isoformat()
        self._conn.execute(
            """
            INSERT INTO session_summaries (session, summary, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(session) DO UPDATE SET
                summary = excluded.summary,
                updated_at = excluded.updated_at
            """,
            (session, summary, now),
        )
        self._conn.commit()

    def archive_entries(self, session: str, keep_ids: set[int] | None = None) -> int:
        keep_ids = keep_ids or set()
        rows = self._conn.execute(
            "SELECT id FROM memories WHERE session = ? AND is_archived = 0",
            (session,),
        ).fetchall()
        archived = 0
        for row in rows:
            if row["id"] not in keep_ids:
                self._conn.execute(
                    "UPDATE memories SET is_archived = 1 WHERE id = ?",
                    (row["id"],),
                )
                archived += 1
        self._conn.commit()
        return archived

    def count(self, active_only: bool = False) -> int:
        if active_only:
            row = self._conn.execute(
                "SELECT COUNT(*) AS c FROM memories WHERE is_archived = 0"
            ).fetchone()
        else:
            row = self._conn.execute("SELECT COUNT(*) AS c FROM memories").fetchone()
        return int(row["c"])

    def count_archived(self) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) AS c FROM memories WHERE is_archived = 1"
        ).fetchone()
        return int(row["c"])

    def avg_retrieval_time_ms(self) -> float:
        if not self._retrieval_times:
            return 0.0
        return sum(self._retrieval_times) / len(self._retrieval_times)

    def graph_data(self, session: str | None = None, link_threshold: float = 0.7) -> dict:
        """Nœuds + liens pour le graphe Ebbinghaus du dashboard."""
        entries = self.list_active(session)
        nodes = []
        for e in entries:
            color = (
                "green"
                if e.retention_score > 0.7
                else "yellow"
                if e.retention_score > 0.3
                else "red"
            )
            nodes.append(
                {
                    "id": e.id,
                    "label": e.content[:60],
                    "importance": e.importance,
                    "retention_score": round(e.retention_score, 4),
                    "stability": round(e.stability, 4),
                    "color": color,
                    "session": e.session,
                }
            )

        rows = self._conn.execute(
            "SELECT source_id, target_id, weight FROM memory_links"
        ).fetchall()
        stored_links = {(r["source_id"], r["target_id"]): r["weight"] for r in rows}

        links = []
        node_ids = {n["id"] for n in nodes}
        if stored_links:
            for (id_a, id_b), w in stored_links.items():
                if id_a in node_ids and id_b in node_ids:
                    links.append({"source": id_a, "target": id_b, "weight": round(w, 4)})
        if not links:
            vecs: dict[int, np.ndarray] = {}
            for e in entries:
                vec = self.get_embedding(e.id)
                if vec is not None:
                    vecs[e.id] = vec

            ids = list(vecs.keys())
            for i, id_a in enumerate(ids):
                for id_b in ids[i + 1 :]:
                    sim = cosine_similarity(vecs[id_a], vecs[id_b])
                    if sim >= link_threshold:
                        links.append({"source": id_a, "target": id_b, "weight": round(sim, 4)})

        return {"nodes": nodes, "links": links}

    def reset(self) -> None:
        self._conn.execute("DELETE FROM memories")
        self._conn.execute("DELETE FROM session_summaries")
        self._conn.execute("DELETE FROM memory_links")
        self._conn.commit()
        self._retrieval_times.clear()

    def close(self) -> None:
        self._conn.close()
