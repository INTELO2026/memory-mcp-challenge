"""Agent de démo — boucle store → search → LLM → store + questions pièges."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from benchmark.harness import generate_long_conversation, load_json
from benchmark.traps import evaluate_trap_questions
from demo.llm import generate_reply, require_llm_configured
from memory_mcp.config import ensure_env_loaded, get_settings
from memory_mcp.stats import count_tokens, reset_stats
from memory_mcp.tools import MemoryTools

ROOT = Path(__file__).parent.parent
CONVERSATION = ROOT / "benchmark" / "conversation.json"
DEMO_RESULTS = ROOT / "demo" / "results" / "demo_report.json"


def _build_agent_context(
    tools: MemoryTools, session: str, user_message: str, *, use_llm: bool
) -> str:
    demo_tokens = get_settings().summary_max_tokens_demo
    summary = tools.memory_summarize(session=session, max_tokens=demo_tokens, use_llm=use_llm)
    search = tools.memory_search(query=user_message, top_k=3, session=session)
    hits = "\n".join(f"- {r['content']}" for r in search["results"])
    return (
        f"Résumé session :\n{summary['summary']}\n\n"
        f"Souvenirs pertinents :\n{hits}\n\n"
        f"Message actuel :\n{user_message}"
    )


def _tags_for_turn(turn: dict) -> list[str]:
    if turn["turn"] <= 10:
        return [turn["role"], "fact"]
    return [turn["role"], "exchange"]


def _content_for_turn(turn: dict) -> str:
    if turn["turn"] > 10:
        return f"{turn['role']}: #{turn['turn']}"
    return f"{turn['role']}: {turn['content']}"


def _offline_reply(user_turn: dict, base_turns: list[dict]) -> str:
    """Réponses scriptées sans LLM — utile pour la démo jury sans quota API."""
    next_turn = user_turn["turn"] + 1
    for base in base_turns:
        if base["turn"] == next_turn and base["role"] == "assistant":
            return base["content"]
    return f"Pris en charge — suivi du dossier au tour {user_turn['turn']}."


def _export_demo_report(payload: dict) -> Path:
    DEMO_RESULTS.parent.mkdir(parents=True, exist_ok=True)
    DEMO_RESULTS.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return DEMO_RESULTS


def run_demo(
    session: str = "demo",
    target_turns: int = 50,
    *,
    offline: bool = False,
    export: bool = False,
) -> dict:
    """Simule l'agent support client avec la boucle MemBridge complète."""
    ensure_env_loaded()
    if not offline:
        require_llm_configured()
    settings = get_settings()

    reset_stats()
    tools = MemoryTools()
    base = load_json(CONVERSATION)
    turns = generate_long_conversation(base, target_turns=target_turns)
    total_context_tokens = 0

    mode = "offline (sans LLM)" if offline else f"{settings.llm_provider}/{settings.active_model}"
    print(f"=== MemBridge — Agent démo (session: {session}, {len(turns)} tours) ===")
    print(f"LLM : {mode} | Mémoire : search + summarize + store\n")

    for turn in turns:
        role = turn["role"]
        content = turn["content"]

        if role != "user":
            tools.memory_store(
                content=_content_for_turn(turn),
                tags=_tags_for_turn(turn),
                session=session,
                turn=turn["turn"],
            )
            continue

        use_llm = not offline
        context = _build_agent_context(tools, session, content, use_llm=use_llm)
        total_context_tokens += count_tokens(context)
        reply = _offline_reply(turn, base) if offline else generate_reply(context, content)
        tools.memory_store(
            content=f"user: {content}",
            tags=_tags_for_turn(turn),
            session=session,
            turn=turn["turn"],
        )
        tools.memory_store(
            content=f"assistant: {reply}",
            tags=["assistant", "exchange"],
            session=session,
            turn=turn["turn"],
        )
        if turn["turn"] % 10 == 0 or turn["turn"] <= 4:
            print(f"  Tour {turn['turn']:2d} — user -> assistant ({len(reply)} car.)")

    summary = tools.memory_summarize(
        session=session,
        max_tokens=settings.summary_max_tokens_demo,
        use_llm=not offline,
    )
    stats = tools.memory_stats(session=session)
    quality = evaluate_trap_questions(tools, session)

    print(
        f"\n--- Résumé ({summary['source_turns']} tours -> {summary['compressed_chars']} car.) ---"
    )
    print(summary["summary"][:400])
    print(f"\n--- Questions pièges : {quality['passed']}/{quality['total']} ---")
    for item in quality["details"]:
        mark = "OK" if item["passed"] else "KO"
        print(f"  [{mark}] {item['query']}")
    print(f"\n--- Contexte agent cumulé : {total_context_tokens} tokens ---")
    print(json.dumps(stats, indent=2, ensure_ascii=False))

    payload = {
        "summary": summary,
        "stats": stats,
        "quality": quality,
        "agent_context_tokens": total_context_tokens,
        "offline": offline,
        "session": session,
        "turns": len(turns),
    }

    if export:
        path = _export_demo_report(payload)
        print(f"\nRapport démo exporté : {path}")

    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Agent démo MemBridge")
    parser.add_argument("--offline", action="store_true", help="Sans appel LLM")
    parser.add_argument("--export", action="store_true", help="Écrit demo/results/demo_report.json")
    parser.add_argument("--session", default="demo")
    parser.add_argument("--turns", type=int, default=50)
    args = parser.parse_args()
    run_demo(
        session=args.session,
        target_turns=args.turns,
        offline=args.offline,
        export=args.export,
    )


if __name__ == "__main__":
    main()
