"""Harnais de benchmark : compare mode naïf vs serveur mémoire MCP."""

from __future__ import annotations

import json
from pathlib import Path

from benchmark.naive import simulate_naive_conversation
from benchmark.scoring import compression_ratio, context_growth_factor, per_turn_context_tokens
from memory_mcp.stats import reset_stats
from memory_mcp.tools import MemoryTools
from memory_mcp.validation import normalize_text

ROOT = Path(__file__).parent
CONVERSATION_PATH = ROOT / "conversation.json"
REPORT_PATH = ROOT / "results" / "report.json"

# Prix indicatif (entrée, classe GPT-4o ~2,50 $/1M tokens ≈ 0,0023 €/1k).
# Ajustez selon le modèle réellement utilisé.
EUR_PER_1K_TOKENS = 0.0023

# Questions « pièges » : la réponse dépend d'une information donnée plus tôt.
# (requête paraphrasée, réponse attendue)
QUALITY_PROBES = [
    ("identité de la cliente premium", "marie dupont"),
    ("entreprise mentionnée par l'interlocutrice", "techcorp"),
    ("référence du contrat client", "ctr-2024-8847"),
    ("montant erroné affiché sur la facture de mars", "149,90"),
    ("montant correct attendu pour la facture", "99,90"),
    ("date de l'incident signalé sur l'application mobile", "12 février"),
    ("coordonnées électroniques de contact", "marie.dupont@email.fr"),
    ("niveau de fidélité de la cliente", "premium"),
]


def load_json(path: Path) -> list | dict:
    return json.loads(path.read_text(encoding="utf-8"))


def tokens_to_eur(tokens: int) -> float:
    return round(tokens / 1000 * EUR_PER_1K_TOKENS, 4)


def evaluate_memory_quality(tools: MemoryTools, session: str) -> dict:
    """Rejoue les questions pièges via le serveur mémoire (résumé + recherche)."""
    summary = normalize_text(tools.memory_summarize(session=session)["summary"])
    passed = 0
    for query, expected in QUALITY_PROBES:
        hits = tools.memory_search(query, top_k=3, session=session)
        retrieved = normalize_text(" ".join(r["content"] for r in hits["results"]))
        context = summary + " " + retrieved
        if normalize_text(expected) in context:
            passed += 1
    return {"passed": passed, "total": len(QUALITY_PROBES)}


def evaluate_naive_quality(turns: list[dict]) -> dict:
    """En mode naïf l'historique complet est renvoyé : tout reste accessible."""
    history = normalize_text(" ".join(t["content"] for t in turns))
    passed = sum(1 for _, expected in QUALITY_PROBES if normalize_text(expected) in history)
    return {"passed": passed, "total": len(QUALITY_PROBES)}


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
        "quality": evaluate_memory_quality(tools, session),
        "stats": stats,
    }


def run_benchmark(turn_count: int = 50) -> dict:
    """Lance le benchmark complet et retourne le rapport."""
    base = load_json(CONVERSATION_PATH)
    turns = generate_long_conversation(base, target_turns=turn_count)
    naive = simulate_naive_conversation(turns)
    memory = simulate_memory_conversation(turns)

    savings_pct = 0.0
    if naive["total_tokens"] > 0:
        savings_pct = round(100 * (1 - memory["total_tokens"] / naive["total_tokens"]), 1)

    naive["quality"] = evaluate_naive_quality(turns)
    saved_tokens = naive["total_tokens"] - memory["total_tokens"]
    q_mem = memory["quality"]
    q_score = round(100 * q_mem["passed"] / q_mem["total"], 1) if q_mem["total"] else 0.0

    return {
        "naive": naive,
        "memory": memory,
        "savings_pct": savings_pct,
        "saved_tokens": saved_tokens,
        "cost": {
            "naive_eur": tokens_to_eur(naive["total_tokens"]),
            "memory_eur": tokens_to_eur(memory["total_tokens"]),
            "saved_eur": tokens_to_eur(saved_tokens),
            "rate_eur_per_1k": EUR_PER_1K_TOKENS,
        },
        "quality": {
            "passed": q_mem["passed"],
            "total": q_mem["total"],
            "score_pct": q_score,
            "naive": naive["quality"],
            "memory": q_mem,
        },
    }


def _write_report(report: dict) -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")


def main() -> None:
    report = run_benchmark()
    _write_report(report)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"\nRapport écrit dans {REPORT_PATH}")


if __name__ == "__main__":
    main()
