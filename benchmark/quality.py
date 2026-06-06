"""Axe qualité du benchmark : les « questions pièges ».

Le défi MemBridge n'est pas jugé sur l'économie de tokens seule, mais sur
l'économie *à qualité maintenue*. On mesure donc une dizaine de questions dont
la réponse dépend d'informations données plus tôt dans la conversation, et on
compte combien chaque mode réussit :

- Mode naïf : tout l'historique est dans le contexte → l'information est
  toujours « atteignable » (référence haute, mais coût de tokens explosif).
- Mode MemBridge : seuls le résumé et les souvenirs pertinents (via
  `memory_search`) sont fournis → on vérifie que la recherche sémantique
  ramène bien le fait attendu.

Les questions sont des *paraphrases* (pas de copie des mots-clés exacts) afin de
tester une vraie compréhension sémantique, pas un simple match lexical.
"""

from __future__ import annotations

from memory_mcp.tools import MemoryTools
from memory_mcp.validation import answer_in_results, normalize_text

# (question paraphrasée, fragment de réponse attendu)
# Chaque réponse provient d'un tour antérieur de benchmark/conversation.json.
TRAP_QUESTIONS: list[tuple[str, str]] = [
    ("Comment s'appelle l'interlocutrice du dossier ?", "Marie Dupont"),
    ("Quelle est la référence légale du contrat client ?", "CTR-2024-8847"),
    ("Quel montant erroné apparaît sur la note de mars ?", "149,90"),
    ("Quel aurait dû être le tarif correct facturé ?", "99,90"),
    ("Quelle est l'adresse de courriel de contact ?", "marie.dupont@email.fr"),
    ("À quelle date l'incident applicatif a-t-il été remonté ?", "12 février"),
    ("Quel est le niveau d'abonnement de la cliente ?", "premium"),
    ("Pour quelle société travaille la cliente ?", "TechCorp"),
    ("Sur quel support le dysfonctionnement a-t-il été constaté ?", "mobile"),
    ("Quelle est la différence de prix constatée sur la facture ?", "50"),
]


def evaluate_memory_quality(tools: MemoryTools, session: str, top_k: int = 3) -> dict:
    """Évalue le mode MemBridge : la recherche ramène-t-elle le bon fait ?"""
    details = []
    passed = 0
    for question, expected in TRAP_QUESTIONS:
        res = tools.memory_search(query=question, top_k=top_k, session=session)
        ok = answer_in_results(expected, res["results"])
        passed += int(ok)
        details.append(
            {
                "question": question,
                "expected": expected,
                "passed": ok,
                "top_id": res["results"][0]["id"] if res["results"] else None,
            }
        )
    total = len(TRAP_QUESTIONS)
    return {
        "mode": "memory",
        "passed": passed,
        "total": total,
        "score_pct": round(100 * passed / total, 1) if total else 0.0,
        "details": details,
    }


def evaluate_naive_quality(turns: list[dict]) -> dict:
    """Évalue le mode naïf : tout l'historique est présent dans le contexte."""
    haystack = normalize_text(" ".join(f"{t['role']}: {t['content']}" for t in turns))
    passed = sum(1 for _, expected in TRAP_QUESTIONS if normalize_text(expected) in haystack)
    total = len(TRAP_QUESTIONS)
    return {
        "mode": "naive",
        "passed": passed,
        "total": total,
        "score_pct": round(100 * passed / total, 1) if total else 0.0,
    }
