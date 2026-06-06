"""Démo bonus — persistance entre sessions : l'agent retrouve le contexte d'hier (§10)."""

from __future__ import annotations

import json
from pathlib import Path

from memory_mcp.storage import MemoryStore
from memory_mcp.tools import MemoryTools

ROOT = Path(__file__).parent.parent
OUTPUT = ROOT / "demo" / "results" / "persistence_report.json"
DB_PATH = ROOT / "data" / "persistent_memory.db"

DAY1_FACTS = [
    (1, "user: Bonjour, je suis Marie Dupont, cliente premium chez TechCorp.", ["fact", "user"]),
    (3, "user: Mon numéro de contrat est CTR-2024-8847.", ["fact", "user"]),
    (5, "user: Ma facture de mars affiche 149,90 EUR au lieu de 99,90 EUR.", ["fact", "user"]),
    (7, "user: Bug mobile signale le 12 fevrier sur l'application iOS.", ["fact", "user"]),
    (9, "user: Mon email est marie.dupont@email.fr.", ["fact", "user"]),
]

DAY2_QUERIES = [
    ("identite de l'interlocutrice premium", "Marie Dupont"),
    ("reference legale du dossier client", "CTR-2024-8847"),
    ("coordonnees electroniques de contact", "marie.dupont@email.fr"),
]


def _day1_session(session: str) -> None:
    if DB_PATH.exists():
        DB_PATH.unlink()
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    tools = MemoryTools(store=MemoryStore(DB_PATH))
    print("[Jour 1] Agent support enregistre les faits...")
    for turn, content, tags in DAY1_FACTS:
        tools.memory_store(content=content, tags=tags, session=session, turn=turn)
        for _ in range(8):
            tools.memory_store(
                content=f"assistant: echange filler tour {turn}-{_}",
                tags=["exchange"],
                session=session,
                turn=turn * 10 + _,
            )
    stats = tools.memory_stats(session=session)
    tools.close()
    print(f"  {stats['entry_count']} entrees actives, {stats['archived_entries']} archivees")


def _day2_session(session: str) -> dict:
    print("\n[Jour 2] Nouveau processus — rechargement SQLite...")
    tools = MemoryTools(store=MemoryStore(DB_PATH))
    checks: list[dict] = []
    passed = 0

    for query, expected in DAY2_QUERIES:
        result = tools.memory_search(query, top_k=1, session=session)
        hit = result["results"][0]["content"] if result["results"] else ""
        ok = expected.lower() in hit.lower()
        if ok:
            passed += 1
        checks.append({"query": query, "expected": expected, "passed": ok, "top_content": hit})
        mark = "OK" if ok else "KO"
        print(f"  [{mark}] {query}")

    summary = tools.memory_summarize(session=session, max_tokens=100)
    stats = tools.memory_stats(session=session)
    tools.close()

    return {
        "checks": checks,
        "passed": passed,
        "total": len(DAY2_QUERIES),
        "summary": summary,
        "stats": stats,
    }


def run_persistence(session: str = "marie-dupont", export: bool = True) -> dict:
    print("=== MemBridge — Persistance inter-sessions ===")
    print(f"Session : {session} | DB : {DB_PATH.name}\n")

    _day1_session(session)
    day2 = _day2_session(session)

    payload = {
        "scenario": "persistence",
        "session": session,
        "db_path": str(DB_PATH),
        "day1_facts": len(DAY1_FACTS),
        "day2_recall": day2,
        "recall_score_pct": round(100 * day2["passed"] / day2["total"], 1),
    }

    print(f"\nRappel Jour 2 : {day2['passed']}/{day2['total']}")
    if export:
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Rapport exporte : {OUTPUT}")

    return payload


if __name__ == "__main__":
    run_persistence()
