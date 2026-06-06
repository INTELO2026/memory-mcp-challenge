"""Publication live des métriques MCP vers le dashboard."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from memory_mcp.stats import get_stats

if TYPE_CHECKING:
    from memory_mcp.tools import MemoryTools

ROOT = Path(__file__).resolve().parents[2]
LIVE_PATH = ROOT / "dashboard" / "live.json"
MAX_ACTIVITY = 30
MAX_SERIES = 80

_per_call_tokens: list[int] = []
_last_total = 0
_history: list[dict] = []
_naive_total = 0
_memory_context_total = 0
_per_turn_naive: list[int] = []
_per_turn_memory: list[int] = []


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_role_content(content: str) -> tuple[str, str]:
    if ":" in content:
        prefix, body = content.split(":", 1)
        if prefix.strip().lower() in {"user", "assistant"}:
            return prefix.strip().lower(), body.strip()
    return "user", content.strip()


def _naive_turn_tokens(history: list[dict]) -> int:
    from memory_mcp.stats import count_tokens

    context = "\n".join(f"[{m['role']}] {m['content']}" for m in history)
    return count_tokens(context)


def _memory_turn_tokens(
    tools: MemoryTools,
    session: str,
    query: str,
    *,
    noise_turn: bool = False,
    turn: int = 0,
) -> int:
    from memory_mcp.context_metrics import per_turn_context_tokens

    return per_turn_context_tokens(
        tools, session, query, noise_turn=noise_turn, turn=turn
    )


def record_turn(
    tools: MemoryTools,
    session: str,
    content: str,
    *,
    noise_turn: bool = False,
    turn: int = 0,
) -> None:
    """Enregistre un tour conversationnel et calcule l'économie live."""
    global _naive_total, _memory_context_total

    role, body = _parse_role_content(content)
    _history.append({"role": role, "content": body})

    naive_turn = _naive_turn_tokens(_history)
    memory_turn = _memory_turn_tokens(
        tools, session, body, noise_turn=noise_turn, turn=turn
    )

    _naive_total += naive_turn
    _memory_context_total += memory_turn
    _per_turn_naive.append(naive_turn)
    _per_turn_memory.append(memory_turn)

    if len(_per_turn_naive) > MAX_SERIES:
        _per_turn_naive.pop(0)
        _per_turn_memory.pop(0)


def _savings_payload() -> dict:
    saved = max(0, _naive_total - _memory_context_total)
    pct = round(100 * (1 - _memory_context_total / _naive_total), 1) if _naive_total else 0.0
    return {
        "savings_pct": pct,
        "naive_tokens": _naive_total,
        "memory_tokens": _memory_context_total,
        "tokens_saved": saved,
        "turns": len(_history),
        "per_turn_naive": list(_per_turn_naive),
        "per_turn_memory": list(_per_turn_memory),
    }


def record_call(
    tool: str,
    session: str = "default",
    detail: str = "",
    *,
    tools: MemoryTools | None = None,
    content: str = "",
    noise_turn: bool = False,
    turn: int = 0,
) -> None:
    """Enregistre un appel outil et publie l'état live."""
    global _last_total

    if tool == "memory_store" and tools is not None and content:
        record_turn(tools, session, content, noise_turn=noise_turn, turn=turn)

    stats = get_stats()
    current_total = stats.total()
    delta = max(0, current_total - _last_total)
    _last_total = current_total

    _per_call_tokens.append(delta)
    if len(_per_call_tokens) > MAX_SERIES:
        _per_call_tokens.pop(0)

    publish_live(
        tool=tool,
        session=session,
        detail=detail,
        delta_tokens=delta,
        memories_count=tools.store.count() if tools else 0,
    )


def publish_live(
    *,
    tool: str | None = None,
    session: str = "default",
    detail: str = "",
    delta_tokens: int = 0,
    memories_count: int = 0,
    status: str = "online",
) -> None:
    """Écrit dashboard/live.json pour le polling frontend."""
    stats = get_stats()
    existing = _read_existing()

    activity = existing.get("recent_activity", [])
    if tool:
        activity.insert(
            0,
            {
                "tool": tool,
                "session": session,
                "detail": detail,
                "tokens": delta_tokens,
                "at": _now(),
            },
        )
    activity = activity[:MAX_ACTIVITY]

    payload = {
        "status": status,
        "updated_at": _now(),
        "stats": stats.to_dict(),
        "memories_count": memories_count,
        "per_call_tokens": list(_per_call_tokens),
        "recent_activity": activity,
        "savings": _savings_payload(),
    }

    LIVE_PATH.parent.mkdir(parents=True, exist_ok=True)
    LIVE_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def reset_live() -> None:
    """Réinitialise la série live."""
    global _last_total, _per_call_tokens, _history, _naive_total, _memory_context_total
    global _per_turn_naive, _per_turn_memory

    _per_call_tokens = []
    _last_total = 0
    _history = []
    _naive_total = 0
    _memory_context_total = 0
    _per_turn_naive = []
    _per_turn_memory = []
    publish_live(status="reset", memories_count=0)


def _read_existing() -> dict:
    if not LIVE_PATH.exists():
        return {}
    try:
        return json.loads(LIVE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}
