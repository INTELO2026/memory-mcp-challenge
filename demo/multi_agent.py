"""Démo bonus — mémoire partagée : agent A écrit, agent B relit (§10)."""

from __future__ import annotations

import json
from pathlib import Path

from benchmark.harness import load_json
from benchmark.traps import evaluate_trap_questions
from memory_mcp.storage import MemoryStore
from memory_mcp.tools import MemoryTools

ROOT = Path(__file__).parent.parent
CONVERSATION = ROOT / "benchmark" / "conversation.json"
OUTPUT = ROOT / "demo" / "results" / "multi_agent_report.json"
DB_PATH = ROOT / "data" / "shared_memory.db"


def run_multi_agent(session: str = "techcorp-shared", export: bool = True) -> dict:
    """Agent support écrit les faits ; agent superviseur ne lit que via MCP."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    if DB_PATH.exists():
        DB_PATH.unlink()

    store = MemoryStore(DB_PATH)
    agent_support = MemoryTools(store=store)
    turns = load_json(CONVERSATION)

    print("=== MemBridge — Mémoire partagée multi-agents ===")
    print(f"Session : {session} | DB : {DB_PATH.name}\n")

    print("[Agent A — Support client] Enregistre les faits...")
    for turn in turns:
        tags = ["fact", turn["role"]] if turn["turn"] <= 10 else [turn["role"], "exchange"]
        content = (
            f"{turn['role']}: {turn['content']}"
            if turn["turn"] <= 10
            else f"{turn['role']}: #{turn['turn']}"
        )
        agent_support.memory_store(
            content=content,
            tags=tags,
            session=session,
            turn=turn["turn"],
        )
    agent_support.close()

    print("[Agent B — Superviseur] Relit sans historique complet...")
    agent_supervisor = MemoryTools(store=MemoryStore(DB_PATH))
    quality = evaluate_trap_questions(agent_supervisor, session)
    for item in quality["details"]:
        mark = "OK" if item["passed"] else "KO"
        print(f"  [{mark}] {item['query']}")
    summary = agent_supervisor.memory_summarize(session=session, max_tokens=120)
    stats = agent_supervisor.memory_stats(session=session)
    agent_supervisor.close()

    payload = {
        "scenario": "shared_memory",
        "session": session,
        "db_path": str(DB_PATH),
        "agent_a": "support-client",
        "agent_b": "supervisor-audit",
        "audit_passed": quality["passed"],
        "audit_total": quality["total"],
        "audit_score_pct": quality["score_pct"],
        "quality": quality,
        "summary": summary,
        "stats": stats,
        "audit": quality["details"],
    }

    print(f"\nSuperviseur : {quality['passed']}/{quality['total']} questions audit OK")
    if export:
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Rapport exporte : {OUTPUT}")

    return payload


if __name__ == "__main__":
    run_multi_agent()
