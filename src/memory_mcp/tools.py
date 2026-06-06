"""Implémentation des 4 outils MCP : store, search, summarize, stats."""

from __future__ import annotations

from memory_mcp.context_metrics import is_filler_content
from memory_mcp.live import publish_live, record_call
from memory_mcp.stats import count_tokens, get_stats
from memory_mcp.storage import MemoryStore
from memory_mcp.summarize import build_summary


def _role_from_content(content: str) -> str:
    if ":" in content:
        prefix = content.split(":", 1)[0].strip().lower()
        if prefix in {"user", "assistant"}:
            return prefix
    return "user"


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

        stored = content
        if turn > 0 and (
            (tags and "noise" in tags) or is_filler_content(content)
        ):
            stored = f"{_role_from_content(content)}:n{turn}"

        memory_id = self.store.store(content=stored, tags=tags, session=session, turn=turn)
        record_call(
            "memory_store",
            session=session,
            detail=f"id={memory_id}",
            tools=self,
            content=content,
            noise_turn=bool(
                (tags and "noise" in tags) or is_filler_content(content)
            ),
            turn=turn,
        )
        return {"id": memory_id, "stored": True, "tags": tags or []}

    def memory_search(self, query: str, top_k: int = 5, session: str | None = None) -> dict:
        """Recherche sémantique dans la mémoire."""
        stats = get_stats()
        stats.search_calls += 1
        stats.add_input(count_tokens(query))

        hits = self.store.search(query=query, top_k=top_k, session=session)
        results = [
            {
                "id": h.id,
                "content": h.content,
                "tags": h.tags,
                "turn": h.turn,
                "score": round(h.score, 6),
            }
            for h in hits
        ]
        stats.add_output(count_tokens(str(results)))
        record_call("memory_search", session=session or "default", detail=f"hits={len(results)}")
        return {"results": results, "count": len(results)}

    def memory_summarize(self, session: str = "default", max_chars: int = 200) -> dict:
        """Résume compressé de l'historique d'une session."""
        stats = get_stats()
        stats.summarize_calls += 1

        entries = self.store.list_session(session)
        if not entries:
            return {"summary": "", "source_turns": 0, "compressed_chars": 0}

        summary = build_summary(entries, max_chars=max_chars)

        stats.add_input(count_tokens("".join(e.content for e in entries)))
        stats.add_output(count_tokens(summary))
        record_call(
            "memory_summarize",
            session=session,
            detail=f"turns={len(entries)} chars={len(summary)}",
        )
        return {
            "summary": summary,
            "source_turns": len(entries),
            "compressed_chars": len(summary),
        }

    def memory_stats(self) -> dict:
        """Retourne les statistiques de consommation tokens."""
        stats = get_stats().to_dict()
        publish_live(memories_count=self.store.count())
        return stats
