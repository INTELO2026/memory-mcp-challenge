"""Agent de démo — conversation longue + questions pièges via mémoire MCP."""

from __future__ import annotations

import json
from pathlib import Path

from benchmark.harness import TRAP_QUESTIONS, generate_long_conversation, load_json
from memory_mcp.tools import MemoryTools
from memory_mcp.validation import top1_contains

ROOT = Path(__file__).parent.parent
CONVERSATION = ROOT / "benchmark" / "conversation.json"


def answer_from_memory(tools: MemoryTools, session: str, question: str) -> str:
    """Répond à une question en s'appuyant sur memory_search + memory_summarize."""
    hits = tools.memory_search(question, top_k=3, session=session)
    summary = tools.memory_summarize(session=session)
    if hits["results"]:
        best = hits["results"][0]["content"]
        return f"D'après la mémoire : {best}"
    if summary["summary"]:
        return f"D'après le résumé : {summary['summary']}"
    return "Je n'ai pas trouvé cette information en mémoire."


def run_demo(session: str = "demo", target_turns: int = 50) -> None:
    """Joue une conversation de démo avec le serveur mémoire."""
    tools = MemoryTools()
    base = load_json(CONVERSATION)
    turns = generate_long_conversation(base, target_turns=target_turns)

    print(f"=== Démo agent mémoire (session: {session}) ===\n")
    for turn in turns:
        tags = ["fact"] if turn["role"] == "user" else ["assistant"]
        tools.memory_store(
            content=f"{turn['role']}: {turn['content']}",
            tags=tags,
            session=session,
            turn=turn["turn"],
        )
        if turn["turn"] <= 10 or turn["turn"] % 10 == 0:
            print(f"Tour {turn['turn']:>2} — stocké")

    print(f"\n... {target_turns} tours stockés.\n")
    summary = tools.memory_summarize(session=session)
    stats = tools.memory_stats()
    print(f"Résumé ({summary['source_turns']} tours → {summary['compressed_chars']} car.) :")
    print(summary["summary"])
    print(f"\nStats tokens : {json.dumps(stats, indent=2)}")

    print("\n=== Questions pièges ===\n")
    passed = 0
    for question, expected in TRAP_QUESTIONS:
        hits = tools.memory_search(question, top_k=1, session=session)
        ok = top1_contains(expected, hits["results"])
        passed += int(ok)
        status = "OK" if ok else "FAIL"
        answer = answer_from_memory(tools, session, question)
        print(f"[{status}] {question}")
        print(f"       attendu : {expected}")
        print(f"       réponse : {answer}\n")

    print(f"Score pièges : {passed}/{len(TRAP_QUESTIONS)}")


if __name__ == "__main__":
    run_demo()
