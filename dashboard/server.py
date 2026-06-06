"""Serveur web live pour le dashboard MemBridge (chat + MCP en temps réel)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).parent
PROJECT_ROOT = ROOT.parent


def _load_env() -> None:
    env_path = PROJECT_ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key, val = key.strip(), val.strip().strip('"').strip("'")
        if key and val and key not in os.environ:
            os.environ[key] = val


_load_env()

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from benchmark.scoring import per_turn_context_tokens
from dashboard.llm import brain_status, fallback_reply, generate_reply, is_configured
from memory_mcp.stats import count_tokens, reset_stats
from memory_mcp.tools import MemoryTools
FRONTEND_DIST = ROOT / "frontend" / "dist"
EUR_PER_1K_TOKENS = 0.003
MAX_LOG = 40


@dataclass
class SessionState:
    tools: MemoryTools = field(default_factory=MemoryTools)
    history: list[dict] = field(default_factory=list)
    turn: int = 0
    naive_total: int = 0
    memory_total: int = 0


sessions: dict[str, SessionState] = {}
action_log: list[dict] = []


def _now() -> str:
    return datetime.now(UTC).strftime("%H:%M:%S")


def _log(tool: str, detail: str, tokens: int = 0) -> None:
    action_log.insert(
        0,
        {"time": _now(), "tool": tool, "detail": detail[:160], "tokens": tokens},
    )
    del action_log[MAX_LOG:]


def _session(session_id: str) -> SessionState:
    if session_id not in sessions:
        sessions[session_id] = SessionState()
    return sessions[session_id]


def _naive_context_tokens(history: list[dict]) -> int:
    context = "\n".join(f"[{m['role']}] {m['content']}" for m in history)
    return count_tokens(context)


def _build_memory_context(tools: MemoryTools, session_id: str, query: str) -> tuple[str, str | None]:
    hits = tools.memory_search(query, top_k=3, session=session_id)
    summary = tools.memory_summarize(session=session_id)
    parts = []
    if summary["summary"]:
        parts.append(f"Summary: {summary['summary']}")
    for h in hits["results"]:
        parts.append(f"- {h['content']}")
    best = hits["results"][0]["content"] if hits["results"] else None
    return "\n".join(parts), best


def _reply(tools: MemoryTools, session_id: str, query: str) -> str:
    context, _best_hit = _build_memory_context(tools, session_id, query)
    if is_configured():
        try:
            return generate_reply(query, context)
        except Exception as exc:
            return f"{fallback_reply(query, context)} [LLM error: {exc}]"
    return fallback_reply(query, context)


def _metrics(state: SessionState) -> dict:
    stats = state.tools.memory_stats()
    tokens_consumed = state.memory_total
    spent = round(tokens_consumed / 1000 * EUR_PER_1K_TOKENS, 4)
    naive_equiv = state.naive_total
    saved = max(0, naive_equiv - tokens_consumed)
    savings_pct = round(100 * saved / naive_equiv, 1) if naive_equiv else 0.0
    euros_saved = round(saved / 1000 * EUR_PER_1K_TOKENS, 4)

    return {
        "tokens_consumed": tokens_consumed,
        "amount_spent_eur": spent,
        "retrieves": stats["search_calls"],
        "stores": stats["store_calls"],
        "summaries": stats["summarize_calls"],
        "naive_equivalent": naive_equiv,
        "tokens_saved": saved,
        "savings_pct": savings_pct,
        "euros_saved": euros_saved,
        "turns": state.turn,
    }


async def api_chat(request: Request) -> JSONResponse:
    body = await request.json()
    message = (body.get("message") or "").strip()
    session_id = body.get("session") or "live-demo"
    if not message:
        return JSONResponse({"error": "message required"}, status_code=400)

    state = _session(session_id)
    state.turn += 1

    user_line = f"user: {message}"
    store = state.tools.memory_store(
        content=user_line,
        tags=["user", "fact"],
        session=session_id,
        turn=state.turn,
    )
    _log("memory_store", user_line, count_tokens(message))

    state.history.append({"role": "user", "content": message})
    state.naive_total += _naive_context_tokens(state.history)

    mem_ctx = per_turn_context_tokens(state.tools, session_id, message)
    state.memory_total += mem_ctx

    search = state.tools.memory_search(message, top_k=3, session=session_id)
    _log(
        "memory_search",
        f"{search['count']} hit(s) - {search['results'][0]['content'] if search['results'] else 'none'}",
        count_tokens(message),
    )

    summary = state.tools.memory_summarize(session=session_id)
    _log("memory_summarize", summary["summary"] or "(empty)", summary["compressed_chars"])

    answer = _reply(state.tools, session_id, message)
    state.tools.memory_store(
        content=f"assistant: {answer}",
        tags=["assistant"],
        session=session_id,
        turn=state.turn,
    )
    _log("memory_store", f"assistant: {answer[:80]}", count_tokens(answer))
    state.history.append({"role": "assistant", "content": answer})

    return JSONResponse(
        {
            "reply": answer,
            "turn": state.turn,
            "store_id": store["id"],
            "search_results": search["results"],
            "summary": summary["summary"],
            "brain": brain_status(),
            "metrics": _metrics(state),
            "actions": action_log[:12],
        }
    )


async def api_stats(request: Request) -> JSONResponse:
    session_id = request.query_params.get("session") or "live-demo"
    state = _session(session_id)
    return JSONResponse({"metrics": _metrics(state), "actions": action_log, "brain": brain_status()})


async def api_status(_: Request) -> JSONResponse:
    return JSONResponse(brain_status())


async def api_reset(request: Request) -> JSONResponse:
    body: dict = {}
    if "application/json" in (request.headers.get("content-type") or ""):
        try:
            body = await request.json()
        except Exception:
            body = {}
    session_id = body.get("session") or "live-demo"
    reset_stats()
    sessions.pop(session_id, None)
    action_log.clear()
    return JSONResponse({"ok": True})


async def index_page(_: Request) -> FileResponse:
    return FileResponse(ROOT / "index.html")


def _build_routes() -> list:
    routes: list = [
        Route("/api/chat", api_chat, methods=["POST"]),
        Route("/api/stats", api_stats, methods=["GET"]),
        Route("/api/status", api_status, methods=["GET"]),
        Route("/api/reset", api_reset, methods=["POST"]),
        Route("/", index_page),
        Mount("/static", StaticFiles(directory=ROOT), name="static"),
    ]
    if FRONTEND_DIST.exists():
        routes.insert(-1, Mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets"))
    return routes


app = Starlette(routes=_build_routes())


def main() -> None:
    import uvicorn

    port = int(os.environ.get("MEMBRIDGE_PORT", "8765"))
    print(f"MemBridge API: http://127.0.0.1:{port}")
    status = brain_status()
    if status["on"]:
        print(f"AI brain: ON ({status['provider']} / {status['model']})")
    else:
        print("AI brain: OFF — add GROQ_API_KEY or GEMINI_API_KEY to .env (see .env.example)")
    print("Press Ctrl+C to stop.")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")


if __name__ == "__main__":
    main()
