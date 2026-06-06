"""Implémentation des 4 outils MCP : store, search, summarize, stats."""

from __future__ import annotations

from memory_mcp.stats import count_tokens, get_stats
from memory_mcp.storage import MemoryStore
from memory_mcp.summarize import distill_session

_SEARCH_TOTAL_CHARS = 120


class MemoryTools:
    def __init__(self, store: MemoryStore | None = None) -> None:
        self.store = store or MemoryStore()

    def memory_store(
        self, content: str, tags: list[str] | None = None, session: str = "default", turn: int = 0
    ) -> dict:
        """Stocke un fragment de mémoire avec tags optionnels."""
        stats = get_stats()
        stats.store_calls += 1
        stats.add_input(count_tokens(content))

        memory_id = self.store.store(content=content, tags=tags, session=session, turn=turn)
        return {"id": memory_id, "stored": True, "tags": tags or []}

    def memory_search(self, query: str, top_k: int = 5, session: str | None = None) -> dict:
        """Recherche sémantique dans la mémoire."""
        stats = get_stats()
        stats.search_calls += 1
        stats.add_input(count_tokens(query))

        hits = self.store.search(query=query, top_k=top_k, session=session)
        per_hit = _SEARCH_TOTAL_CHARS // max(len(hits), 1)
        results = []
        for h in hits:
            snippet = h.content
            if len(snippet) > per_hit:
                snippet = snippet[: per_hit - 3] + "..."
            results.append(
                {
                    "id": h.id,
                    "content": snippet,
                    "tags": h.tags,
                    "turn": h.turn,
                    "score": round(h.score, 6),
                }
            )
        stats.add_output(count_tokens(str(results)))
        return {"results": results, "count": len(results)}

    def memory_summarize(self, session: str = "default", max_chars: int = 500) -> dict:
        """Résume compressé de l'historique d'une session."""
        stats = get_stats()
        stats.summarize_calls += 1

        entries = self.store.list_session(session)
        if not entries:
            return {"summary": "", "source_turns": 0, "compressed_chars": 0}

        summary = distill_session(entries, max_chars=max_chars)

        stats.add_input(count_tokens("".join(e.content for e in entries)))
        stats.add_output(count_tokens(summary))
        return {
            "summary": summary,
            "source_turns": len(entries),
            "compressed_chars": len(summary),
        }

    def memory_stats(self) -> dict:
        """Retourne les statistiques de consommation tokens."""
        return get_stats().to_dict()
