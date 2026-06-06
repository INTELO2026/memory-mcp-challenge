"""Agent de démo : tient une longue conversation en consommant le serveur mémoire.

Au lieu de renvoyer tout l'historique au modèle à chaque tour (mode naïf), l'agent
n'envoie que le **résumé compressé** + les **souvenirs pertinents** récupérés par
recherche sémantique. La démo rejoue une conversation de 30 à 50 tours, puis pose
des questions pièges et montre que l'agent retrouve les bons faits — la preuve que
la qualité tient malgré l'économie de tokens (scénario §5 du sujet).

Usage :
    python -m demo.agent          # conversation 40 tours + questions pièges
"""

from __future__ import annotations

import json

from benchmark.harness import CONVERSATION_PATH, generate_long_conversation, load_json
from benchmark.naive import build_naive_context
from benchmark.quality import TRAP_QUESTIONS
from memory_mcp.stats import count_tokens, reset_stats
from memory_mcp.tools import MemoryTools


def run_demo(session: str = "demo", total_turns: int = 40, top_k: int = 3) -> dict:
    """Joue la conversation puis interroge la mémoire ; renvoie un petit bilan."""
    reset_stats()
    tools = MemoryTools()
    base = load_json(CONVERSATION_PATH)
    turns = generate_long_conversation(base, target_turns=total_turns)

    print(f"=== Démo agent mémoire (session: {session}, {len(turns)} tours) ===\n")

    history: list[dict] = []
    naive_tokens = 0
    memory_tokens = 0

    for turn in turns:
        content = f"{turn['role']}: {turn['content']}"
        tools.memory_store(content=content, tags=[turn["role"]], session=session, turn=turn["turn"])
        history.append({"role": turn["role"], "content": turn["content"]})

        # Ce que le mode naïf enverrait : tout l'historique.
        _, naive_ctx = build_naive_context(history)
        naive_tokens += naive_ctx

        # Ce que MemBridge envoie : résumé + souvenirs pertinents.
        summary = tools.memory_summarize(session=session)["summary"]
        hits = tools.memory_search(turn["content"], top_k=top_k, session=session)["results"]
        mem_ctx = summary + "\n" + "\n".join(h["content"] for h in hits)
        memory_tokens += count_tokens(mem_ctx)

    print("— Questions pièges (réponses dépendantes d'infos passées) —")
    correct = 0
    for question, expected in TRAP_QUESTIONS:
        hits = tools.memory_search(question, top_k=top_k, session=session)["results"]
        top = hits[0]["content"] if hits else "(aucun souvenir)"
        found = any(expected.lower() in h["content"].lower() for h in hits)
        correct += found
        flag = "OK" if found else "??"
        print(f"  [{flag}] {question}\n        -> souvenir top-1 : {top}")

    saved = naive_tokens - memory_tokens
    savings_pct = round(100 * (1 - memory_tokens / naive_tokens), 1) if naive_tokens else 0.0
    stats = tools.memory_stats()

    print("\n— Bilan —")
    print(f"  Contexte naïf cumulé   : {naive_tokens} tokens")
    print(f"  Contexte MemBridge     : {memory_tokens} tokens")
    print(f"  Économie               : {savings_pct} % ({saved} tokens)")
    print(f"  Questions pièges OK     : {correct}/{len(TRAP_QUESTIONS)}")
    print(f"  Stats outils           : {json.dumps(stats)}")

    return {
        "turns": len(turns),
        "naive_tokens": naive_tokens,
        "memory_tokens": memory_tokens,
        "savings_pct": savings_pct,
        "trap_passed": correct,
        "trap_total": len(TRAP_QUESTIONS),
    }


if __name__ == "__main__":
    run_demo()
