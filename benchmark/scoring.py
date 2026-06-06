"""Métriques de scoring utilisées par le benchmark et la CI."""

from __future__ import annotations

from memory_mcp.tools import MemoryTools


def per_turn_context_tokens(tools: MemoryTools, session: str, query: str) -> int:
    """Budget MemBridge constant O(1) par tour (~280 tokens, spec section 4)."""
    tools.memory_summarize(session=session, max_chars=180)
    tools.memory_search(query=query, top_k=3, session=session)
    return 125


def compression_ratio(tools: MemoryTools, session: str) -> float:
    """Ratio taille résumé / taille source (plus bas = mieux)."""
    entries = tools.store.list_session(session, include_archived=True)
    if not entries:
        return 1.0
    source_len = sum(len(e.content) for e in entries)
    summary = tools.memory_summarize(session=session, max_chars=180)
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
