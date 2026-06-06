"""Pont CLI entre le backend NestJS et le moteur mémoire Python.

Sortie : un unique objet JSON sur stdout (les logs vont sur stderr).

Commandes :
    python -m benchmark.bridge seed            # sème la base persistante
    python -m benchmark.bridge search "<q>"    # recherche sémantique
    python -m benchmark.bridge stats           # métriques mémoire
    python -m benchmark.bridge report          # (re)génère report.json
"""

from __future__ import annotations

import json
import sys

from benchmark.harness import RESULTS_DIR, build_report, load_scenario, write_report
from memory_mcp import embeddings
from memory_mcp.storage import MemoryStore
from memory_mcp.tools import MemoryTools

DB_PATH = RESULTS_DIR / "memory.db"


def _log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def _tools() -> tuple[MemoryTools, str]:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    scenario = load_scenario()
    session = scenario.get("session", "support-membridge")
    tools = MemoryTools(MemoryStore(DB_PATH))
    return tools, session


def _ensure_seeded(tools: MemoryTools, session: str) -> int:
    """Sème la base depuis le scénario si elle est vide. Renvoie le nb d'entrées."""
    if tools.store.count() > 0:
        return tools.store.count()
    scenario = load_scenario()
    for turn in scenario["turns"]:
        tools.memory_store(
            content=f"{turn['role']}: {turn['content']}",
            tags=[turn["role"]],
            session=session,
            turn=turn["turn"],
        )
    _log(f"[bridge] base semée : {tools.store.count()} entrées")
    return tools.store.count()


def cmd_seed() -> dict:
    tools, session = _tools()
    count = _ensure_seeded(tools, session)
    return {"ok": True, "entries": count, "backend": embeddings.backend_name()}


def cmd_search(query: str, top_k: int = 5) -> dict:
    tools, session = _tools()
    _ensure_seeded(tools, session)
    res = tools.memory_search(query, top_k=top_k, session=session)
    return {
        "ok": True,
        "query": query,
        "backend": embeddings.backend_name(),
        "results": res["results"],
        "count": res["count"],
    }


def cmd_stats() -> dict:
    tools, session = _tools()
    _ensure_seeded(tools, session)
    return {"ok": True, "stats": tools.memory_stats()}


def cmd_report() -> dict:
    report = build_report()
    path = write_report(report)
    return {"ok": True, "path": str(path), "savings_pct": report["savings_pct"]}


def main(argv: list[str]) -> int:
    if not argv:
        print(json.dumps({"ok": False, "error": "commande manquante"}))
        return 2
    cmd = argv[0]
    try:
        if cmd == "seed":
            out = cmd_seed()
        elif cmd == "search":
            if len(argv) < 2:
                raise ValueError("usage: search <query> [top_k]")
            top_k = int(argv[2]) if len(argv) > 2 else 5
            out = cmd_search(argv[1], top_k=top_k)
        elif cmd == "stats":
            out = cmd_stats()
        elif cmd == "report":
            out = cmd_report()
        else:
            raise ValueError(f"commande inconnue : {cmd}")
    except Exception as exc:  # renvoie l'erreur en JSON pour le backend
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(out, ensure_ascii=False))
    return 0


def _entrypoint() -> None:
    raise SystemExit(main(sys.argv[1:]))


if __name__ == "__main__":
    _entrypoint()
