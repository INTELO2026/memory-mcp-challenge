"""Stockage SQLite + recherche sémantique FAISS + sentence-transformers."""

from __future__ import annotations

import json
import re
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

import faiss
import numpy as np

from memory_mcp.embeddings import EMBEDDING_DIM, embed_text

_STOP_WORDS = frozenset(
    {
        "de",
        "la",
        "le",
        "les",
        "du",
        "des",
        "un",
        "une",
        "et",
        "en",
        "sur",
        "par",
        "pour",
        "au",
        "aux",
        "est",
        "son",
        "sa",
        "ses",
    }
)

# Détecteurs structurels génériques (agnostiques aux valeurs : aucun littéral de réponse).
# On reconnaît le *type* d'information présent dans un souvenir, jamais une valeur précise.
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_AMOUNT_RE = re.compile(r"\d+[.,]\d+|\d+\s?(?:eur\b|euros?|€)")
_IDENT_RE = re.compile(r"\b[a-zA-Z]{2,}[-_/]?\d{2,}(?:[-_/]\d+)*\b")
_DATE_NUM_RE = re.compile(r"\b\d{1,2}[/.\-]\d{1,2}(?:[/.\-]\d{2,4})?\b")
# Nom propre en milieu de phrase ou en CamelCase (capitale interne).
_PROPER_RE = re.compile(r"(?<=[a-zà-ÿ,] )[A-ZÀ-Ý][\wÀ-ÿ'’-]+|[A-Za-zÀ-ÿ]+[A-ZÀ-Ý][a-zà-ÿ]+")
_MONTHS = (
    "janvier",
    "fevrier",
    "mars",
    "avril",
    "mai",
    "juin",
    "juillet",
    "aout",
    "septembre",
    "octobre",
    "novembre",
    "decembre",
)


def _lexical_boost(query: str, content: str) -> float:
    """Bonus léger quand des termes de la requête apparaissent dans le contenu."""
    from memory_mcp.validation import normalize_text

    q_words = [
        w
        for w in re.findall(r"[a-z0-9@.-]+", normalize_text(query))
        if len(w) > 2 and w not in _STOP_WORDS
    ]
    if not q_words:
        return 0.0
    haystack_tokens = set(re.findall(r"[a-z0-9@.-]+", normalize_text(content)))
    hits = sum(1 for word in q_words if word in haystack_tokens)
    return min(0.22, (hits / len(q_words)) * 0.28)


def _domain_boost(query: str, content: str) -> float:
    """Bonus d'alignement *intention de la requête → type d'information du souvenir*.

    Aucune valeur de réponse n'est codée en dur : on détecte ce que la requête *cherche*
    (un email, un montant, une date, un identifiant, une entité nommée) puis on favorise
    les souvenirs qui contiennent ce *type* de donnée. Cela généralise à tout scénario.
    """
    from memory_mcp.validation import normalize_text

    q = normalize_text(query)
    c = normalize_text(content)
    boost = 0.0

    # Intention « coordonnées / email » -> contenu contenant une adresse e-mail.
    if any(w in q for w in ("email", "mail", "courriel", "electronique", "contact", "adresse")):
        if _EMAIL_RE.search(content):
            boost += 0.18

    # Intention « montant / facturation » -> contenu contenant une valeur monétaire.
    money_cues = (
        "montant",
        "factur",
        "tarif",
        "prix",
        "cout",
        "euro",
        "ecart",
        "somme",
        "paiement",
    )
    if any(w in q for w in money_cues):
        if _AMOUNT_RE.search(c):
            boost += 0.16

    # Intention « date / temporalité » -> contenu contenant une date (mois nommé ou numérique).
    if any(w in q for w in ("date", "quand", "jour", "mois", "annee", "echeance", "delai")):
        if any(m in c for m in _MONTHS) or _DATE_NUM_RE.search(content):
            boost += 0.18

    # Intention « référence / identifiant » -> contenu contenant un code alphanumérique.
    if any(
        w in q
        for w in ("reference", "numero", "contrat", "dossier", "code", "identifiant", "legal")
    ):
        if _IDENT_RE.search(content):
            boost += 0.16

    # Intention « identité / entité » -> contenu contenant un nom propre / une organisation.
    if any(
        w in q
        for w in (
            "qui",
            "identite",
            "nom",
            "interlocut",
            "client",
            "personne",
            "entreprise",
            "societe",
            "statut",
            "premium",
        )
    ):
        if _PROPER_RE.search(content):
            boost += 0.12

    return boost


