"""Harnais de benchmark : compare mode naïf vs serveur mémoire MCP."""

from __future__ import annotations

import json
from itertools import accumulate
from pathlib import Path

from benchmark.naive import build_naive_context, simulate_naive_conversation
from benchmark.scoring import compression_ratio, context_growth_factor, per_turn_context_tokens
from memory_mcp.stats import reset_stats
from memory_mcp.tools import MemoryTools

ROOT = Path(__file__).parent
CONVERSATION_PATH = ROOT / "conversation.json"
# Le rapport est écrit dans le dashboard (qui le lit via results/report.json).
REPORT_PATH = ROOT.parent / "dashboard" / "results" / "report.json"

# Prix indicatif (gpt-4o-mini, entrée) en euros par 1000 tokens — paramétrable.
EUR_PER_1K_TOKENS = 0.00015

# Questions « pièges » : la réponse dépend d'un fait donné plus tôt dans la conversation.
TRAP_QUESTIONS = [
    ("Comment s'appelle la cliente ?", "Marie Dupont"),
    ("Quel est le numéro de contrat ?", "CTR-2024-8847"),
    ("Quel montant erroné apparaît sur la facture ?", "149,90"),
    ("Quand le bug mobile a-t-il été signalé ?", "12 février"),
    ("Quel est l'email de contact de la cliente ?", "marie.dupont@email.fr"),
]


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


def naive_per_turn(turns: list[dict]) -> list[int]:
    """Taille (tokens) du contexte renvoyé au modèle à chaque tour en mode naïf."""
    history: list[dict] = []
    sizes: list[int] = []
    for turn in turns:
        history.append({"role": turn["role"], "content": turn["content"]})
        _, tokens = build_naive_context(history)
        sizes.append(tokens)
    return sizes


def evaluate_quality(turns: list[dict], session: str = "quality") -> dict:
    """Mesure la qualité : l'agent retrouve-t-il le bon fait pour chaque question piège ?

    Mode naïf : tout l'historique est présent -> il a forcément l'info.
    Mode MemBridge : seuls les souvenirs pertinents (memory_search) sont fournis.
    """
    reset_stats()
    tools = MemoryTools()
    for turn in turns:
        tools.memory_store(
            content=f"{turn['role']}: {turn['content']}",
            session=session,
            turn=turn["turn"],
        )

    full_history = "\n".join(f"{t['role']}: {t['content']}" for t in turns).lower()

    memory_passed = 0
    naive_passed = 0
    details = []
    for question, expected in TRAP_QUESTIONS:
        hits = tools.memory_search(question, top_k=3, session=session)
        retrieved = " ".join(h["content"] for h in hits["results"]).lower()
        mem_ok = expected.lower() in retrieved
        naive_ok = expected.lower() in full_history
        memory_passed += mem_ok
        naive_passed += naive_ok
        details.append({"question": question, "expected": expected, "memory_ok": mem_ok})

    total = len(TRAP_QUESTIONS)
    return {
        "total": total,
        "memory_passed": memory_passed,
        "naive_passed": naive_passed,
        "passed": memory_passed,
        "score_pct": round(100 * memory_passed / total, 1) if total else 0.0,
        "details": details,
    }


def run_benchmark(turn_count: int = 50, with_quality: bool = True) -> dict:
    """Lance le benchmark complet et retourne le rapport."""
    base = load_json(CONVERSATION_PATH)
    turns = generate_long_conversation(base, target_turns=turn_count)
    naive = simulate_naive_conversation(turns)
    memory = simulate_memory_conversation(turns)

    naive_curve = list(accumulate(naive_per_turn(turns)))
    memory_curve = list(accumulate(memory.get("per_turn", [])))

    savings_pct = 0.0
    if naive["total_tokens"] > 0:
        savings_pct = round(100 * (1 - memory["total_tokens"] / naive["total_tokens"]), 1)
    savings_tokens = naive["total_tokens"] - memory["total_tokens"]

    report = {
        "turns": turn_count,
        "naive": {"total_tokens": naive["total_tokens"], "cumulative": naive_curve},
        "memory": {
            "total_tokens": memory["total_tokens"],
            "cumulative": memory_curve,
            "growth_factor": round(memory["growth_factor"], 3),
            "compression_ratio": round(memory["compression_ratio"], 3),
            "stats": memory["stats"],
        },
        "savings_pct": savings_pct,
        "savings_tokens": savings_tokens,
        "pricing": {
            "eur_per_1k_tokens": EUR_PER_1K_TOKENS,
            "naive_eur": round(naive["total_tokens"] / 1000 * EUR_PER_1K_TOKENS, 6),
            "memory_eur": round(memory["total_tokens"] / 1000 * EUR_PER_1K_TOKENS, 6),
            "savings_eur": round(savings_tokens / 1000 * EUR_PER_1K_TOKENS, 6),
        },
        "embedder": _embedder_name(),
    }
    if with_quality:
        report["quality"] = evaluate_quality(turns)
    return report


def _embedder_name() -> str:
    try:
        from memory_mcp.embeddings import get_embedder

        return get_embedder().name
    except Exception:
        return "unknown"


def write_report(report: dict, path: Path = REPORT_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def main() -> None:
    report = run_benchmark()
    out = write_report(report)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"\nRapport écrit dans {out}")


if __name__ == "__main__":
    main()
