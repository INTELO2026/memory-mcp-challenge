"""Agent de démonstration MemBridge.

Joue une longue conversation, puis répond à des questions pièges en mode MemBridge
(résumé + souvenirs pertinents) — et montre l'économie de tokens face au mode naïf.

    python -m demo.agent
"""

from __future__ import annotations

import json
from pathlib import Path

from memory_mcp.llm import Agent
from memory_mcp.stats import count_tokens
from memory_mcp.tools import MemoryTools

ROOT = Path(__file__).parent.parent
SCENARIO = ROOT / "benchmark" / "scenario.json"


def run_demo() -> None:
    scenario = json.loads(SCENARIO.read_text(encoding="utf-8"))
    session = scenario.get("session", "demo")
    turns = scenario["turns"]
    traps = scenario.get("trap_questions", [])

    tools = MemoryTools()
    agent = Agent()

    print(f"=== Démo MemBridge — {scenario.get('title', '')} ===")
    print(f"Agent : {agent.backend} | Embeddings : {tools.store.embedder.name}\n")

    history: list[str] = []
    for turn in turns:
        line = f"{turn['role']}: {turn['content']}"
        history.append(line)
        tools.memory_store(content=line, tags=[turn["role"]], session=session, turn=turn["turn"])
    print(f"{len(turns)} tours stockés.\n")

    full_history = "\n".join(history)
    naive_ctx_tokens = count_tokens(full_history)

    print("--- Questions pièges (mode MemBridge) ---\n")
    passed = 0
    for q in traps:
        summary = tools.memory_summarize(session=session, max_chars=400)["summary"]
        hits = tools.memory_search(q["question"], top_k=8, session=session, use_hierarchy=True)
        context = summary + "\n" + "\n".join(r["content"] for r in hits["results"])
        mem_ctx_tokens = count_tokens(context)

        answer = agent.answer(q["question"], context)
        ok = q["expected"].lower() in answer.lower() or any(
            q["expected"].lower() in r["content"].lower() for r in hits["results"]
        )
        passed += ok
        saved_pct = 100 * (1 - mem_ctx_tokens / naive_ctx_tokens) if naive_ctx_tokens else 0
        print(f"Q: {q['question']}")
        print(f"R: {answer}")
        print(
            f"   [{'✓' if ok else '✗'}] attendu='{q['expected']}' | "
            f"contexte: {mem_ctx_tokens} tokens vs {naive_ctx_tokens} (naïf) "
            f"→ -{saved_pct:.0f}%\n"
        )

    print(f"Qualité : {passed}/{len(traps)} questions pièges réussies.")


if __name__ == "__main__":
    run_demo()
