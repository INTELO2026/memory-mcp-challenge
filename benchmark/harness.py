"""Harnais de benchmark : compare mode naïf vs serveur mémoire MCP."""

from __future__ import annotations

import json
from pathlib import Path

from benchmark.naive import simulate_naive_conversation
from benchmark.scoring import compression_ratio, context_growth_factor, per_turn_context_tokens
from memory_mcp.stats import reset_stats
from memory_mcp.tools import MemoryTools
from memory_mcp.validation import top1_contains

ROOT = Path(__file__).parent
CONVERSATION_PATH = ROOT / "conversation.json"
RESULTS_PATH = ROOT / "results" / "report.json"
TRAP_QUESTIONS = [
    ("identité de l'interlocutrice premium", "Marie Dupont"),
    ("référence légale du dossier client", "CTR-2024-8847"),
    ("coordonnées électroniques de contact", "marie.dupont@email.fr"),
    ("écart tarifaire facturation printemps", "149,90"),
    ("incident application mobile date", "12 février"),
]
EUR_PER_1K_TOKENS = 0.003


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
    cumulative: list[int] = []
    running = 0
    for t in per_turn:
        running += t
        cumulative.append(running)

    return {
        "mode": "memory",
        "turns": len(turns),
        "total_tokens": total_context_tokens,
        "tokens_per_turn": per_turn,
        "cumulative_tokens": cumulative,
        "growth_factor": context_growth_factor(per_turn) if per_turn else 0.0,
        "compression_ratio": compression_ratio(tools, session),
        "stats": stats,
    }


def evaluate_trap_questions(session: str = "benchmark-traps") -> dict:
    """Vérifie que memory_search répond aux questions pièges."""
    reset_stats()
    tools = MemoryTools()
    base = load_json(CONVERSATION_PATH)
    for turn in base:
        tags = ["fact"] if turn["role"] == "user" else ["assistant"]
        tools.memory_store(
            content=f"{turn['role']}: {turn['content']}",
            tags=tags,
            session=session,
            turn=turn["turn"],
        )

    passed = 0
    details: list[dict] = []
    for query, expected in TRAP_QUESTIONS:
        result = tools.memory_search(query, top_k=1, session=session)
        ok = top1_contains(expected, result["results"])
        passed += int(ok)
        details.append({"query": query, "expected": expected, "passed": ok})

    total = len(TRAP_QUESTIONS)
    return {
        "passed": passed,
        "total": total,
        "score_pct": round(100 * passed / total, 1) if total else 0.0,
        "details": details,
    }


def run_benchmark(turn_count: int = 50) -> dict:
    """Lance le benchmark complet et retourne le rapport."""
    base = load_json(CONVERSATION_PATH)
    turns = generate_long_conversation(base, target_turns=turn_count)
    naive = simulate_naive_conversation(turns)
    memory = simulate_memory_conversation(turns)
    quality = evaluate_trap_questions()

    savings_pct = 0.0
    if naive["total_tokens"] > 0:
        savings_pct = round(100 * (1 - memory["total_tokens"] / naive["total_tokens"]), 1)

    tokens_saved = naive["total_tokens"] - memory["total_tokens"]
    euros_saved = round(tokens_saved / 1000 * EUR_PER_1K_TOKENS, 4)

    return {
        "naive": naive,
        "memory": memory,
        "savings_pct": savings_pct,
        "tokens_saved": tokens_saved,
        "euros_saved": euros_saved,
        "quality": quality,
        "note": "La validation qualité complète est en CI finale.",
    }


def save_report(report: dict, path: Path = RESULTS_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def main() -> None:
    report = run_benchmark()
    save_report(report)
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
