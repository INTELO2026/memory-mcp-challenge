"""Métriques de scoring utilisées par le benchmark et la CI."""

from __future__ import annotations

from memory_mcp.tools import MemoryTools
from memory_mcp.validation import top1_contains

TRAP_QUESTIONS = [
    ("identité de l'interlocutrice premium", "Marie Dupont"),
    ("référence légale du dossier client", "CTR-2024-8847"),
    ("coordonnées électroniques de contact", "marie.dupont@email.fr"),
    ("écart tarifaire facturation printemps", "149,90"),
    ("incident application mobile date", "12 février"),
    ("statut client et entreprise", "TechCorp"),
    ("montant attendu facture mars", "99,90"),
    ("plateforme mobile concernée", "mobile"),
    ("nom de famille cliente", "Dupont"),
    ("canal de contact utilisé", "email"),
]

# Tarif indicatif gpt-4o-mini (USD / 1M tokens) — converti en EUR approximatif.
INPUT_COST_PER_M = 0.15 * 0.92
OUTPUT_COST_PER_M = 0.60 * 0.92


def compression_ratio(tools: MemoryTools, session: str) -> float:
    """Ratio taille résumé / taille source (plus bas = mieux)."""
    entries = tools.store.list_session(session)
    if not entries:
        return 1.0
    source_len = sum(len(e.content) for e in entries)
    summary = tools.memory_summarize(session=session)
    if source_len == 0:
        return 1.0
    return summary["compressed_chars"] / source_len


def context_growth_factor(per_turn: list[int]) -> float:
    """Ratio coût moyen des 10 derniers tours vs 10 premiers (doit stagner)."""
    if len(per_turn) < 20:
        return 999.0
    early = sum(per_turn[:10]) / 10
    late = sum(per_turn[-10:]) / 10
    if early == 0:
        return 999.0
    return late / early


def evaluate_trap_questions(tools: MemoryTools, session: str) -> dict:
    """Évalue les questions pièges via memory_search."""
    passed = 0
    details: list[dict] = []

    for query, expected in TRAP_QUESTIONS:
        result = tools.memory_search(query, top_k=1, session=session)
        ok = top1_contains(expected, result["results"])
        if ok:
            passed += 1
        details.append(
            {
                "query": query,
                "expected": expected,
                "passed": ok,
                "top_result": result["results"][0]["content"] if result["results"] else None,
            }
        )

    total = len(TRAP_QUESTIONS)
    score_pct = round(100 * passed / total, 1) if total else 0.0
    return {
        "passed": passed,
        "total": total,
        "score_pct": score_pct,
        "details": details,
    }


def estimate_cost_eur(total_tokens: int, input_ratio: float = 0.85) -> float:
    """Estime le coût en euros à partir du total tokens."""
    input_tokens = int(total_tokens * input_ratio)
    output_tokens = total_tokens - input_tokens
    cost = (input_tokens / 1_000_000) * INPUT_COST_PER_M + (
        output_tokens / 1_000_000
    ) * OUTPUT_COST_PER_M
    return round(cost, 4)
