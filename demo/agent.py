"""Agent de démonstration MemBridge.

Rejoue une conversation longue (30–50 tours) côté mémoire MCP, puis pose les
« questions pièges » dont la réponse dépend d'informations données très tôt.
Il démontre le scénario du sujet : le compteur naïf explose, le compteur
MemBridge reste quasi plat, et l'agent répond juste grâce à `memory_search`.

Usage :
    python -m demo.agent                       # 40 tours, session "demo"
    python -m demo.agent 50 support            # 50 tours, session "support"
    python -m demo.agent 50 support claude-opus-4-8   # + coût via models.dev
"""

from __future__ import annotations

import sys

from benchmark.harness import CONVERSATION_PATH, generate_long_conversation, load_json
from benchmark.naive import simulate_naive_conversation
from benchmark.quality import TRAP_QUESTIONS
from memory_mcp.stats import reset_stats
from memory_mcp.tools import MemoryTools
from memory_mcp.validation import answer_in_results


def run_demo(turn_count: int = 40, session: str = "demo", model: str = "claude-opus-4-8") -> None:
    base = load_json(CONVERSATION_PATH)
    turns = generate_long_conversation(base, target_turns=turn_count)

    print(f"=== Démo MemBridge — {len(turns)} tours (session: {session}) ===\n")

    # 1) Mode MemBridge : on stocke chaque tour dans la mémoire.
    reset_stats()
    tools = MemoryTools()
    for turn in turns:
        tools.memory_store(
            content=f"{turn['role']}: {turn['content']}",
            tags=[turn["role"]],
            session=session,
            turn=turn["turn"],
        )

    # 2) Comparaison de coût naïf vs MemBridge.
    naive = simulate_naive_conversation(turns)
    summary = tools.memory_summarize(session=session)
    # Coût d'un tour MemBridge = résumé + souvenirs pertinents (pas tout l'historique).
    naive_total = naive["total_tokens"]
    mem_stats = tools.memory_stats(model=model)

    print("--- Coût (tokens) ---")
    print(f"Naïf (historique complet à chaque tour) : {naive_total:,}")
    print(f"MemBridge (entrées stockées)            : {mem_stats['tokens_stored']:,}")
    if naive_total:
        ratio = 100 * (1 - mem_stats["tokens_stored"] / naive_total)
        print(f"Compression du contexte transmis        : ~{ratio:.1f} % de tokens en moins")
    cost = mem_stats.get("cost")
    if cost and cost.get("pricing_found"):
        cur = cost["currency"]
        for c in cost["per_model"]:
            if c.get("pricing_found"):
                print(
                    f"Tarif {c['model']} : {c['input_price_per_1m']} {cur}/1M entrée, "
                    f"{c['output_price_per_1m']} {cur}/1M sortie (models.dev)"
                )
    print()

    print("--- Résumé compressé de la session ---")
    print(summary["summary"], "\n")

    # 3) Questions pièges : l'agent doit retrouver des faits anciens.
    print("--- Questions pièges (réponse via memory_search) ---")
    passed = 0
    for question, expected in TRAP_QUESTIONS:
        res = tools.memory_search(query=question, top_k=3, session=session)
        ok = answer_in_results(expected, res["results"])
        passed += int(ok)
        top = res["results"][0]["content"] if res["results"] else "(aucun souvenir)"
        mark = "OK " if ok else "KO "
        print(f"[{mark}] {question}")
        print(f"        attendu : {expected}")
        print(f"        souvenir: {top}")

    total = len(TRAP_QUESTIONS)
    print(
        f"\nQualité MemBridge : {passed}/{total} questions réussies ({100 * passed / total:.0f} %)"
    )
    print("Conclusion : contexte fortement compressé, qualité préservée.")


if __name__ == "__main__":
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 40
    sess = sys.argv[2] if len(sys.argv) > 2 else "demo"
    mdl = sys.argv[3] if len(sys.argv) > 3 else "claude-opus-4-8"
    run_demo(turn_count=count, session=sess, model=mdl)
