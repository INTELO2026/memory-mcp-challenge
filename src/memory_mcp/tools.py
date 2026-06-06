"""Implémentation des outils MCP de MemBridge.

Outils principaux (exigés par le défi) :
    - memory_store     : enregistre un fragment + métadonnées (embedding, importance…)
    - memory_search    : recherche sémantique par similarité
    - memory_summarize : résumé compressé conservant les faits
    - memory_stats     : métriques tokens (axe coût)

Outils bonus (différenciation) :
    - memory_rank      : hiérarchie de pertinence (importance × récence × fréquence)
    - memory_forget    : oubli intelligent des doublons
"""

from __future__ import annotations

from memory_mcp.stats import count_tokens, get_stats
from memory_mcp.storage import MemoryStore
from memory_mcp.summarize import DEFAULT_MAX_CHARS, summarize_entries


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
        importance = 0.0
        # Récupère l'importance calculée pour le retour (utile au dashboard).
        for entry in self.store.list_session(session):
            if entry.id == memory_id:
                importance = entry.importance
                break
        return {
            "id": memory_id,
            "stored": True,
            "tags": tags or [],
            "importance": round(importance, 4),
        }

    def memory_search(
        self,
        query: str,
        top_k: int = 5,
        session: str | None = None,
        use_hierarchy: bool = False,
    ) -> dict:
        """Recherche sémantique dans la mémoire."""
        stats = get_stats()
        stats.search_calls += 1
        stats.add_input(count_tokens(query))

        hits = self.store.search(
            query=query, top_k=top_k, session=session, use_hierarchy=use_hierarchy
        )
        results = [
            {
                "id": h.id,
                "content": h.content,
                "tags": h.tags,
                "turn": h.turn,
                "score": round(h.score, 6),
                "importance": round(h.importance, 4),
            }
            for h in hits
        ]
        stats.add_output(count_tokens(str(results)))
        return {"results": results, "count": len(results)}

    def memory_summarize(
        self, session: str = "default", max_chars: int = DEFAULT_MAX_CHARS
    ) -> dict:
        """Résumé compressé de l'historique d'une session (conserve les faits saillants)."""
        stats = get_stats()
        stats.summarize_calls += 1

        entries = self.store.list_session(session)
        if not entries:
            return {"summary": "", "source_turns": 0, "compressed_chars": 0, "facts_kept": 0}

        result = summarize_entries(entries, max_chars=max_chars)

        stats.add_input(count_tokens("".join(e.content for e in entries)))
        stats.add_output(count_tokens(result["summary"]))
        return result

    def memory_stats(self) -> dict:
        """Retourne les statistiques de consommation tokens."""
        stats = get_stats().to_dict()
        stats["entries"] = self.store.count()
        stats["sessions"] = len(self.store.sessions())
        return stats

    # --------------------------------------------------------------- bonus ---
    def memory_rank(self, session: str = "default", top_k: int = 10) -> dict:
        """Hiérarchie de pertinence : souvenirs triés par importance × récence × fréquence."""
        ranked = self.store.ranked_session(session, top_k=top_k)
        return {
            "results": [
                {
                    "id": e.id,
                    "content": e.content,
                    "turn": e.turn,
                    "importance": round(e.importance, 4),
                    "access_count": e.access_count,
                    "rank_score": e.rank_score,
                }
                for e in ranked
            ],
            "count": len(ranked),
        }

    def memory_forget(self, session: str = "default", similarity_threshold: float = 0.93) -> dict:
        """Oubli intelligent : purge les souvenirs quasi-dupliqués."""
        removed = self.store.forget_redundant(session, similarity_threshold=similarity_threshold)
        return {"forgotten": removed, "remaining": self.store.count(session)}
