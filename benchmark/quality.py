"""Évaluation qualité — questions pièges via memory_search."""

from __future__ import annotations

import json
from pathlib import Path

from memory_mcp.tools import MemoryTools
from memory_mcp.validation import top1_contains

ROOT = Path(__file__).parent
TRAPS_PATH = ROOT / "trap_questions.json"


def load_traps() -> list[dict]:
    return json.loads(TRAPS_PATH.read_text(encoding="utf-8"))


def evaluate_quality(tools: MemoryTools, session: str = "benchmark") -> dict:
    """Teste les questions pièges après une conversation simulée."""
    traps = load_traps()
    results: list[dict] = []
    passed = 0

    for trap in traps:
        search = tools.memory_search(
            query=trap["query"],
            top_k=1,
            session=session,
            record_access=False,
            expand_links=False,
        )
        hits = search.get("results", [])
        answer = hits[0]["content"] if hits else ""
        ok = top1_contains(trap["expected"], hits) if hits else False
        if ok:
            passed += 1
        results.append(
            {
                "id": trap["id"],
                "question": trap["question"],
                "query": trap["query"],
                "expected": trap["expected"],
                "top1": answer[:120],
                "passed": ok,
            }
        )

    total = len(traps)
    score_pct = round(100 * passed / total, 1) if total else 0.0
    return {
        "passed": passed,
        "total": total,
        "score_pct": score_pct,
        "quality_ok": score_pct >= 80.0,
        "details": results,
    }
