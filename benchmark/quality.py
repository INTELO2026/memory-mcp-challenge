"""Axe qualité : les questions pièges sont-elles correctement retrouvées ?

Mesure déterministe (sans LLM, donc reproductible) de la qualité : pour chaque question piège,
on vérifie que la réponse attendue est bien présente dans le contexte fourni au modèle.

- Mode **naïf** : le contexte est l'historique complet → contient toujours la réponse (10/10),
  mais à un coût en tokens prohibitif.
- Mode **MemBridge** : le contexte est le résumé + les souvenirs récupérés par ``memory_search``.
  La qualité est maintenue *si et seulement si* le retrieval ramène le bon fait.

C'est exactement le critère du défi : « économiser des tokens en rendant l'agent amnésique ne
compte pas ».
"""

from __future__ import annotations

from memory_mcp.stats import count_tokens
from memory_mcp.tools import MemoryTools
from memory_mcp.validation import answer_in_results, normalize_text


def evaluate_memory_quality(
    tools: MemoryTools, session: str, trap_questions: list[dict], top_k: int = 8
) -> dict:
    """Évalue le rappel des questions pièges en mode mémoire."""
    details = []
    passed = 0
    context_tokens = 0
    for q in trap_questions:
        summary = tools.memory_summarize(session=session, max_chars=400)["summary"]
        search = tools.memory_search(
            q["question"], top_k=top_k, session=session, use_hierarchy=True
        )
        retrieved = search["results"]
        context = summary + "\n" + "\n".join(r["content"] for r in retrieved)
        context_tokens += count_tokens(context)

        hit = answer_in_results(q["expected"], retrieved) or (
            normalize_text(q["expected"]) in normalize_text(summary)
        )
        passed += int(hit)
        details.append(
            {
                "id": q.get("id", ""),
                "question": q["question"],
                "expected": q["expected"],
                "hit": hit,
                "top_score": round(retrieved[0]["score"], 4) if retrieved else 0.0,
                "retrieved": retrieved[0]["content"] if retrieved else "",
            }
        )
    total = len(trap_questions)
    return {
        "passed": passed,
        "total": total,
        "score_pct": round(100 * passed / total, 1) if total else 0.0,
        "context_tokens": context_tokens,
        "details": details,
    }


def evaluate_naive_quality(history_text: str, trap_questions: list[dict]) -> dict:
    """En mode naïf, l'historique complet contient tout : référence de qualité maximale."""
    hay = normalize_text(history_text)
    details = []
    passed = 0
    for q in trap_questions:
        hit = normalize_text(q["expected"]) in hay
        passed += int(hit)
        details.append({"id": q.get("id", ""), "hit": hit})
    total = len(trap_questions)
    # Coût : à chaque question, l'agent naïf renvoie tout l'historique.
    context_tokens = count_tokens(history_text) * total
    return {
        "passed": passed,
        "total": total,
        "score_pct": round(100 * passed / total, 1) if total else 0.0,
        "context_tokens": context_tokens,
        "details": details,
    }
