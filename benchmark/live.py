"""Rejoue le scénario tour par tour en écrivant report.json en continu.

Pensé pour la démo : le tableau de bord interroge report.json toutes les
secondes et voit les deux courbes monter en direct (rouge = naïf qui explose,
verte = MemBridge qui reste plate).

Usage :
    python -m benchmark.live            # cadence par défaut
    python -m benchmark.live --delay 0.2
"""

from __future__ import annotations

import argparse
import json
import time

from benchmark.harness import (
    PRICE_EUR_PER_1M_TOKENS,
    REPORT_PATH,
    RESULTS_DIR,
    _eur,
    load_scenario,
    run_quality_eval,
)
from benchmark.naive import build_naive_context
from benchmark.scoring import per_turn_context_tokens
from memory_mcp import embeddings
from memory_mcp.stats import reset_stats
from memory_mcp.tools import MemoryTools


def _write(payload: dict) -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def run_live(delay: float = 0.35) -> None:
    scenario = load_scenario()
    turns = scenario["turns"]
    session = scenario.get("session", "support-membridge")

    reset_stats()
    tools = MemoryTools()
    history: list[dict] = []

    naive_cum: list[int] = []
    mem_cum: list[int] = []
    labels: list[int] = []
    naive_total = 0
    mem_total = 0

    print(f"Backend embeddings : {embeddings.backend_name()}")
    print("Rejeu live du scénario… (Ctrl+C pour arrêter)\n")

    for turn in turns:
        history.append({"role": turn["role"], "content": turn["content"]})
        _, naive_tokens = build_naive_context(history)
        naive_total += naive_tokens

        tools.memory_store(
            content=f"{turn['role']}: {turn['content']}",
            tags=[turn["role"]],
            session=session,
            turn=turn["turn"],
        )
        mem_tokens = per_turn_context_tokens(tools, session, turn["content"])
        mem_total += mem_tokens

        labels.append(turn["turn"])
        naive_cum.append(naive_total)
        mem_cum.append(mem_total)

        savings = round(100 * (1 - mem_total / naive_total), 1) if naive_total else 0.0
        _write(
            {
                "live": True,
                "turns": len(turns),
                "current_turn": turn["turn"],
                "labels": labels,
                "naive": {"total_tokens": naive_total, "cumulative": naive_cum},
                "memory": {"total_tokens": mem_total, "cumulative": mem_cum},
                "savings_pct": savings,
                "savings_tokens": naive_total - mem_total,
                "cost": {
                    "naive_eur": _eur(naive_total),
                    "memory_eur": _eur(mem_total),
                    "savings_eur": round(_eur(naive_total) - _eur(mem_total), 6),
                    "price_eur_per_1m": PRICE_EUR_PER_1M_TOKENS,
                },
                "quality": {"passed": 0, "total": len(scenario.get("traps", [])), "score_pct": 0.0},
                "embedding_backend": embeddings.backend_name(),
            }
        )
        print(
            f"tour {turn['turn']:>2} | naïf {naive_total:>7,} | MemBridge {mem_total:>6,} "
            f"| économie {savings:>5} %"
        )
        time.sleep(delay)

    print("\nÉvaluation qualité (questions pièges)…")
    quality = run_quality_eval(scenario.get("traps", []), session=f"{session}-q")
    final = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
    final["live"] = False
    final["quality"] = quality
    _write(final)
    print(f"Qualité : {quality['passed']}/{quality['total']} ({quality['score_pct']} %)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Rejeu live du benchmark MemBridge")
    parser.add_argument("--delay", type=float, default=0.35, help="Délai entre tours (s)")
    args = parser.parse_args()
    run_live(delay=args.delay)


if __name__ == "__main__":
    main()
