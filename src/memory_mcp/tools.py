"""Implémentation avancée des 4 outils MCP : store, search, summarize, stats."""

from __future__ import annotations

from datetime import UTC, datetime

from memory_mcp.config import ensure_env_loaded, get_settings, is_llm_configured
from memory_mcp.stats import count_tokens, get_stats
from memory_mcp.storage import MemoryStore
from memory_mcp.summarize import build_summary_report


class MemoryTools:
    def __init__(self, store: MemoryStore | None = None) -> None:

        ensure_env_loaded()

        if store is not None:
            self.store = store

        else:
            settings = get_settings()

            db_path = settings.db_path or ":memory:"

            self.store = MemoryStore(db_path)

    def close(self) -> None:

        self.store.close()

    def memory_store(
        self,
        content: str,
        tags: list[str] | None = None,
        session: str = "default",
        turn: int = 0,
        importance: int | None = None,
    ) -> dict:
        """Enregistre une information avec métadonnées (session, date, importance)."""

        stats = get_stats()

        stats.store_calls += 1

        token_count = count_tokens(content)

        stats.add_input(token_count)

        stored = self.store.store(
            content=content,
            tags=tags,
            session=session,
            turn=turn,
            importance=importance,
            dedupe=True,
        )

        if not stored.get("deduplicated"):
            stats.tokens_stored += token_count

        pruned = self.store.prune_stale(session=session, current_turn=turn)

        created = stored.get("created_at", 0)

        return {
            **stored,
            "tags": stored.get("tags") or tags or [],
            "tokens": 0 if stored.get("deduplicated") else token_count,
            "date": datetime.fromtimestamp(created, tz=UTC).isoformat() if created else None,
            "pruned": pruned,
        }

    def memory_search(
        self,
        query: str,
        top_k: int = 5,
        session: str | None = None,
        *,
        tag: str | None = None,
        min_importance: int = 0,
        exclude_tags: list[str] | None = None,
    ) -> dict:
        """Récupère par similarité sémantique + hiérarchie de pertinence."""

        stats = get_stats()

        stats.search_calls += 1

        stats.add_input(count_tokens(query))

        hits = self.store.search(
            query=query,
            top_k=top_k,
            session=session,
            tag=tag,
            min_importance=min_importance,
            exclude_tags=exclude_tags,
        )

        results = [h.to_dict() for h in hits]

        stats.add_output(count_tokens(str(results)))

        return {
            "results": results,
            "count": len(results),
            "query": query,
            "filters": {
                "session": session,
                "tag": tag,
                "min_importance": min_importance,
                "exclude_tags": exclude_tags or [],
            },
            "ranking_signals": [
                "semantic",
                "lexical",
                "domain",
                "hierarchy",
                "tag_boost",
            ],
        }

    def memory_summarize(
        self,
        session: str = "default",
        max_chars: int | None = None,
        max_tokens: int | None = None,
        use_llm: bool = False,
    ) -> dict:
        """Résume compressé — cerveau de la compression avec métriques."""

        stats = get_stats()

        stats.summarize_calls += 1

        entries = self.store.list_session(session)

        if not entries:
            return {
                "summary": "",
                "source_turns": 0,
                "compressed_chars": 0,
                "source_tokens": 0,
                "summary_tokens": 0,
                "compression_ratio": 0.0,
                "facts_preserved": 0,
                "method": "none",
            }

        settings = get_settings()

        effective_tokens = max_tokens if max_tokens is not None else settings.summary_max_tokens

        report = build_summary_report(entries, max_tokens=effective_tokens, use_llm=use_llm)

        summary = report["summary"]

        if max_chars is not None and len(summary) > max_chars:
            summary = summary[: max_chars - 3] + "..."

            report["summary"] = summary

            report["compressed_chars"] = len(summary)

        stats.tokens_saved += max(0, report["source_tokens"] - report["summary_tokens"])

        stats.add_input(report["source_tokens"])

        stats.add_output(report["summary_tokens"])

        return report

    def memory_stats(self, session: str | None = None) -> dict:
        """Métriques tokens stockés, économisés, entrées + analytics avancées."""

        settings = get_settings()

        stats = get_stats()

        entry_count = self.store.count(session=session) if session else self.store.count()

        archived = (
            self.store.archived_count(session=session) if session else self.store.archived_count()
        )

        stored_chars = self.store.stored_characters(session=session)

        payload = stats.to_dict(entry_count=entry_count)

        payload.update(
            {
                "archived_entries": archived,
                "stored_characters": stored_chars,
                "estimated_stored_tokens": count_tokens("x" * stored_chars) if stored_chars else 0,
                "tokens_saved_total": stats.tokens_saved,
                "savings_rate_pct": round(
                    100 * stats.tokens_saved / max(stats.tokens_stored, 1), 1
                ),
                "persistent": settings.db_path is not None,
                "db_path": settings.db_path,
                "sessions": self.store.list_sessions() if not session else None,
                "engine": {
                    "embeddings": "sentence-transformers/all-MiniLM-L6-v2",
                    "vector_index": "FAISS IndexFlatIP",
                    "storage": "SQLite + archivage intelligent",
                },
                "ranking": {
                    "importance_levels": {0: "noise", 1: "exchange", 3: "fact"},
                    "signals": [
                        "semantic",
                        "lexical",
                        "intent",
                        "source",
                        "recency",
                        "importance",
                        "access_frequency",
                    ],
                },
                "features": {
                    "deduplication": True,
                    "intelligent_forgetting": True,
                    "cross_session_search": True,
                    "hybrid_ranking": True,
                    "llm_summarize": settings.use_llm and is_llm_configured(),
                },
            }
        )

        if session:
            payload["session"] = self.store.session_summary(session)

        return payload
