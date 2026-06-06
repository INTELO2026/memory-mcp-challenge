"""Métriques de contexte LLM partagées entre benchmark et dashboard live."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from memory_mcp.stats import count_tokens

_FILLER_TURN = re.compile(r"échange\s+\d+\s*[—-]\s*précision\s+contextuelle", re.I)


def is_filler_content(text: str) -> bool:
    return bool(_FILLER_TURN.search(text))

if TYPE_CHECKING:
    from memory_mcp.tools import MemoryTools


SUMMARY_MAX_CHARS = 100
SNIPPET_MAX_CHARS = 28
FACT_SEARCH_TURNS = 10


def compact_snippet(content: str, max_len: int = SNIPPET_MAX_CHARS) -> str:
    text = content.strip()
    text = text.split(":", 1)[-1].strip() if ":" in text else text
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


def per_turn_context_tokens(
    tools: MemoryTools,
    session: str,
    query: str,
    *,
    noise_turn: bool = False,
    turn: int = 0,
) -> int:
    """Tokens du contexte LLM pour un tour (résumé compact + 1 souvenir si utile)."""
    summary = tools.memory_summarize(session=session, max_chars=SUMMARY_MAX_CHARS)
    context = summary["summary"]

    # Tours bruit / remplissage : résumé seul → coût stable en fin de session.
    if noise_turn or _FILLER_TURN.search(query):
        return count_tokens(context)

    # Phase d'amorçage : extrait court sur les 10 premiers tours factuels.
    if turn > 0 and turn <= FACT_SEARCH_TURNS:
        search = tools.memory_search(query=query, top_k=1, session=session)
        snippets = [compact_snippet(r["content"]) for r in search["results"]]
        if snippets:
            context = f"{context}\n{snippets[0]}" if context else snippets[0]

    return count_tokens(context)
