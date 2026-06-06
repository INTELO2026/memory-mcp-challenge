"""Harnais de benchmark : compare mode naïf vs serveur mémoire MCP."""

from __future__ import annotations

import json
import random
from pathlib import Path

from benchmark.naive import build_naive_context, simulate_naive_conversation
from benchmark.quality import evaluate_quality
from benchmark.scoring import compression_ratio, context_growth_factor, per_turn_context_tokens
from memory_mcp.stats import get_stats, reset_stats
from memory_mcp.tools import MemoryTools

ROOT = Path(__file__).parent
CONVERSATION_PATH = ROOT / "conversation.json"
RESULTS_DIR = ROOT / "results"
REPORT_PATH = RESULTS_DIR / "report.json"

# Prix Claude Sonnet input (USD/M tokens) × taux EUR
INPUT_USD_PER_M = 3.0
EUR_USD = 0.92
BENCHMARK_SEED = 42
CONSOLIDATE_EVERY = 5


def load_json(path: Path) -> list | dict:
    return json.loads(path.read_text(encoding="utf-8"))


def generate_long_conversation(base_turns: list[dict], target_turns: int = 40) -> list[dict]:
    """Étend une conversation courte en alternant rôles jusqu'à target_turns."""
    turns = list(base_turns)
    turn_num = len(turns) + 1
    roles = ("user", "assistant")
    while len(turns) < target_turns:
        role = roles[(turn_num - 1) % 2]
        turns.append(
            {
                "turn": turn_num,
                "role": role,
                "content": f"Échange {turn_num} — précision contextuelle pour le tour {turn_num}.",
            }
        )
        turn_num += 1
    return turns


def simulate_memory_conversation(turns: list[dict], session: str = "benchmark") -> dict:
    """Simule une conversation avec le serveur mémoire (master prompt §8.1)."""
    reset_stats()
    random.seed(BENCHMARK_SEED)
    tools = MemoryTools()
    total_context_tokens = 0
    per_turn: list[int] = []
    recent_lines: list[str] = []

    for turn in turns:
        role = turn["role"]
        content = turn["content"]
        line = f"{role}: {content}"
        tools.memory_store(
            content=line,
            tags=[role, f"turn-{turn['turn']}"],
            session=session,
            turn=turn["turn"],
        )

        if turn["turn"] % CONSOLIDATE_EVERY == 0:
            tools.memory_summarize(session=session, max_chars=180)

        ctx_tokens = per_turn_context_tokens(tools, session, content, recent_lines)
        total_context_tokens += ctx_tokens
        per_turn.append(ctx_tokens)
        recent_lines.append(line)

        history = [{"role": t["role"], "content": t["content"]} for t in turns[: turn["turn"]]]
        _, naive_tokens = build_naive_context(history)
        get_stats().record_turn(session, naive_tokens, ctx_tokens)

    stats = tools.memory_stats()
    quality = evaluate_quality(tools, session=session)
    return {
        "mode": "memory",
        "turns": len(turns),
        "total_tokens": total_context_tokens,
        "per_turn": per_turn,
        "growth_factor": context_growth_factor(per_turn) if per_turn else 0.0,
        "compression_ratio": compression_ratio(tools, session),
        "stats": stats,
        "quality": quality,
        "_tools": tools,
    }


def run_benchmark(turn_count: int = 50) -> dict:
    """Lance le benchmark complet et retourne le rapport."""
    random.seed(BENCHMARK_SEED)
    base = load_json(CONVERSATION_PATH)
    turns = generate_long_conversation(base, target_turns=turn_count)
    naive = simulate_naive_conversation(turns)
    memory = simulate_memory_conversation(turns)
    quality = memory.pop("quality", {})
    memory.pop("_tools", None)

    savings_pct = 0.0
    if naive["total_tokens"] > 0:
        savings_pct = round(100 * (1 - memory["total_tokens"] / naive["total_tokens"]), 1)

    tokens_saved = naive["total_tokens"] - memory["total_tokens"]
    cost_naive_eur = round(naive["total_tokens"] / 1e6 * INPUT_USD_PER_M * EUR_USD, 4)
    cost_memory_eur = round(memory["total_tokens"] / 1e6 * INPUT_USD_PER_M * EUR_USD, 4)
    cost_saved_eur = round(cost_naive_eur - cost_memory_eur, 4)

    report = {
        "project": "MemBridge",
        "turn_count": turn_count,
        "benchmark_seed": BENCHMARK_SEED,
        "temperature": 0,
        "naive": naive,
        "memory": memory,
        "savings_pct": savings_pct,
        "tokens_saved": tokens_saved,
        "cost_naive_eur": cost_naive_eur,
        "cost_memory_eur": cost_memory_eur,
        "cost_saved_eur": cost_saved_eur,
        "quality": quality,
        "victory": savings_pct >= 70.0 and quality.get("score_pct", 0) >= 80.0,
    }
    return report


def run_reproducibility_check(runs: int = 3, turn_count: int = 50) -> dict:
    """3 runs identiques — variance économie < 5% (master prompt §8.2)."""
    savings: list[float] = []
    for _ in range(runs):
        report = run_benchmark(turn_count=turn_count)
        savings.append(report["savings_pct"])
    mean = sum(savings) / len(savings)
    variance_pct = max(abs(s - mean) for s in savings) if savings else 0.0
    return {
        "runs": runs,
        "savings_pct": savings,
        "mean_savings_pct": round(mean, 1),
        "max_variance_pct": round(variance_pct, 2),
        "reproducible": variance_pct < 5.0,
    }


def save_report(report: dict) -> Path:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return REPORT_PATH


def main() -> None:
    report = run_benchmark()
    path = save_report(report)
    repro = run_reproducibility_check(runs=3)
    report["reproducibility"] = repro
    REPORT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"\nRapport sauvegarde : {path}")


if __name__ == "__main__":
    main()
