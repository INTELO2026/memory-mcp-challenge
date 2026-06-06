"""Agent de démo — mémoire MCP locale + Kimi (optionnel)."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

from memory_mcp.kimi import get_kimi_config, kimi_available, kimi_chat
from memory_mcp.stats import reset_stats
from memory_mcp.tools import MemoryTools
from memory_mcp.validation import top1_contains

ROOT = Path(__file__).parent.parent
CONVERSATION = ROOT / "benchmark" / "conversation.json"

TRAP_QUESTIONS = [
    ("Quel est le nom complet de la cliente premium ?", "Marie Dupont"),
    ("Quel est le numéro de contrat ?", "CTR-2024-8847"),
    ("Quel montant incorrect apparaît sur la facture de mars ?", "149,90"),
    ("Quand le bug mobile a-t-il été signalé ?", "12 février"),
    ("Quelle est l'adresse email de contact ?", "marie.dupont@email.fr"),
]

USE_KIMI = os.environ.get("USE_KIMI", "1").strip().lower() not in {"0", "false", "no"}


def _local_reply(query: str, tools: MemoryTools, session: str) -> str:
    hits = tools.memory_search(query, top_k=2, session=session)
    if not hits["results"]:
        return "Je n'ai pas retrouvé cette information dans la mémoire."
    best = hits["results"][0]["content"]
    best = best.split(":", 1)[-1].strip() if ":" in best else best
    return f"D'après la mémoire : {best}"


def _kimi_reply(query: str, context: str) -> str | None:
    return kimi_chat(
        messages=[
            {
                "role": "system",
                "content": (
                    "Tu es un assistant support client TechCorp. "
                    "Réponds brièvement en français en utilisant uniquement le contexte fourni."
                ),
            },
            {"role": "user", "content": f"Contexte:\n{context}\n\nQuestion: {query}"},
        ],
        max_tokens=150,
    )


def _build_context(tools: MemoryTools, session: str, query: str) -> str:
    summary = tools.memory_summarize(session=session)
    search = tools.memory_search(query=query, top_k=3, session=session)
    parts = [summary["summary"]] if summary["summary"] else []
    parts.extend(r["content"] for r in search["results"])
    return "\n".join(parts)


def run_demo(session: str = "demo") -> dict:
    reset_stats()
    tools = MemoryTools()
    turns = json.loads(CONVERSATION.read_text(encoding="utf-8"))
    kimi_config = get_kimi_config()
    use_kimi = USE_KIMI and kimi_available()

    print(f"=== Démo agent MemBridge (session: {session}) ===")
    if use_kimi:
        print(f"Kimi via OpenRouter : {kimi_config['model']}\n")
    else:
        print("Mode local — ajoutez OPENROUTER_API_KEY dans .env pour activer Kimi\n")

    for turn in turns:
        role = turn["role"]
        content = turn["content"]
        tags = ["fact", role] if turn["turn"] <= 10 else [role, "noise"]
        tools.memory_store(
            content=f"{role}: {content}",
            tags=tags,
            session=session,
            turn=turn["turn"],
        )
        print(f"Tour {turn['turn']:>2} [{role}] stocké")

    print("\n--- Questions pièges ---")
    trap_results = []
    for index, (question, expected) in enumerate(TRAP_QUESTIONS):
        if use_kimi and index > 0:
            time.sleep(1.5)
        context = _build_context(tools, session, question)
        if use_kimi:
            llm_answer = _kimi_reply(question, context)
            if llm_answer:
                answer = llm_answer
                source = "kimi"
            else:
                answer = _local_reply(question, tools, session)
                source = "local"
        else:
            answer = _local_reply(question, tools, session)
            source = "local"

        search = tools.memory_search(question, top_k=1, session=session)
        passed = top1_contains(expected, search["results"])
        trap_results.append(
            {
                "question": question,
                "expected": expected,
                "answer": answer,
                "passed": passed,
                "source": source,
            }
        )
        status = "OK" if passed else "FAIL"
        print(f"[{status}] [{source}] {question}")
        print(f"      -> {answer}\n")

    summary = tools.memory_summarize(session=session)
    stats = tools.memory_stats()
    passed_count = sum(1 for r in trap_results if r["passed"])

    report = {
        "session": session,
        "mode": "openrouter" if use_kimi else "local",
        "provider": "openrouter",
        "kimi_model": kimi_config["model"] if use_kimi else None,
        "turns_played": len(turns),
        "summary_preview": summary["summary"][:300],
        "trap_questions": trap_results,
        "quality": {
            "passed": passed_count,
            "total": len(trap_results),
            "score_pct": round(100 * passed_count / len(trap_results), 1),
        },
        "stats": stats,
    }

    print("--- Résumé compressé ---")
    print(summary["summary"])
    print("\n--- Stats MCP ---")
    print(json.dumps(stats, indent=2, ensure_ascii=False))
    print(f"\nQualité pièges : {passed_count}/{len(trap_results)}")
    return report


if __name__ == "__main__":
    run_demo()
