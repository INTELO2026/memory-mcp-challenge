"""Questions pièges et scoring qualité pour le benchmark."""

from __future__ import annotations

from memory_mcp.tools import MemoryTools
from memory_mcp.validation import normalize_text, top1_contains

TRAP_QUESTIONS: list[tuple[str, str]] = [
    ("identité de l'interlocutrice premium", "Marie Dupont"),
    ("référence légale du dossier client", "CTR-2024-8847"),
    ("coordonnées électroniques de contact", "marie.dupont@email.fr"),
    ("écart tarifaire facturation printemps", "149,90"),
    ("incident application mobile date", "12 février"),
    ("montant attendu sur la facture de mars", "99,90"),
    ("nom de l'entreprise cliente", "TechCorp"),
    ("statut commercial de la cliente", "premium"),
    ("email confirmé par l'assistant", "marie.dupont@email.fr"),
]


def evaluate_trap_questions(tools: MemoryTools, session: str) -> dict:
    """Évalue la qualité via memory_search sur les questions pièges."""
    passed = 0
    details: list[dict] = []

    for query, expected in TRAP_QUESTIONS:
        result = tools.memory_search(query, top_k=1, session=session)
        ok = result["count"] >= 1 and top1_contains(expected, result["results"])
        if ok:
            passed += 1
        details.append(
            {
                "query": query,
                "expected": expected,
                "passed": ok,
                "top_content": result["results"][0]["content"] if result["results"] else "",
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


def evaluate_naive_trap_questions(turns: list[dict]) -> dict:
    """Qualité mode naïf : l'agent voit tout l'historique (haystack complet)."""
    haystack = normalize_text(" ".join(turn["content"] for turn in turns))
    passed = 0
    details: list[dict] = []

    for query, expected in TRAP_QUESTIONS:
        ok = normalize_text(expected) in haystack
        if ok:
            passed += 1
        details.append(
            {
                "query": query,
                "expected": expected,
                "passed": ok,
                "mode": "naive_full_history",
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
