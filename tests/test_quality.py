"""Axe qualité : les questions pièges doivent rester answerable en mode mémoire.

Économiser des tokens en rendant l'agent amnésique ne compte pas : on vérifie
ici que la recherche sémantique ramène bien les faits attendus malgré le bruit
d'une longue conversation.
"""

from __future__ import annotations

from benchmark.harness import CONVERSATION_PATH, generate_long_conversation, load_json
from benchmark.quality import (
    TRAP_QUESTIONS,
    evaluate_memory_quality,
    evaluate_naive_quality,
)
from memory_mcp.tools import MemoryTools


def _seed_memory(session: str, turn_count: int = 40) -> MemoryTools:
    turns = generate_long_conversation(load_json(CONVERSATION_PATH), target_turns=turn_count)
    tools = MemoryTools()
    for turn in turns:
        tools.memory_store(
            content=f"{turn['role']}: {turn['content']}",
            tags=[turn["role"]],
            session=session,
            turn=turn["turn"],
        )
    return tools


def test_naive_mode_knows_everything():
    """Le mode naïf a tout l'historique : il doit réussir toutes les pièges."""
    turns = generate_long_conversation(load_json(CONVERSATION_PATH), target_turns=40)
    q = evaluate_naive_quality(turns)
    assert q["passed"] == q["total"] == len(TRAP_QUESTIONS)


def test_memory_mode_maintains_quality():
    """MemBridge doit retrouver l'essentiel des faits malgré la compression."""
    tools = _seed_memory("quality")
    q = evaluate_memory_quality(tools, "quality")
    # Seuil prudent : tolère quelques échecs liés au repli lexical hors-ligne,
    # mais garantit que l'agent n'est pas amnésique.
    assert q["passed"] >= 7, f"Qualité insuffisante : {q['passed']}/{q['total']} ({q['details']})"
