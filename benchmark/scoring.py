"""Métriques de scoring utilisées par le benchmark et la CI."""

from __future__ import annotations

from memory_mcp.stats import count_tokens
from memory_mcp.tools import MemoryTools


def per_turn_context_tokens(tools: MemoryTools, session: str, query: str) -> int:
    """Tokens du contexte LLM pour un tour (résumé + recherche)."""
    summary = tools.memory_summarize(session=session)
    search = tools.memory_search(query=query, top_k=3, session=session)
    context = summary["summary"] + "\n" + "\n".join(r["content"] for r in search["results"])
    return count_tokens(context)


def compression_ratio(tools: MemoryTools, session: str) -> float:
    """Ratio taille résumé / taille source (plus bas = mieux)."""
    entries = tools.store.list_session(session)
    if not entries:
        return 1.0
    source_len = sum(len(e.content) for e in entries)
    summary = tools.memory_summarize(session=session)
    if source_len == 0:
        return 1.0
    return summary["compressed_chars"] / source_len


def context_growth_factor(per_turn: list[int], warmup: int = 10) -> float:
    """Ratio coût moyen des 10 derniers tours vs 10 tours après warmup.

    Les premiers tours ont moins d'entrées en mémoire → contexte naturellement
    plus petit. On mesure le plateau une fois la session stabilisée (pas le
    démarrage à froid).
    """
    if len(per_turn) < warmup + 20:
        return 999.0
    early = sum(per_turn[warmup : warmup + 10]) / 10
    late = sum(per_turn[-10:]) / 10
    if early == 0:
        return 999.0
    return late / early
