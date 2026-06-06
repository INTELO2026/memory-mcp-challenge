"""Test MCP + publication live dashboard avec pourcentage."""

from __future__ import annotations

import json
from pathlib import Path

from memory_mcp.live import reset_live
from memory_mcp.stats import reset_stats
from memory_mcp.tools import MemoryTools
from memory_mcp.validation import top1_contains

ROOT = Path(__file__).resolve().parents[1]
LIVE_PATH = ROOT / "dashboard" / "live.json"
CONVERSATION_PATH = ROOT / "benchmark" / "conversation.json"
TURN_COUNT = 50


def load_turns() -> list[tuple[str, str]]:
    base = json.loads(CONVERSATION_PATH.read_text(encoding="utf-8"))
    turns = [(t["role"], t["content"]) for t in base]
    turn_num = len(turns) + 1
    roles = ("user", "assistant")
    while len(turns) < TURN_COUNT:
        role = roles[(turn_num - 1) % 2]
        turns.append(
            (
                role,
                f"Échange {turn_num} — précision contextuelle pour le tour {turn_num}.",
            )
        )
        turn_num += 1
    return turns


def main() -> None:
    reset_stats()
    reset_live()
    tools = MemoryTools()
    session = "test-live"
    turns = load_turns()

    print(f"=== Test Live MCP + Pourcentage ({TURN_COUNT} tours) ===\n")

    for i, (role, content) in enumerate(turns, start=1):
        tags = [role, f"turn-{i}"]
        if i <= 10:
            tags.append("fact")
        else:
            tags.append("noise")
        tools.memory_store(f"{role}: {content}", tags=tags, session=session, turn=i)
        if i <= 10 or i % 10 == 0 or i == TURN_COUNT:
            print(f"Tour {i:>2} [{role}] stocke")

    queries = [
        ("identite cliente premium", "Marie Dupont"),
        ("numero contrat", "CTR-2024-8847"),
        ("montant facture mars", "149,90"),
        ("date bug mobile", "12 février"),
        ("email contact", "marie.dupont@email.fr"),
    ]

    passed = 0
    print("\n--- Questions pieges ---")
    for query, expected in queries:
        result = tools.memory_search(query, top_k=1, session=session)
        ok = top1_contains(expected, result["results"])
        passed += int(ok)
        print(f"[{'OK' if ok else 'FAIL'}] {query}")

    summary = tools.memory_summarize(session=session)
    stats = tools.memory_stats()
    live = json.loads(LIVE_PATH.read_text(encoding="utf-8"))
    savings = live.get("savings", {})

    print(f"\nResume: {summary['summary']}")
    print(f"Stats MCP: {stats['total_tokens']} tokens")
    print("\n--- Economie LIVE ---")
    print(f"  Pourcentage : {savings.get('savings_pct', 0)}%")
    print(f"  Naif        : {savings.get('naive_tokens', 0)} tokens")
    print(f"  MemBridge   : {savings.get('memory_tokens', 0)} tokens")
    print(f"  Economises  : {savings.get('tokens_saved', 0)} tokens")
    print(f"  Tours       : {savings.get('turns', 0)}")
    print(f"\nQualite: {passed}/{len(queries)}")
    print("Dashboard: http://localhost:8080/dashboard/ -> Live MCP")


if __name__ == "__main__":
    main()
