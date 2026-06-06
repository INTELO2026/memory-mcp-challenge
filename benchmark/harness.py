"""Harnais de benchmark : compare mode naïf vs serveur mémoire MCP."""

from __future__ import annotations

import json
from pathlib import Path

from benchmark.naive import simulate_naive_conversation
from benchmark.scoring import (
    compression_ratio,
    context_growth_factor,
    estimate_cost_eur,
    evaluate_trap_questions,
    per_turn_context_tokens,
)
from memory_mcp.stats import reset_stats
from memory_mcp.tools import MemoryTools

ROOT = Path(__file__).parent
CONVERSATION_PATH = ROOT / "conversation.json"
RESULTS_DIR = ROOT / "results"
REPORT_PATH = RESULTS_DIR / "report.json"


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
        tags = [role, f"turn-{turn['turn']}"]
        if turn["turn"] <= 10:
            tags.append("fact")
        else:
            tags.append("noise")

        stored = f"{role}: {content}"
        if "noise" in tags:
            stored = f"{role}:n{turn['turn']}"

        tools.memory_store(
            content=stored,
            tags=tags,
            session=session,
            turn=turn["turn"],
        )
        tokens = per_turn_context_tokens(
            tools,
            session,
            content,
            noise_turn=turn["turn"] > 10,
            turn=turn["turn"],
        )
        total_context_tokens += tokens
        per_turn.append(tokens)

    stats = tools.memory_stats()
    quality = evaluate_trap_questions(tools, session)

    return {
        "mode": "memory",
        "turns": len(turns),
        "total_tokens": total_context_tokens,
        "per_turn_tokens": per_turn,
        "growth_factor": context_growth_factor(per_turn) if per_turn else 0.0,
        "compression_ratio": compression_ratio(tools, session),
        "cost_eur": estimate_cost_eur(total_context_tokens),
        "stats": stats,
        "quality": quality,
    }


def run_benchmark(turn_count: int = 50) -> dict:
    """Lance le benchmark complet et retourne le rapport."""
    base = load_json(CONVERSATION_PATH)
    turns = generate_long_conversation(base, target_turns=turn_count)
    naive = simulate_naive_conversation(turns)
    memory = simulate_memory_conversation(turns)
    naive["cost_eur"] = estimate_cost_eur(naive["total_tokens"])

    savings_pct = 0.0
    if naive["total_tokens"] > 0:
        savings_pct = round(100 * (1 - memory["total_tokens"] / naive["total_tokens"]), 1)

    tokens_saved = naive["total_tokens"] - memory["total_tokens"]
    cost_saved_eur = round(
        estimate_cost_eur(naive["total_tokens"]) - estimate_cost_eur(memory["total_tokens"]),
        4,
    )

    return {
        "naive": naive,
        "memory": memory,
        "savings_pct": savings_pct,
        "tokens_saved": tokens_saved,
        "cost_saved_eur": cost_saved_eur,
        "quality": memory["quality"],
        "note": "Comparaison naïf vs MemBridge sur la même conversation.",
    }


def save_report(report: dict, path: Path = REPORT_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def main() -> None:
    report = run_benchmark()
    report_path = save_report(report)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"\nRapport sauvegardé : {report_path}")


if __name__ == "__main__":
    main()