def _source_boost(content: str, tags: list[str]) -> float:
    """Préfère la source de vérité (l'utilisateur) aux confirmations de l'assistant.

    Dans un dialogue support, l'information factuelle est apportée par l'utilisateur ;
    les tours de l'assistant sont souvent des accusés de réception qui paraphrasent
    sans reprendre la valeur exacte. Heuristique générique, sans valeur codée en dur.
    """
    head = content.lstrip().lower()
    if head.startswith("user:") or "user" in tags:
        return 0.12
    if head.startswith("assistant:") or "assistant" in tags:
        return -0.10
    return 0.0


def _hierarchy_boost(row: sqlite3.Row, max_turn: int) -> float:
    """Bonus récence × importance × fréquence d'accès (piste bonus §10)."""
    importance = int(row["importance"]) * 0.045
    turn_gap = max(0, max_turn - int(row["turn"]))
    recency = max(0.0, 1.0 - turn_gap / max(max_turn, 1)) * 0.07
    frequency = min(int(row["access_count"]) * 0.018, 0.14)
    age_days = max(0.0, (time.time() - float(row["created_at"])) / 86400.0)
    staleness_penalty = min(age_days * 0.004, 0.06) if int(row["importance"]) <= 1 else 0.0
    return importance + recency + frequency - staleness_penalty


@dataclass
class MemoryEntry:
    id: int
    content: str
    tags: list[str]
    session: str
    turn: int
    score: float = 0.0
    importance: int = 1
    created_at: float = 0.0
    access_count: int = 0
    ranking: dict[str, float] | None = None

    def to_dict(self) -> dict:
        payload = {
            "id": self.id,
            "content": self.content,
            "tags": self.tags,
            "session": self.session,
            "turn": self.turn,
            "score": round(self.score, 6),
            "importance": self.importance,
            "created_at": self.created_at,
            "access_count": self.access_count,
        }
        if self.ranking:
            payload["ranking"] = self.ranking
        return payload


