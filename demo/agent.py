"""Agent de démo branché sur le serveur mémoire MCP (Phase 2 — temps réel).

Boucle : memory_store -> (memory_search + memory_summarize) -> prompt court -> LLM.
L'agent ne reçoit JAMAIS tout l'historique : seulement le résumé compressé et les
souvenirs pertinents. La démo « question piège » prouve qu'il répond juste quand même.
"""

from __future__ import annotations

import json
from pathlib import Path

from demo.llm_client import get_llm_client
from memory_mcp.stats import count_tokens
from memory_mcp.tools import MemoryTools, strip_role

ROOT = Path(__file__).parent.parent
CONVERSATION = ROOT / "benchmark" / "conversation.json"

SYSTEM_PROMPT = (
    "Tu es un assistant support client. Réponds de façon concise en t'appuyant "
    "UNIQUEMENT sur le contexte mémoire fourni (résumé + souvenirs pertinents)."
)

TRAP_QUESTIONS = [
    "Comment s'appelle la cliente et quel est son statut ?",
    "Quel est le numéro de contrat ?",
    "Quel montant erroné apparaît sur la facture de mars ?",
    "Quand le bug mobile a-t-il été signalé ?",
    "Quel est l'email de contact de la cliente ?",
]


def build_context(tools: MemoryTools, question: str, session: str, top_k: int = 3) -> str:
    """Contexte court envoyé au LLM : résumé compressé + souvenirs pertinents."""
    summary = tools.memory_summarize(session=session)["summary"]
    hits = tools.memory_search(question, top_k=top_k, session=session)["results"]
    memories = "\n".join(f"- {strip_role(h['content'])}" for h in hits)
    return f"Résumé de session:\n{summary}\n\nSouvenirs pertinents:\n{memories}"


def run_demo(session: str = "demo") -> None:
    tools = MemoryTools()
    llm = get_llm_client()
    turns = json.loads(CONVERSATION.read_text(encoding="utf-8"))

    print(f"=== Démo agent MemBridge (LLM: {llm.name}, session: {session}) ===\n")

    # 1) Ingestion : l'agent mémorise chaque tour via le serveur MCP.
    for turn in turns:
        tools.memory_store(
            content=f"{turn['role']}: {turn['content']}",
            tags=[turn["role"]],
            session=session,
            turn=turn["turn"],
        )
    print(f"{len(turns)} tours mémorisés.\n")

    full_history = "\n".join(f"{t['role']}: {t['content']}" for t in turns)
    naive_tokens = count_tokens(full_history)

    # 2) Questions pièges : réponse via contexte court (MemBridge).
    for question in TRAP_QUESTIONS:
        context = build_context(tools, question, session)
        mem_tokens = count_tokens(context)
        answer = llm.generate(SYSTEM_PROMPT, f"{context}\n\nQuestion: {question}")
        saved = 100 * (1 - mem_tokens / naive_tokens) if naive_tokens else 0
        print(f"Q: {question}")
        print(f"   contexte MemBridge: {mem_tokens} tokens (naïf: {naive_tokens}, -{saved:.0f}%)")
        print(f"   R: {answer}\n")


if __name__ == "__main__":
    run_demo()
