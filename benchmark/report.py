"""Génère le rapport complet du benchmark (tokens, courbes, €, qualité) → report.json.

C'est la source de vérité du tableau de bord : il rejoue la même conversation en mode naïf et
en mode MemBridge, mesure tout, et écrit un JSON consommé par la plateforme web.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

from benchmark.quality import evaluate_memory_quality, evaluate_naive_quality
from memory_mcp.stats import count_tokens, reset_stats
from memory_mcp.tools import MemoryTools

ROOT = Path(__file__).parent
SCENARIO_PATH = ROOT / "scenario.json"
RESULTS_DIR = ROOT / "results"
REPORT_PATH = RESULTS_DIR / "report.json"

DEFAULT_PRICE_PER_MTOK = float(os.getenv("MEMBRIDGE_PRICE_PER_MTOK", "0.15"))


def load_scenario(path: Path = SCENARIO_PATH) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def build_report(
    scenario: dict | None = None, price_per_mtok: float = DEFAULT_PRICE_PER_MTOK
) -> dict:
    scenario = scenario or load_scenario()
    turns = scenario["turns"]
    session = scenario.get("session", "demo")
    traps = scenario.get("trap_questions", [])

    reset_stats()
    tools = MemoryTools()

    naive_per_turn: list[int] = []
    naive_cumulative: list[int] = []
    memory_per_turn: list[int] = []
    memory_cumulative: list[int] = []

    history: list[str] = []
    naive_running = 0
    memory_running = 0

    for turn in turns:
        line = f"[{turn['role']}] {turn['content']}"
        history.append(line)

        # Mode naïf : on renvoie tout l'historique à chaque tour.
        naive_ctx = count_tokens("\n".join(history))
        naive_per_turn.append(naive_ctx)
        naive_running += naive_ctx
        naive_cumulative.append(naive_running)

        # Mode MemBridge : on stocke puis on ne renvoie que résumé + souvenirs pertinents.
        tools.memory_store(
            content=f"{turn['role']}: {turn['content']}",
            tags=[turn["role"]],
            session=session,
            turn=turn["turn"],
        )
        summary = tools.memory_summarize(session=session)["summary"]
        search = tools.memory_search(turn["content"], top_k=3, session=session)
        mem_ctx = count_tokens(summary + "\n" + "\n".join(r["content"] for r in search["results"]))
        memory_per_turn.append(mem_ctx)
        memory_running += mem_ctx
        memory_cumulative.append(memory_running)

    naive_total = naive_cumulative[-1] if naive_cumulative else 0
    memory_total = memory_cumulative[-1] if memory_cumulative else 0
    saved = naive_total - memory_total
    savings_pct = round(100 * saved / naive_total, 1) if naive_total else 0.0
    euros_saved = round(saved / 1_000_000 * price_per_mtok, 6)

    full_history = "\n".join(history)
    q_memory = evaluate_memory_quality(tools, session, traps)
    q_naive = evaluate_naive_quality(full_history, traps)

    return {
        "scenario": {
            "title": scenario.get("title", ""),
            "persona": scenario.get("persona", ""),
            "turns": len(turns),
            "session": session,
        },
        "embedder": tools.store.embedder.name,
        "modes": {
            "naive": {
                "total_tokens": naive_total,
                "per_turn": naive_per_turn,
                "cumulative": naive_cumulative,
            },
            "memory": {
                "total_tokens": memory_total,
                "per_turn": memory_per_turn,
                "cumulative": memory_cumulative,
                "compression_ratio": round(
                    tools.memory_summarize(session=session)["compressed_chars"]
                    / max(sum(len(t["content"]) for t in turns), 1),
                    4,
                ),
            },
        },
        "savings": {
            "tokens": saved,
            "pct": savings_pct,
            "euros": euros_saved,
            "price_per_mtok": price_per_mtok,
            "euros_per_1k_conversations": round(euros_saved * 1_000, 2),
            "euros_per_100k_conversations": round(euros_saved * 100_000, 2),
        },
        "quality": {
            "passed": q_memory["passed"],
            "total": q_memory["total"],
            "score_pct": q_memory["score_pct"],
            "naive_passed": q_naive["passed"],
            "naive_score_pct": q_naive["score_pct"],
            "memory_context_tokens": q_memory["context_tokens"],
            "naive_context_tokens": q_naive["context_tokens"],
            "details": q_memory["details"],
        },
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }


def save_report(report: dict, path: Path = REPORT_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def main() -> None:
    report = build_report()
    out = save_report(report)
    s = report["savings"]
    q = report["quality"]
    print(f"Embedder        : {report['embedder']}")
    print(f"Naïf            : {report['modes']['naive']['total_tokens']:,} tokens")
    print(f"MemBridge       : {report['modes']['memory']['total_tokens']:,} tokens")
    print(f"Économie        : {s['pct']}%  ({s['tokens']:,} tokens ≈ {s['euros']} €)")
    print(f"Qualité mémoire : {q['passed']}/{q['total']}  ({q['score_pct']}%)")
    print(f"Rapport écrit   : {out}")


if __name__ == "__main__":
    main()
