"""Mode naïf : renvoie tout l'historique à chaque tour (croissance quadratique)."""

from __future__ import annotations

from memory_mcp.stats import count_tokens


def build_naive_context(history: list[dict]) -> tuple[str, int]:
    """Construit le contexte complet et compte les tokens."""
    lines = [f"[{m['role']}] {m['content']}" for m in history]
    context = "\n".join(lines)
    return context, count_tokens(context)


def simulate_naive_conversation(turns: list[dict]) -> dict:
    """Simule une conversation en mode naïf."""
    history: list[dict] = []
    total_tokens = 0
    per_turn: list[int] = []

    for turn in turns:
        history.append({"role": turn["role"], "content": turn["content"]})
        _, tokens = build_naive_context(history)
        total_tokens += tokens
        per_turn.append(tokens)

    return {
        "mode": "naive",
        "turns": len(turns),
        "total_tokens": total_tokens,
        "per_turn_tokens": per_turn,
        "tokens_per_turn": per_turn,
    }
