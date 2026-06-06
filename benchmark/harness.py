"""Harnais de benchmark : compare mode naïf vs serveur mémoire MCP."""

from __future__ import annotations

import json
from pathlib import Path

from benchmark.naive import simulate_naive_conversation
from benchmark.quality import evaluate_quality
from benchmark.scoring import compression_ratio, context_growth_factor, per_turn_context_tokens
from memory_mcp.stats import reset_stats
from memory_mcp.tools import MemoryTools

ROOT = Path(__file__).parent
CONVERSATION_PATH = ROOT / "conversation.json"
RESULTS_DIR = ROOT / "results"
REPORT_PATH = RESULTS_DIR / "report.json"

# Prix Claude Sonnet input (USD/M tokens) × taux EUR
INPUT_USD_PER_M = 3.0
EUR_USD = 0.92


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
    """Simule une conversation avec le serveur mémoire."""
    reset_stats()
    tools = MemoryTools()
    total_context_tokens = 0
    per_turn: list[int] = []

    for turn in turns:
        role = turn["role"]
        content = turn["content"]
        tools.memory_store(
            content=f"{role}: {content}",
            tags=[role, f"turn-{turn['turn']}"],
            session=session,
            turn=turn["turn"],
        )
        tokens = per_turn_context_tokens(tools, session, content)
        total_context_tokens += tokens
        per_turn.append(tokens)

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


def save_report(report: dict) -> Path:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return REPORT_PATH


def main() -> None:
    report = run_benchmark()
    path = save_report(report)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"\nRapport sauvegarde : {path}")


if __name__ == "__main__":
    main()
