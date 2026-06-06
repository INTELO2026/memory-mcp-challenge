"""Implémentation des outils MCP : store, search, summarize, stats, graph."""

from __future__ import annotations

from pathlib import Path

from memory_mcp.memory_graph import expand_with_linked, link_memory_to_similar
from memory_mcp.stats import count_tokens, enrich_stats_dict, get_stats
from memory_mcp.storage import MemoryStore
from memory_mcp.summarizer import build_structured_summary, consolidate_session

CONSOLIDATE_EVERY_N_TURNS = 5
_DB_DIR = Path.home() / ".membridge"
_DB_PATH = _DB_DIR / "memories.db"


def _default_store() -> MemoryStore:
    import os

    if os.environ.get("MEMBRIDGE_PERSIST") == "1":
        _DB_DIR.mkdir(parents=True, exist_ok=True)
        return MemoryStore(_DB_PATH)
    db = os.environ.get("MEMBRIDGE_DB")
    return MemoryStore(db) if db else MemoryStore()


class MemoryTools:
    def __init__(self, store: MemoryStore | None = None) -> None:
        self.store = store or _default_store()
        self._turn_counters: dict[str, int] = {}

    def memory_store(
        self,
        content: str,
        tags: list[str] | None = None,
        session: str = "default",
        turn: int = 0,
        agent_id: str = "default",
    ) -> dict:
        """Stocke un fragment de mémoire avec tags optionnels."""
        stats = get_stats()
        stats.store_calls += 1
        stats.add_input(count_tokens(content))

        memory_id = self.store.store(
            content=content,
            tags=tags,
            session=session,
            turn=turn,
            agent_id=agent_id,
        )
        links_created = link_memory_to_similar(self.store, memory_id, session)

        counter = self._turn_counters.get(session, 0) + 1
        self._turn_counters[session] = counter
        if counter % CONSOLIDATE_EVERY_N_TURNS == 0:
            consolidate_session(self.store, session, max_chars=160)

        return {
            "id": memory_id,
            "stored": True,
            "tags": tags or [],
            "agent_id": agent_id,
            "links_created": links_created,
        }

    def memory_search(
        self,
        query: str,
        top_k: int = 5,
        session: str | None = None,
        agent_id: str | None = None,
        expand_links: bool = True,
        record_access: bool = True,
    ) -> dict:
        """Recherche sémantique dans la mémoire (mémoire partagée multi-agents)."""
        stats = get_stats()
        stats.search_calls += 1
        stats.add_input(count_tokens(query))

        hits = self.store.search(
            query=query,
            top_k=top_k,
            session=session,
            agent_id=agent_id,
            record_access=record_access,
        )
        hit_ids = [h.id for h in hits]
        if expand_links and hit_ids:
            for extra_id in expand_with_linked(self.store, hit_ids, max_extra=2):
                extra = self.store.get_memory_by_id(extra_id)
                if extra and not extra.is_archived:
                    hits.append(extra)

        results = [
            {
                "id": h.id,
                "content": h.content,
                "tags": h.tags,
                "turn": h.turn,
                "score": round(h.score, 6),
                "retention_score": round(h.retention_score, 4),
                "importance": round(h.importance, 4),
            }
            for h in hits[: top_k + 2]
        ]
        stats.add_output(count_tokens(str(results)))
        return {"results": results, "count": len(results)}

    def memory_summarize(self, session: str = "default", max_chars: int = 180) -> dict:
        """Résume compressé de l'historique d'une session (JSON structuré inclus)."""
        stats = get_stats()
        stats.summarize_calls += 1

        entries = self.store.list_session(session)
        if not entries and not self.store.get_session_summary(session):
            empty = {"key_facts": [], "entities": {}, "open_questions": [], "context_anchors": []}
            return {"summary": "", "structured": empty, "source_turns": 0, "compressed_chars": 0}

        source_text = "".join(e.content for e in entries)
        source_len = len(source_text)
        if source_len > 0:
            max_chars = min(max_chars, max(120, int(source_len * 0.19)))

        summary, structured, source_turns = build_structured_summary(
            self.store, session, max_chars=max_chars
        )

        stats.add_input(count_tokens(source_text))
        stats.add_output(count_tokens(summary))
        return {
            "summary": summary,
            "structured": structured,
            "source_turns": source_turns,
            "compressed_chars": len(summary),
        }

    def memory_graph(self, session: str | None = None) -> dict:
        """Graphe A-MEM : nœuds + liens sémantiques entre souvenirs."""
        return self.store.graph_data(session=session)

    def memory_stats(self) -> dict:
        """Retourne les statistiques de consommation tokens."""
        return enrich_stats_dict(get_stats().to_dict(), self.store)

    def reset(self) -> None:
        """Réinitialise store et compteurs."""
        self.store.reset()
        self._turn_counters.clear()