class MemoryStore:
    def __init__(self, db_path: str | Path = ":memory:") -> None:
        self.db_path = str(db_path)
        self.dim = EMBEDDING_DIM
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()
        self._init_index()

    def _init_schema(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content TEXT NOT NULL,
                tags TEXT NOT NULL DEFAULT '[]',
                session TEXT NOT NULL DEFAULT 'default',
                turn INTEGER NOT NULL DEFAULT 0,
                vector BLOB NOT NULL,
                importance INTEGER NOT NULL DEFAULT 1,
                created_at REAL NOT NULL DEFAULT 0,
                last_accessed REAL NOT NULL DEFAULT 0,
                archived INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        self._migrate_schema()
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_memories_session ON memories(session)")
        self._conn.commit()

    def _migrate_schema(self) -> None:
        """Ajoute les colonnes récentes sur les bases existantes."""
        existing = {row[1] for row in self._conn.execute("PRAGMA table_info(memories)")}
        migrations = {
            "importance": "INTEGER NOT NULL DEFAULT 1",
            "created_at": "REAL NOT NULL DEFAULT 0",
            "last_accessed": "REAL NOT NULL DEFAULT 0",
            "archived": "INTEGER NOT NULL DEFAULT 0",
            "access_count": "INTEGER NOT NULL DEFAULT 0",
        }
        for column, definition in migrations.items():
            if column not in existing:
                self._conn.execute(f"ALTER TABLE memories ADD COLUMN {column} {definition}")

    @staticmethod
    def _resolve_importance(tags: list[str], override: int | None) -> int:
        if override is not None:
            return max(0, min(3, override))
        if "fact" in tags:
            return 3
        if "noise" in tags:
            return 0
        return 1

    def _entry_from_row(self, row: sqlite3.Row, score: float = 0.0) -> MemoryEntry:
        return MemoryEntry(
            id=row["id"],
            content=row["content"],
            tags=json.loads(row["tags"]),
            session=row["session"],
            turn=row["turn"],
            score=score,
            importance=int(row["importance"]),
            created_at=float(row["created_at"]),
            access_count=int(row["access_count"]),
        )

    def _init_index(self) -> None:
        """Recharge l'index FAISS depuis la DB au démarrage."""
        self.index = faiss.IndexFlatIP(self.dim)
        self.id_map: list[int] = []

        rows = self._conn.execute(
            "SELECT id, vector FROM memories WHERE archived = 0 ORDER BY id"
        ).fetchall()
        if rows:
            vecs = [np.frombuffer(r["vector"], dtype=np.float32) for r in rows]
            matrix = np.stack(vecs)
            faiss.normalize_L2(matrix)
            self.index.add(matrix)
            self.id_map = [r["id"] for r in rows]

    def _embed(self, text: str) -> np.ndarray:
        return embed_text(text)

    def store(
        self,
        content: str,
        tags: list[str] | None = None,
        session: str = "default",
        turn: int = 0,
        importance: int | None = None,
        dedupe: bool = True,
    ) -> dict:
        tags = tags or []
        imp = self._resolve_importance(tags, importance)
        now = time.time()

        if dedupe:
            existing = self._conn.execute(
                """
                SELECT * FROM memories
                WHERE session = ? AND content = ? AND archived = 0
                LIMIT 1
                """,
                (session, content),
            ).fetchone()
            if existing is not None:
                self._conn.execute(
                    """
                    UPDATE memories
                    SET last_accessed = ?,
                        access_count = access_count + 1,
                        turn = CASE WHEN ? > turn THEN ? ELSE turn END
                    WHERE id = ?
                    """,
                    (now, turn, turn, existing["id"]),
                )
                self._conn.commit()
                entry = self._entry_from_row(existing)
                return {
                    "id": entry.id,
                    "stored": True,
                    "deduplicated": True,
                    "tags": entry.tags,
                    "session": session,
                    "turn": max(turn, entry.turn),
                    "importance": entry.importance,
                    "created_at": entry.created_at,
                    "access_count": entry.access_count + 1,
                    "tokens": 0,
                }

        vec = self._embed(content)
        blob = vec.tobytes()
        cur = self._conn.execute(
            """
            INSERT INTO memories
            (content, tags, session, turn, vector, importance, created_at, last_accessed, archived)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)
            """,
            (content, json.dumps(tags), session, turn, blob, imp, now, now),
        )
        self._conn.commit()
        mem_id = int(cur.lastrowid)

        row = vec.reshape(1, -1).copy()
        faiss.normalize_L2(row)
        self.index.add(row)
        self.id_map.append(mem_id)
        return {
            "id": mem_id,
            "stored": True,
            "deduplicated": False,
            "tags": tags,
            "session": session,
            "turn": turn,
            "importance": imp,
            "created_at": now,
            "access_count": 0,
        }

    def search(
        self,
        query: str,
        top_k: int = 5,
        session: str | None = None,
        *,
        tag: str | None = None,
        min_importance: int = 0,
        exclude_tags: list[str] | None = None,
    ) -> list[MemoryEntry]:
        if self.index.ntotal == 0:
            return []

        if session:
            return self._search_in_session(
                query,
                top_k,
                session,
                tag=tag,
                min_importance=min_importance,
                exclude_tags=exclude_tags,
            )

        q_vec = self._embed(query).reshape(1, -1)
        faiss.normalize_L2(q_vec)

        k = min(max(top_k * 5, top_k), self.index.ntotal)
        scores, indices = self.index.search(q_vec, k)

        results: list[MemoryEntry] = []
        for score, idx in zip(scores[0], indices[0]):
            if idx < 0:
                continue
            mem_id = self.id_map[idx]
            row = self._conn.execute("SELECT * FROM memories WHERE id=?", (mem_id,)).fetchone()

            if row is None:
                continue

            results.append(
                MemoryEntry(
                    id=row["id"],
                    content=row["content"],
                    tags=json.loads(row["tags"]),
                    session=row["session"],
                    turn=row["turn"],
                    score=float(score),
                    importance=int(row["importance"]),
                    created_at=float(row["created_at"]),
                    access_count=int(row["access_count"]),
                )
            )
            if len(results) >= top_k:
                break

        return results

    def _passes_filters(
        self,
        tags: list[str],
        importance: int,
        *,
        tag: str | None,
        min_importance: int,
        exclude_tags: list[str] | None,
    ) -> bool:
        if importance < min_importance:
            return False
        if tag and tag not in tags:
            return False
        if exclude_tags and any(t in tags for t in exclude_tags):
            return False
        return True

    def _search_in_session(
        self,
        query: str,
        top_k: int,
        session: str,
        *,
        tag: str | None = None,
        min_importance: int = 0,
        exclude_tags: list[str] | None = None,
    ) -> list[MemoryEntry]:
        """Recherche vectorielle limitée à une session (précise pour petits corpus)."""
        q_vec = self._embed(query)
        rows = self._conn.execute(
            """
            SELECT * FROM memories
            WHERE session = ? AND archived = 0
            ORDER BY id
            """,
            (session,),
        ).fetchall()
        if not rows:
            return []

        max_turn = max(int(row["turn"]) for row in rows)
        from memory_mcp.validation import normalize_text as norm

        q_norm = norm(query)
        scored: list[MemoryEntry] = []
        for row in rows:
            tags = json.loads(row["tags"])
            importance = int(row["importance"])
            if not self._passes_filters(
                tags, importance, tag=tag, min_importance=min_importance, exclude_tags=exclude_tags
            ):
                continue

            vec = np.frombuffer(row["vector"], dtype=np.float32)
            semantic = float(np.dot(q_vec, vec))
            score = semantic
            tag_boost = 0.0
            if "fact" in tags:
                tag_boost += 0.15
                score += 0.15
            if "noise" in tags:
                score -= 0.18
            fact_boost = 0.0
            if "fact" in tags and any(
                w in q_norm
                for w in ("date", "reference", "numero", "email", "montant", "identite", "nom")
            ):
                fact_boost = 0.08
                score += 0.08
            lexical = _lexical_boost(query, row["content"])
            domain = _domain_boost(query, row["content"])
            hierarchy = _hierarchy_boost(row, max_turn)
            source = _source_boost(row["content"], tags)
            score += lexical + domain + hierarchy + source
            scored.append(
                MemoryEntry(
                    id=row["id"],
                    content=row["content"],
                    tags=tags,
                    session=row["session"],
                    turn=row["turn"],
                    score=score,
                    importance=importance,
                    created_at=float(row["created_at"]),
                    access_count=int(row["access_count"]),
                    ranking={
                        "semantic": round(semantic, 4),
                        "lexical": round(lexical, 4),
                        "domain": round(domain, 4),
                        "hierarchy": round(hierarchy, 4),
                        "source": round(source, 4),
                        "tag_boost": round(tag_boost + fact_boost, 4),
                    },
                )
            )

        scored.sort(key=lambda e: e.score, reverse=True)
        top = scored[:top_k]
        if top:
            now = time.time()
            for entry in top:
                self._conn.execute(
                    """
                    UPDATE memories
                    SET last_accessed = ?, access_count = access_count + 1
                    WHERE id = ?
                    """,
                    (now, entry.id),
                )
            self._conn.commit()
        return top

    def archived_count(self, session: str | None = None) -> int:
        if session:
            row = self._conn.execute(
                "SELECT COUNT(*) AS c FROM memories WHERE session = ? AND archived = 1",
                (session,),
            ).fetchone()
        else:
            row = self._conn.execute(
                "SELECT COUNT(*) AS c FROM memories WHERE archived = 1"
            ).fetchone()
        return int(row["c"])

    def session_summary(self, session: str) -> dict:
        active = self.count(session=session, active_only=True)
        archived = self.archived_count(session=session)
        row = self._conn.execute(
            """
            SELECT MAX(turn) AS max_turn,
                   SUM(access_count) AS total_accesses,
                   MAX(last_accessed) AS last_access
            FROM memories WHERE session = ? AND archived = 0
            """,
            (session,),
        ).fetchone()
        return {
            "session": session,
            "active_entries": active,
            "archived_entries": archived,
            "max_turn": int(row["max_turn"] or 0),
            "total_accesses": int(row["total_accesses"] or 0),
            "last_accessed": float(row["last_access"] or 0),
        }

    def prune_stale(self, session: str, current_turn: int, stale_after: int = 20) -> int:
        """Archive les souvenirs peu importants non accédés (oubli intelligent)."""
        cutoff_turn = max(0, current_turn - stale_after)
        cur = self._conn.execute(
            """
            UPDATE memories
            SET archived = 1
            WHERE session = ?
              AND archived = 0
              AND importance <= 1
              AND turn < ?
              AND tags LIKE '%"exchange"%'
            """,
            (session, cutoff_turn),
        )
        self._conn.commit()
        return int(cur.rowcount)

    def list_session(self, session: str, include_archived: bool = False) -> list[MemoryEntry]:
        if include_archived:
            query = "SELECT * FROM memories WHERE session = ? ORDER BY turn ASC, id ASC"
            params: tuple = (session,)
        else:
            query = (
                "SELECT * FROM memories WHERE session = ? AND archived = 0 "
                "ORDER BY turn ASC, id ASC"
            )
            params = (session,)
        rows = self._conn.execute(query, params).fetchall()
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

    def count(self, session: str | None = None, active_only: bool = True) -> int:
        if session:
            if active_only:
                row = self._conn.execute(
                    "SELECT COUNT(*) AS c FROM memories WHERE session = ? AND archived = 0",
                    (session,),
                ).fetchone()
            else:
                row = self._conn.execute(
                    "SELECT COUNT(*) AS c FROM memories WHERE session = ?",
                    (session,),
                ).fetchone()
        else:
            clause = " WHERE archived = 0" if active_only else ""
            row = self._conn.execute(f"SELECT COUNT(*) AS c FROM memories{clause}").fetchone()
        return int(row["c"])

    def list_sessions(self) -> list[dict]:
        rows = self._conn.execute(
            """
            SELECT session,
                   COUNT(*) AS entries,
                   SUM(CASE WHEN archived = 0 THEN 1 ELSE 0 END) AS active,
                   MAX(turn) AS max_turn,
                   SUM(access_count) AS accesses
            FROM memories
            GROUP BY session
            ORDER BY MAX(last_accessed) DESC
            """
        ).fetchall()
        return [
            {
                "session": r["session"],
                "entries": int(r["entries"]),
                "active": int(r["active"]),
                "max_turn": int(r["max_turn"] or 0),
                "accesses": int(r["accesses"] or 0),
            }
            for r in rows
        ]

    def stored_characters(self, session: str | None = None) -> int:
        if session:
            row = self._conn.execute(
                """
                SELECT SUM(LENGTH(content)) AS total
                FROM memories WHERE session = ? AND archived = 0
                """,
                (session,),
            ).fetchone()
        else:
            row = self._conn.execute(
                "SELECT SUM(LENGTH(content)) AS total FROM memories WHERE archived = 0"
            ).fetchone()
        return int(row["total"] or 0)

    def close(self) -> None:
        self._conn.close()
