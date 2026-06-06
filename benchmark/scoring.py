"""Métriques de scoring utilisées par le benchmark et la CI."""

from __future__ import annotations

from memory_mcp.stats import count_tokens
from memory_mcp.tools import MemoryTools, strip_role


def per_turn_context_tokens(tools: MemoryTools, session: str, query: str) -> int:
    """Tokens du contexte LLM pour un tour (résumé + recherche).

    Les souvenirs sont injectés sans préfixe de rôle (non informatif) : on garde
    le fait, on supprime le verbiage -> aucune perte d'information.
    """
    summary = tools.memory_summarize(session=session)
    search = tools.memory_search(query=query, top_k=3, session=session)
    memories = "\n".join(strip_role(r["content"]) for r in search["results"])
    context = summary["summary"] + "\n" + memories
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


def context_growth_factor(per_turn: list[int]) -> float:
    """Ratio coût moyen des 10 derniers tours vs 10 premiers (doit stagner)."""
    if len(per_turn) < 20:
        return 999.0
    early = sum(per_turn[:10]) / 10
    late = sum(per_turn[-10:]) / 10
    if early == 0:
        return 999.0
    return late / early
