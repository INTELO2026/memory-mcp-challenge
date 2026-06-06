"""Mode naïf : renvoie tout l'historique à chaque tour (croissance quadratique)."""

from __future__ import annotations

from memory_mcp.stats import count_tokens


def build_naive_context(history: list[dict]) -> tuple[str, int]:
    """Construit le contexte complet et compte les tokens."""
    lines = [f"[{m['role']}] {m['content']}" for m in history]
    context = "\n".join(lines)
    return context, count_tokens(context)


def simulate_naive_conversation(turns: list[dict]) -> dict:
    """Simule une conversation en mode naïf.

    À chaque tour, l'intégralité de l'historique est renvoyée au modèle ; la
    taille du contexte croît donc de façon quadratique. `context_per_turn`
    expose la taille du contexte effectivement envoyé à chaque tour (la courbe
    rouge du tableau de bord).
    """
    history: list[dict] = []
    total_tokens = 0
    context_per_turn: list[int] = []

    for turn in turns:
        history.append({"role": turn["role"], "content": turn["content"]})
        _, tokens = build_naive_context(history)
        total_tokens += tokens
        context_per_turn.append(tokens)

    return {
        "mode": "naive",
        "turns": len(turns),
        "total_tokens": total_tokens,
        "context_per_turn": context_per_turn,
        "tokens_per_turn": [count_tokens(f"[{t['role']}] {t['content']}") for t in turns],
    }
