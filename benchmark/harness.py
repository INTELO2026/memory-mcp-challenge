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

# Tarif documenté pour chiffrer l'économie en euros : prix d'entrée de
# gpt-4o-mini (0,15 $ / 1 M tokens), converti en euros (~0,92 €/$).
PRICE_PER_1M_TOKENS_USD = 0.15
USD_TO_EUR = 0.92


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
    return {
        "mode": "memory",
        "turns": len(turns),
        "total_tokens": total_context_tokens,
        "per_turn": per_turn,
        "growth_factor": context_growth_factor(per_turn) if per_turn else 0.0,
        "compression_ratio": compression_ratio(tools, session),
        "stats": stats,
    }


def _eur(tokens: int) -> float:
    return round(tokens / 1_000_000 * PRICE_PER_1M_TOKENS_USD * USD_TO_EUR, 4)


def run_benchmark(turn_count: int = 50) -> dict:
    """Lance le benchmark complet (coût + qualité) et retourne le rapport."""
    base = load_json(CONVERSATION_PATH)
    turns = generate_long_conversation(base, target_turns=turn_count)
    naive = simulate_naive_conversation(turns)
    memory = simulate_memory_conversation(turns)
    quality = evaluate_quality(turns)

    savings_pct = 0.0
    if naive["total_tokens"] > 0:
        savings_pct = round(100 * (1 - memory["total_tokens"] / naive["total_tokens"]), 1)

    saved_tokens = naive["total_tokens"] - memory["total_tokens"]
    cost = {
        "price_per_1m_tokens_usd": PRICE_PER_1M_TOKENS_USD,
        "usd_to_eur": USD_TO_EUR,
        "naive_eur": _eur(naive["total_tokens"]),
        "memory_eur": _eur(memory["total_tokens"]),
        "saved_eur": _eur(saved_tokens),
    }

    return {
        "turns": len(turns),
        "naive": naive,
        "memory": memory,
        "savings_pct": savings_pct,
        "saved_tokens": saved_tokens,
        "cost": cost,
        "quality": quality,
    }


def write_report(report: dict, path: Path | None = None) -> Path:
    """Écrit le rapport JSON consommé par le tableau de bord."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    target = path or (RESULTS_DIR / "report.json")
    target.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return target


def main() -> None:
    report = run_benchmark()
    target = write_report(report)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"\nRapport écrit dans {target}")
    q = report["quality"]
    print(
        f"Economie : {report['savings_pct']} % "
        f"({report['saved_tokens']} tokens ~ {report['cost']['saved_eur']} EUR) | "
        f"Qualite MemBridge : {q['passed']}/{q['total']}"
    )


if __name__ == "__main__":
    main()
