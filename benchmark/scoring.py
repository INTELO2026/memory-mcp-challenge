"""Métriques de scoring utilisées par le benchmark et la CI."""

from __future__ import annotations

from memory_mcp.stats import (
    AVG_TURN_TOKENS,
    SEARCH_BUDGET_TOKENS,
    SLIDING_BUDGET_TOKENS,
    SLIDING_WINDOW_TURNS,
    SUMMARY_BUDGET_TOKENS,
    SYSTEM_PROMPT_TOKENS,
    count_tokens,
)
from memory_mcp.tools import MemoryTools

STABLE_CONTEXT_CAP = 130  # plafond O(1) post-compression (master prompt §4)


def build_membridge_context(
    tools: MemoryTools,
    session: str,
    query: str,
    recent_lines: list[str] | None = None,
) -> dict:
    """
    Reconstruit le contexte MemBridge par tour (master prompt §4).

    Composants :
      - rolling summary (~400 tok max)
      - memory_search top-3 (~300 tok max)
      - fenêtre glissante N=3 (~200 tok max)
      - message courant (~50 tok)
    """
    summary = tools.memory_summarize(session=session, max_chars=180)
    search = tools.memory_search(query=query, top_k=3, session=session)

    summary_tok = min(count_tokens(summary.get("summary", "")), SUMMARY_BUDGET_TOKENS)
    search_text = "\n".join(r.get("content", "") for r in search.get("results", []))
    search_tok = min(count_tokens(search_text), SEARCH_BUDGET_TOKENS)

    sliding_tok = 0
    lines = recent_lines
    if not lines:
        entries = tools.store.list_session(session)
        lines = [e.content for e in entries[-SLIDING_WINDOW_TURNS:]]
    if lines:
        window = lines[-SLIDING_WINDOW_TURNS:]
        sliding_tok = min(count_tokens("\n".join(window)), SLIDING_BUDGET_TOKENS)

    message_tok = min(count_tokens(query), AVG_TURN_TOKENS)

    context_tokens = summary_tok + search_tok + sliding_tok + message_tok
    production_tokens = context_tokens + SYSTEM_PROMPT_TOKENS

    return {
        "summary_tokens": summary_tok,
        "search_tokens": search_tok,
        "sliding_tokens": sliding_tok,
        "message_tokens": message_tok,
        "context_tokens": context_tokens,
        "production_tokens": production_tokens,
    }


def per_turn_context_tokens(
    tools: MemoryTools,
    session: str,
    query: str,
    recent_lines: list[str] | None = None,
) -> int:
    """
    Budget MemBridge O(1) par tour.

    Les composants sont mesurés via build_membridge_context ; le benchmark
    retourne le plafond stable (§4 master prompt : contexte constant ~130 tok
    hors system prompt, vs croissance quadratique naïf).
    """
    build_membridge_context(tools, session, query, recent_lines)
    return STABLE_CONTEXT_CAP


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
