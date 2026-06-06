"""Implémentation des 4 outils MCP : store, search, summarize, stats."""

from __future__ import annotations

from memory_mcp import embeddings
from memory_mcp.stats import count_tokens, get_stats
from memory_mcp.storage import MemoryEntry, MemoryStore, estimate_importance

# Nombre max d'entrées retenues dans un résumé. Volontairement petit : le résumé
# sature vite (contexte ~constant tour après tour) et la recherche sémantique se
# charge du rappel fin des faits pour les questions pièges.
SUMMARY_MAX_ENTRIES = 3
_ENTRY_TRIM = 100


def _dedupe(entries: list[MemoryEntry]) -> list[MemoryEntry]:
    """Retire les quasi-doublons (même contenu normalisé)."""
    seen: set[str] = set()
    unique: list[MemoryEntry] = []
    for e in entries:
        key = " ".join(e.content.lower().split())
        if key in seen:
            continue
        seen.add(key)
        unique.append(e)
    return unique


class MemoryTools:
    def __init__(self, store: MemoryStore | None = None) -> None:
        self.store = store or MemoryStore()

    def memory_store(
        self,
        content: str,
        tags: list[str] | None = None,
        session: str = "default",
        turn: int = 0,
        importance: float | None = None,
    ) -> dict:
        """Stocke un fragment de mémoire avec embedding et métadonnées."""
        stats = get_stats()
        stats.store_calls += 1
        stats.add_input(count_tokens(content))

        memory_id = self.store.store(
            content=content,
            tags=tags,
            session=session,
            turn=turn,
            importance=importance,
        )
        return {"id": memory_id, "stored": True, "tags": tags or []}

    def memory_search(self, query: str, top_k: int = 5, session: str | None = None) -> dict:
        """Recherche sémantique dans la mémoire (similarité + pertinence)."""
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
                "importance": round(h.importance, 4),
                "score": round(h.score, 6),
            }
            for h in hits
        ]
        stats.add_output(count_tokens(str(results)))
        return {"results": results, "count": len(results)}

    def memory_summarize(self, session: str = "default", max_chars: int = 500) -> dict:
        """Résumé compressé d'une session : sélection des faits les plus importants.

        On classe les tours par importance (densité d'entités factuelles), on
        déduplique, puis on rétablit l'ordre chronologique. Les faits critiques
        (identifiants, noms, montants) sont ainsi préservés malgré la compression.
        """
        stats = get_stats()
        stats.summarize_calls += 1

        entries = self.store.list_session(session)
        if not entries:
            return {"summary": "", "source_turns": 0, "compressed_chars": 0}

        ranked = sorted(
            _dedupe(entries),
            key=lambda e: (e.importance or estimate_importance(e.content), e.turn),
            reverse=True,
        )
        selected = ranked[:SUMMARY_MAX_ENTRIES]
        selected.sort(key=lambda e: e.turn)

        parts = []
        for e in selected:
            text = " ".join(e.content.split())
            if len(text) > _ENTRY_TRIM:
                text = text[: _ENTRY_TRIM - 1].rstrip() + "…"
            parts.append(f"[t{e.turn}] {text}")
        summary = " | ".join(parts)
        if len(summary) > max_chars:
            summary = summary[: max_chars - 1].rstrip() + "…"

        stats.add_input(count_tokens("".join(e.content for e in entries)))
        stats.add_output(count_tokens(summary))
        return {
            "summary": summary,
            "source_turns": len(entries),
            "compressed_chars": len(summary),
        }

    def memory_stats(self) -> dict:
        """Retourne les métriques de consommation tokens + métadonnées mémoire."""
        data = get_stats().to_dict()
        data["entries"] = self.store.count()
        data["embedding_backend"] = embeddings.backend_name()
        return data
