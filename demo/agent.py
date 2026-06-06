"""Agent de démonstration : assistant support client branché sur la mémoire MCP.

Rejoue le scénario scripté, puis répond en direct aux questions pièges en
n'utilisant QUE ``memory_search`` (pas l'historique brut). Affiche aussi la
comparaison de tokens naïf vs MemBridge.
"""

from __future__ import annotations

import json
from pathlib import Path

from benchmark.naive import build_naive_context
from benchmark.scoring import per_turn_context_tokens
from memory_mcp import embeddings
from memory_mcp.stats import reset_stats
from memory_mcp.tools import MemoryTools
from memory_mcp.validation import answer_in_results

ROOT = Path(__file__).parent.parent
SCENARIO = ROOT / "benchmark" / "scenario.json"


def run_demo(session: str = "demo") -> None:
    scenario = json.loads(SCENARIO.read_text(encoding="utf-8"))
    turns = scenario["turns"]
    traps = scenario.get("traps", [])

    reset_stats()
    tools = MemoryTools()
    history: list[dict] = []
    by_turn = {t["turn"]: t for t in traps}
    naive_total = 0
    mem_total = 0
    passed = 0
    trap_lines: list[str] = []

    backend = embeddings.backend_name()
    print(f"=== Démo MemBridge — assistant support client (backend: {backend}) ===\n")
    for turn in turns:
        # Question piège : l'agent répond via la mémoire AVANT de stocker la question.
        trap = by_turn.get(turn["turn"])
        if trap is not None:
            hits = tools.memory_search(trap["question"], top_k=8, session=session)
            ok = answer_in_results(trap["expected"], hits["results"])
            passed += int(ok)
            best = hits["results"][0]["content"] if hits["results"] else "(rien trouvé)"
            flag = "✅" if ok else "❌"
            trap_lines.append(f"{flag} Q: {trap['question']}")
            trap_lines.append(f"    → attendu « {trap['expected']} » | souvenir top: {best[:70]}")

        history.append({"role": turn["role"], "content": turn["content"]})
        _, naive_tokens = build_naive_context(history)
        naive_total += naive_tokens

        tools.memory_store(
            content=f"{turn['role']}: {turn['content']}",
            tags=[turn["role"]],
            session=session,
            turn=turn["turn"],
        )
        mem_total += per_turn_context_tokens(tools, session, turn["content"])

    savings = round(100 * (1 - mem_total / naive_total), 1) if naive_total else 0.0
    print(f"Conversation rejouée : {len(turns)} tours")
    print(f"Tokens mode naïf      : {naive_total:,}")
    print(f"Tokens mode MemBridge : {mem_total:,}")
    print(f"Économie              : {savings} %\n")

    print("--- Questions pièges (réponses via memory_search uniquement) ---")
    print("\n".join(trap_lines))
    print(f"\nQualité : {passed}/{len(traps)} questions pièges réussies")

    summary = tools.memory_summarize(session=session)
    print(f"\nRésumé compressé de session :\n{summary['summary']}")
    print(f"\nStats : {json.dumps(tools.memory_stats(), ensure_ascii=False)}")


if __name__ == "__main__":
    run_demo()
