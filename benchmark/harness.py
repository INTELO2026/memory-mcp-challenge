"""Harnais de benchmark : compare mode naïf vs serveur mémoire MCP."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from benchmark.naive import simulate_naive_conversation
from benchmark.quality import evaluate_memory_quality, evaluate_naive_quality
from benchmark.scoring import compression_ratio, context_growth_factor, per_turn_context_tokens
from memory_mcp.pricing import normalize_models, price_for
from memory_mcp.stats import reset_stats
from memory_mcp.tools import MemoryTools

ROOT = Path(__file__).parent
CONVERSATION_PATH = ROOT / "conversation.json"
RESULTS_PATH = ROOT / "results" / "report.json"

# Modèle(s) par défaut pour chiffrer le coût (surchargé en CLI : argv[2],
# liste séparée par des virgules ; les slugs acceptent une regex). Plusieurs
# modèles → coûts additionnés. Défaut = modèle récent (Opus 4.8) ; tout slug
# introuvable retombe sur un Sonnet récent.
DEFAULT_MODELS = ["claude-opus-4-8"]


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


def _run_memory(turns: list[dict], session: str) -> tuple[MemoryTools, list[int]]:
    """Rejoue la conversation côté mémoire et renvoie l'outil + la courbe.

    À chaque tour, le contexte envoyé au modèle = résumé compressé + souvenirs
    pertinents (top_k), et NON tout l'historique. La taille reste donc stable
    tour après tour — c'est la garantie de fiabilité de la comparaison.
    """
    reset_stats()
    tools = MemoryTools()
    per_turn: list[int] = []
    for turn in turns:
        tools.memory_store(
            content=f"{turn['role']}: {turn['content']}",
            tags=[turn["role"], f"turn-{turn['turn']}"],
            session=session,
            turn=turn["turn"],
        )
        per_turn.append(per_turn_context_tokens(tools, session, turn["content"]))
    return tools, per_turn


def simulate_memory_conversation(turns: list[dict], session: str = "benchmark") -> dict:
    """Simule une conversation avec le serveur mémoire."""
    tools, per_turn = _run_memory(turns, session)
    return {
        "mode": "memory",
        "turns": len(turns),
        "total_tokens": sum(per_turn),
        "context_per_turn": per_turn,
        "growth_factor": context_growth_factor(per_turn) if per_turn else 0.0,
        "compression_ratio": compression_ratio(tools, session),
        "stats": tools.memory_stats(),
    }


def _cost_per_model(naive_tokens: int, memory_tokens: int, model: str) -> dict:
    """Coût des tokens de contexte (entrée) d'un modèle via models.dev.

    Le slug peut être une regex ; s'il est introuvable, on retombe sur un
    Sonnet récent (champ `fallback_used`).
    """
    pricing = price_for(model)
    if pricing is None:
        return {"model": model, "requested": model, "pricing_found": False}
    price_in = pricing["input"]
    naive_cost = naive_tokens / 1_000_000 * price_in
    memory_cost = memory_tokens / 1_000_000 * price_in
    return {
        "requested": pricing.get("requested", model),
        "model": pricing["model"],
        "provider": pricing["provider"],
        "match": pricing.get("match", "exact"),
        "fallback_used": pricing.get("fallback_used", False),
        "pricing_found": True,
        "source": pricing["source"],
        "input_price_per_1m": price_in,
        "output_price_per_1m": pricing["output"],
        "naive": round(naive_cost, 6),
        "memory": round(memory_cost, 6),
        "saved": round(naive_cost - memory_cost, 6),
    }


def _cost_report(naive_tokens: int, memory_tokens: int, models: list[str]) -> dict:
    """Coût par modèle + total additionné (tokens de contexte facturés en entrée).

    Les tokens comparés sont ceux *envoyés au modèle* à chaque tour (contexte).
    Avec plusieurs modèles, chaque modèle facture la même consommation et les
    coûts sont additionnés — utile pour un pipeline multi-modèles.
    """
    per_model = [_cost_per_model(naive_tokens, memory_tokens, m) for m in models]
    found = [c for c in per_model if c.get("pricing_found")]
    total_naive = sum(c["naive"] for c in found)
    total_memory = sum(c["memory"] for c in found)
    return {
        "currency": "USD",
        "models": models,
        "per_model": per_model,
        "pricing_found": bool(found),
        "total": {
            "naive": round(total_naive, 6),
            "memory": round(total_memory, 6),
            "saved": round(total_naive - total_memory, 6),
        },
    }


def run_benchmark(
    turn_count: int = 50,
    session: str = "benchmark",
    models: str | list[str] | None = None,
    write: bool = True,
) -> dict:
    """Lance le benchmark complet (coût + qualité) et retourne le rapport."""
    model_list = normalize_models(models) or list(DEFAULT_MODELS)
    base = load_json(CONVERSATION_PATH)
    turns = generate_long_conversation(base, target_turns=turn_count)

    naive = simulate_naive_conversation(turns)
    tools, per_turn = _run_memory(turns, session)
    memory = {
        "mode": "memory",
        "turns": len(turns),
        "total_tokens": sum(per_turn),
        "context_per_turn": per_turn,
        "growth_factor": context_growth_factor(per_turn) if per_turn else 0.0,
        "compression_ratio": compression_ratio(tools, session),
        "stats": tools.memory_stats(model=model_list),
    }

    savings_pct = 0.0
    if naive["total_tokens"] > 0:
        savings_pct = round(100 * (1 - memory["total_tokens"] / naive["total_tokens"]), 1)

    # Axe qualité : questions pièges rejouées dans les deux modes.
    quality = evaluate_memory_quality(tools, session)
    quality_naive = evaluate_naive_quality(turns)

    cost = _cost_report(naive["total_tokens"], memory["total_tokens"], model_list)

    report = {
        "turns": len(turns),
        "models": model_list,
        "naive": naive,
        "memory": memory,
        "savings_pct": savings_pct,
        "quality": quality,
        "quality_naive": quality_naive,
        "cost": cost,
    }

    if write:
        RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
        RESULTS_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    return report


def main() -> None:
    # Usage : python -m benchmark.harness [turns] [slug1,slug2,...]
    turn_count = int(sys.argv[1]) if len(sys.argv) > 1 else 50
    models = sys.argv[2] if len(sys.argv) > 2 else None

    report = run_benchmark(turn_count=turn_count, models=models)
    naive_t = report["naive"]["total_tokens"]
    mem_t = report["memory"]["total_tokens"]
    q = report["quality"]
    cost = report["cost"]
    cur = cost.get("currency", "USD")
    print("=== MemBridge — Benchmark ===")
    print(f"Tours                 : {report['turns']}")
    print(f"Tokens naïf           : {naive_t:,}")
    print(f"Tokens MemBridge      : {mem_t:,}")
    print(f"Économie tokens       : {report['savings_pct']} %")
    print(f"Qualité (MemBridge)   : {q['passed']}/{q['total']} ({q['score_pct']} %)")
    qn = report["quality_naive"]
    print(f"Qualité (naïf)        : {qn['passed']}/{qn['total']}")
    print(f"Facteur de croissance : {report['memory']['growth_factor']:.2f} (≈1 = contexte stable)")
    print(f"\n--- Coût par modèle (models.dev, {cur}) ---")
    for c in cost["per_model"]:
        if c.get("pricing_found"):
            note = ""
            if c.get("fallback_used"):
                note = f"  [introuvable → repli {c['model']}]"
            elif c.get("match") == "regex" and c.get("requested") != c.get("model"):
                note = f"  [regex « {c['requested']} » → {c['model']}]"
            label = c.get("requested", c["model"])
            print(
                f"  {label:<24} {c['input_price_per_1m']:>7} {cur}/1M  "
                f"naïf {c['naive']:.6f} → MemBridge {c['memory']:.6f}  "
                f"(économie {c['saved']:.6f}){note}"
            )
        else:
            print(f"  {c.get('requested', c['model']):<24} non chiffré")
    t = cost["total"]
    print(
        f"  {'TOTAL (somme modèles)':<28} "
        f"naïf {t['naive']:.6f} → MemBridge {t['memory']:.6f}  (économie {t['saved']:.6f} {cur})"
    )
    print(f"\nRapport écrit         : {RESULTS_PATH}")


if __name__ == "__main__":
    main()
