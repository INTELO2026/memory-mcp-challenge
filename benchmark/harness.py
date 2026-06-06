"""Harnais de benchmark : compare mode naïf vs serveur mémoire MCP (MemBridge).

Produit un rapport chiffré (tokens, économie %, coût €, qualité sur questions
pièges) et l'exporte en JSON pour le tableau de bord.

Règle d'or : la MÊME conversation scriptée est rejouée à l'identique dans les
deux modes, sinon la comparaison serait invalide.
"""

from __future__ import annotations

import json
from pathlib import Path

from benchmark.naive import simulate_naive_conversation
from benchmark.scoring import compression_ratio, context_growth_factor, per_turn_context_tokens
from memory_mcp.stats import reset_stats
from memory_mcp.tools import MemoryTools
from memory_mcp.validation import answer_in_results

ROOT = Path(__file__).parent
CONVERSATION_PATH = ROOT / "conversation.json"
SCENARIO_PATH = ROOT / "scenario.json"
RESULTS_DIR = ROOT / "results"
REPORT_PATH = RESULTS_DIR / "report.json"

# Tarif indicatif (entrée), ex. classe gpt-4o-mini : 0,15 $/1M ≈ 0,14 €/1M.
PRICE_EUR_PER_1M_TOKENS = 0.14


def load_json(path: Path) -> list | dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_scenario() -> dict:
    return load_json(SCENARIO_PATH)


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
    """Simule une conversation avec le serveur mémoire (contexte compressé)."""
    reset_stats()
    tools = MemoryTools()
    total_context_tokens = 0
    per_turn: list[int] = []
    cumulative: list[int] = []

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
        cumulative.append(total_context_tokens)

    stats = tools.memory_stats()
    return {
        "mode": "memory",
        "turns": len(turns),
        "total_tokens": total_context_tokens,
        "tokens_per_turn": per_turn,
        "cumulative": cumulative,
        "growth_factor": context_growth_factor(per_turn) if per_turn else 0.0,
        "compression_ratio": compression_ratio(tools, session),
        "stats": stats,
    }


def run_quality_eval(traps: list[dict], session: str) -> dict:
    """Mesure la qualité : pour chaque question piège, le souvenir attendu remonte-t-il ?

    Flux réaliste : on rejoue le scénario tour par tour ; à un tour piège, on
    interroge ``memory_search`` AVANT de stocker la question (sinon l'agent
    retomberait sur sa propre question au lieu du fait recherché).
    """
    scenario = load_scenario()
    reset_stats()
    tools = MemoryTools()
    by_turn = {t["turn"]: t for t in traps}

    details = []
    passed = 0
    for turn in scenario["turns"]:
        trap = by_turn.get(turn["turn"])
        if trap is not None:
            hits = tools.memory_search(trap["question"], top_k=8, session=session)
            ok = answer_in_results(trap["expected"], hits["results"])
            passed += int(ok)
            details.append(
                {
                    "question": trap["question"],
                    "expected": trap["expected"],
                    "passed": ok,
                    "top_turn": hits["results"][0]["turn"] if hits["results"] else None,
                }
            )
        tools.memory_store(
            content=f"{turn['role']}: {turn['content']}",
            tags=[turn["role"]],
            session=session,
            turn=turn["turn"],
        )

    total = len(traps)
    return {
        "passed": passed,
        "total": total,
        "score_pct": round(100 * passed / total, 1) if total else 0.0,
        "details": details,
    }


def _eur(tokens: int) -> float:
    return round(tokens / 1_000_000 * PRICE_EUR_PER_1M_TOKENS, 6)


def build_report() -> dict:
    """Construit le rapport complet à partir du scénario scripté."""
    scenario = load_scenario()
    turns = scenario["turns"]
    session = scenario.get("session", "support-membridge")

    naive = simulate_naive_conversation(turns)
    memory = simulate_memory_conversation(turns, session=f"{session}-mem")
    quality = run_quality_eval(scenario.get("traps", []), session=f"{session}-q")

    savings_pct = 0.0
    if naive["total_tokens"] > 0:
        savings_pct = round(100 * (1 - memory["total_tokens"] / naive["total_tokens"]), 1)

    cost_naive = _eur(naive["total_tokens"])
    cost_memory = _eur(memory["total_tokens"])

    return {
        "scenario": scenario.get("description", ""),
        "turns": len(turns),
        "naive": naive,
        "memory": memory,
        "savings_pct": savings_pct,
        "savings_tokens": naive["total_tokens"] - memory["total_tokens"],
        "cost": {
            "naive_eur": cost_naive,
            "memory_eur": cost_memory,
            "savings_eur": round(cost_naive - cost_memory, 6),
            "price_eur_per_1m": PRICE_EUR_PER_1M_TOKENS,
        },
        "quality": quality,
        "embedding_backend": memory["stats"].get("embedding_backend", "unknown"),
    }


def run_benchmark(turn_count: int = 50) -> dict:
    """Benchmark synthétique sur la conversation étendue (compat tests/CLI)."""
    base = load_json(CONVERSATION_PATH)
    turns = generate_long_conversation(base, target_turns=turn_count)
    naive = simulate_naive_conversation(turns)
    memory = simulate_memory_conversation(turns)

    savings_pct = 0.0
    if naive["total_tokens"] > 0:
        savings_pct = round(100 * (1 - memory["total_tokens"] / naive["total_tokens"]), 1)

    return {
        "naive": naive,
        "memory": memory,
        "savings_pct": savings_pct,
        "note": "La validation qualité (questions pièges) est uniquement en CI finale.",
    }


def write_report(report: dict | None = None) -> Path:
    """Écrit le rapport complet dans benchmark/results/report.json."""
    report = report or build_report()
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return REPORT_PATH


def main() -> None:
    report = build_report()
    path = write_report(report)
    print(
        f"Backend embeddings : {report['embedding_backend']}\n"
        f"Tours              : {report['turns']}\n"
        f"Tokens naïf        : {report['naive']['total_tokens']:,}\n"
        f"Tokens MemBridge   : {report['memory']['total_tokens']:,}\n"
        f"Économie           : {report['savings_pct']} %  "
        f"({report['savings_tokens']:,} tokens, {report['cost']['savings_eur']} €)\n"
        f"Qualité (pièges)   : {report['quality']['passed']}/{report['quality']['total']} "
        f"({report['quality']['score_pct']} %)\n"
        f"Rapport écrit      : {path}"
    )


if __name__ == "__main__":
    main()
