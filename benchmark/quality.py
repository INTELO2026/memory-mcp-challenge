"""Mesure de qualité : questions pièges dont la réponse dépend d'infos passées.

Axe « qualité » du sujet (§4) : on compte, dans chaque mode, combien de réponses
restent accessibles. La mesure est **déterministe** (pas de LLM) — une réponse
est jugée « accessible » si l'information attendue est présente dans le contexte
que le mode fournirait au modèle :

* mode naïf : tout l'historique (l'info y est presque toujours, mais au prix fort) ;
* mode MemBridge : résumé compressé + souvenirs récupérés par recherche sémantique.

MemBridge « maintient la qualité » s'il retrouve les faits clés malgré la
compression — c'est exactement ce que le jury veut voir prouvé.
"""

from __future__ import annotations

from memory_mcp.tools import MemoryTools
from memory_mcp.validation import normalize_text

# (question paraphrasée, fragment de réponse attendu). Les réponses dépendent
# d'informations livrées plus tôt dans la conversation (cf. conversation.json).
TRAP_QUESTIONS: list[tuple[str, str]] = [
    ("Comment s'appelle la cliente ?", "Marie Dupont"),
    ("Chez quelle entreprise est-elle cliente ?", "TechCorp"),
    ("Quel est le numéro de contrat ?", "CTR-2024-8847"),
    ("Quel montant erroné apparaît sur la facture ?", "149,90"),
    ("Quel aurait dû être le bon montant facturé ?", "99,90"),
    ("Quelle est l'adresse e-mail de contact ?", "marie.dupont@email.fr"),
    ("À quelle date le bug a-t-il été signalé ?", "12 février"),
    ("Sur quel type d'application le bug est-il survenu ?", "mobile"),
    ("Quel est le statut de fidélité de la cliente ?", "premium"),
    ("De quel mois date la facture contestée ?", "mars"),
]


def _accessible(expected: str, context: str) -> bool:
    return normalize_text(expected) in normalize_text(context)


def evaluate_quality(turns: list[dict], top_k: int = 3) -> dict:
    """Évalue les questions pièges sur une conversation, mode naïf vs MemBridge."""
    tools = MemoryTools()
    session = "quality"
    for turn in turns:
        tools.memory_store(
            content=f"{turn['role']}: {turn['content']}",
            session=session,
            turn=turn["turn"],
        )

    naive_context = "\n".join(f"{t['role']}: {t['content']}" for t in turns)
    summary = tools.memory_summarize(session=session)["summary"]

    naive_passed = 0
    memory_passed = 0
    details: list[dict] = []
    for question, expected in TRAP_QUESTIONS:
        hits = tools.memory_search(question, top_k=top_k, session=session)["results"]
        memory_context = summary + "\n" + "\n".join(h["content"] for h in hits)

        naive_ok = _accessible(expected, naive_context)
        memory_ok = _accessible(expected, memory_context)
        naive_passed += naive_ok
        memory_passed += memory_ok
        details.append(
            {
                "question": question,
                "expected": expected,
                "naive": naive_ok,
                "memory": memory_ok,
            }
        )

    total = len(TRAP_QUESTIONS)
    return {
        "total": total,
        "passed": memory_passed,  # vedette = MemBridge
        "score_pct": round(100 * memory_passed / total, 1) if total else 0.0,
        "naive_passed": naive_passed,
        "memory_passed": memory_passed,
        "details": details,
    }
