"""Agent support client — démo MemBridge (50 tours + questions pièges)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))

from benchmark.harness import (  # noqa: E402, I001
    generate_long_conversation,
    load_json,
    run_benchmark,
    save_report,
)
from benchmark.quality import evaluate_quality  # noqa: E402
from benchmark.scoring import per_turn_context_tokens  # noqa: E402
from memory_mcp.stats import reset_stats  # noqa: E402
from memory_mcp.tools import MemoryTools  # noqa: E402

CONVERSATION = ROOT / "benchmark" / "conversation.json"


def run_live_demo(session: str = "demo-live", turns: int = 50) -> None:
    """Simule l'agent support client avec MemBridge."""
    reset_stats()
    tools = MemoryTools()
    base = load_json(CONVERSATION)
    conversation = generate_long_conversation(base, target_turns=turns)

    print("=" * 60)
    print("  MemBridge — Agent Support Client (démo live)")
    print("=" * 60)

    recent_lines: list[str] = []

    for turn in conversation:
        line = f"{turn['role']}: {turn['content']}"
        tools.memory_store(
            content=line,
            tags=[turn["role"], "support"],
            session=session,
            turn=turn["turn"],
        )
        ctx_tokens = per_turn_context_tokens(tools, session, turn["content"], recent_lines)
        recent_lines.append(line)
        print(f"  Tour {turn['turn']:2d} | ctx={ctx_tokens:3d} tok | {turn['content'][:55]}...")

    print("\n--- Résumé session ---")
    summary = tools.memory_summarize(session=session)
    print(summary["summary"][:400])

    print("\n--- Questions pièges ---")
    quality = evaluate_quality(tools, session=session)
    for d in quality["details"]:
        mark = "✓" if d["passed"] else "✗"
        print(f"  {mark} {d['question']}")
        print(f"      → attendu: {d['expected']}")

    print(f"\n  Qualité: {quality['passed']}/{quality['total']} ({quality['score_pct']}%)")
    print("\n--- Stats ---")
    print(json.dumps(tools.memory_stats(), indent=2, ensure_ascii=False))


def run_full_benchmark() -> None:
    """Lance benchmark complet + sauvegarde rapport dashboard."""
    report = run_benchmark(turn_count=50)
    path = save_report(report)
    print(f"\nÉconomie: {report['savings_pct']}% | Qualité: {report['quality']['score_pct']}%")
    print(f"Coût évité: {report['cost_saved_eur']} €")
    print(f"Rapport: {path}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "benchmark":
        run_full_benchmark()
    else:
        run_live_demo()
