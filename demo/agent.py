"""Agent de démonstration MemBridge.

Joue une conversation longue (30+ tours) de support client en s'appuyant sur le
serveur mémoire, puis :
  1. compare le coût en tokens mode naïf vs mode MemBridge,
  2. pose des questions « pièges » dont la réponse dépend d'infos données plus tôt,
     et montre que l'agent répond juste grâce à memory_search.
"""

from __future__ import annotations

import json
from pathlib import Path

from benchmark.harness import (
    CONVERSATION_PATH,
    EUR_PER_1K_TOKENS,
    QUALITY_PROBES,
    generate_long_conversation,
    tokens_to_eur,
)
from benchmark.naive import build_naive_context
from benchmark.scoring import per_turn_context_tokens
from memory_mcp.stats import reset_stats
from memory_mcp.tools import MemoryTools
from memory_mcp.validation import normalize_text

ROOT = Path(__file__).parent.parent


def _answer_from_memory(tools: MemoryTools, session: str, question: str) -> tuple[str, str, list]:
    """L'agent récupère les souvenirs pertinents (top-3) et y puise sa réponse."""
    hits = tools.memory_search(question, top_k=3, session=session)
    if not hits["results"]:
        return "(aucun souvenir pertinent)", "", []
    snippets = [r["content"] for r in hits["results"]]
    context = normalize_text(" ".join(snippets))
    return snippets[0], context, snippets


def run_demo(session: str = "demo", turns_count: int = 30) -> dict:
    """Joue la conversation, mesure les deux modes et teste les questions pièges."""
    reset_stats()
    base = json.loads(CONVERSATION_PATH.read_text(encoding="utf-8"))
    turns = generate_long_conversation(base, target_turns=turns_count)

    tools = MemoryTools()
    naive_history: list[dict] = []
    naive_total = 0
    memory_total = 0

    print(f"=== Démo MemBridge — conversation de {len(turns)} tours (session: {session}) ===\n")
    for turn in turns:
        # Mode naïf : tout l'historique renvoyé à chaque tour.
        naive_history.append({"role": turn["role"], "content": turn["content"]})
        _, naive_tokens = build_naive_context(naive_history)
        naive_total += naive_tokens

        # Mode MemBridge : on stocke le tour puis on ne renvoie au modèle que le
        # contexte compact (résumé + souvenirs pertinents) — coût quasi plat.
        tools.memory_store(
            content=f"{turn['role']}: {turn['content']}",
            tags=[turn["role"]],
            session=session,
            turn=turn["turn"],
            importance=1.5 if turn["role"] == "user" else 1.0,
        )
        memory_total += per_turn_context_tokens(tools, session, turn["content"])

    savings_pct = round(100 * (1 - memory_total / naive_total), 1) if naive_total else 0.0
    print("--- Coût ---")
    print(f"Mode naïf      : {naive_total:>7} tokens  ≈ {tokens_to_eur(naive_total)} €")
    print(f"Mode MemBridge : {memory_total:>7} tokens  ≈ {tokens_to_eur(memory_total)} €")
    print(f"Économie       : {savings_pct} %  ({naive_total - memory_total} tokens)\n")

    print("--- Questions pièges (réponses via memory_search) ---")
    passed = 0
    for question, expected in QUALITY_PROBES:
        answer, context, _ = _answer_from_memory(tools, session, question)
        ok = bool(context) and normalize_text(expected) in context
        passed += ok
        flag = "OK " if ok else "KO "
        print(f"[{flag}] Q: {question}\n        → {answer}")
    print(f"\nQualité maintenue : {passed}/{len(QUALITY_PROBES)} questions réussies")

    return {
        "naive_tokens": naive_total,
        "memory_tokens": memory_total,
        "savings_pct": savings_pct,
        "quality": {"passed": passed, "total": len(QUALITY_PROBES)},
        "rate_eur_per_1k": EUR_PER_1K_TOKENS,
    }


if __name__ == "__main__":
    run_demo()
