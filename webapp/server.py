"""API de la plateforme MemBridge.

Expose le moteur de mémoire à un frontend premium (Next.js) :

- GET  /api/health        : état (embedder, agent, scénario)
- GET  /api/scenario      : conversation + questions pièges
- GET  /api/report        : dernier rapport (génère si absent)
- POST /api/report/run    : régénère le rapport
- WS   /ws/benchmark      : rejoue la conversation en direct, deux compteurs de tokens
- POST /api/ask           : pose une question → réponse de l'agent + souvenirs + tokens
- GET  /api/memory        : inspecteur mémoire (souvenirs + importance + accès)
- GET  /api/memory/rank   : hiérarchie de pertinence
- POST /api/memory/forget : oubli intelligent (doublons)
- POST /api/multiagent    : démo mémoire partagée (un agent écrit, un autre relit)

Lancer :  uvicorn webapp.server:app --reload --port 8000
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from benchmark.report import build_report, load_scenario, save_report
from benchmark.report import REPORT_PATH
from memory_mcp.llm import Agent
from memory_mcp.stats import count_tokens
from memory_mcp.tools import MemoryTools

app = FastAPI(title="MemBridge API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

SCENARIO = load_scenario()
SESSION = SCENARIO.get("session", "demo-support")
_TRAPS = SCENARIO.get("trap_questions", [])
_FULL_HISTORY = "\n".join(f"[{t['role']}] {t['content']}" for t in SCENARIO["turns"])
_NAIVE_TOKENS = count_tokens(_FULL_HISTORY)


# --- État partagé : un store ensemencé pour /ask et l'inspecteur -------------
class _State:
    tools: MemoryTools | None = None
    agent: Agent | None = None


def get_tools() -> MemoryTools:
    if _State.tools is None:
        tools = MemoryTools()
        for turn in SCENARIO["turns"]:
            tools.memory_store(
                content=f"{turn['role']}: {turn['content']}",
                tags=[turn["role"]],
                session=SESSION,
                turn=turn["turn"],
            )
        _State.tools = tools
    return _State.tools


def get_agent() -> Agent:
    if _State.agent is None:
        _State.agent = Agent()
    return _State.agent


# --- Modèles de requête ------------------------------------------------------
class AskRequest(BaseModel):
    question: str
    top_k: int = 8


class ForgetRequest(BaseModel):
    similarity_threshold: float = 0.93


class MultiAgentRequest(BaseModel):
    fact: str = "Le client a un rendez-vous d'installation le 20 mai à 14h."
    query: str = "Quand est prévue l'installation ?"


# --- Endpoints ---------------------------------------------------------------
@app.get("/api/health")
def health() -> dict:
    tools = get_tools()
    agent = get_agent()
    return {
        "status": "ok",
        "embedder": tools.store.embedder.name,
        "agent_backend": agent.backend,
        "scenario_turns": len(SCENARIO["turns"]),
        "trap_questions": len(_TRAPS),
    }


@app.get("/api/scenario")
def scenario() -> dict:
    return SCENARIO


@app.get("/api/report")
def get_report() -> dict:
    if REPORT_PATH.exists():
        return json.loads(Path(REPORT_PATH).read_text(encoding="utf-8"))
    report = build_report()
    save_report(report)
    return report


@app.post("/api/report/run")
def run_report() -> dict:
    report = build_report()
    save_report(report)
    return report


@app.post("/api/ask")
def ask(req: AskRequest) -> dict:
    tools = get_tools()
    agent = get_agent()
    summary = tools.memory_summarize(session=SESSION, max_chars=400)["summary"]
    hits = tools.memory_search(req.question, top_k=req.top_k, session=SESSION, use_hierarchy=True)
    context = summary + "\n" + "\n".join(r["content"] for r in hits["results"])
    memory_tokens = count_tokens(context)
    answer = agent.answer(req.question, context)
    return {
        "question": req.question,
        "answer": answer,
        "agent_backend": agent.backend,
        "memories": hits["results"],
        "tokens": {
            "memory": memory_tokens,
            "naive": _NAIVE_TOKENS,
            "saved_pct": round(100 * (1 - memory_tokens / _NAIVE_TOKENS), 1)
            if _NAIVE_TOKENS
            else 0.0,
        },
    }


@app.get("/api/memory")
def memory() -> dict:
    tools = get_tools()
    entries = tools.store.list_session(SESSION)
    return {
        "count": len(entries),
        "entries": [
            {
                "id": e.id,
                "turn": e.turn,
                "content": e.content,
                "importance": round(e.importance, 4),
                "access_count": e.access_count,
                "tags": e.tags,
            }
            for e in entries
        ],
    }


@app.get("/api/memory/rank")
def memory_rank(top_k: int = 12) -> dict:
    return get_tools().memory_rank(session=SESSION, top_k=top_k)


@app.post("/api/memory/forget")
def memory_forget(req: ForgetRequest) -> dict:
    return get_tools().memory_forget(session=SESSION, similarity_threshold=req.similarity_threshold)


@app.post("/api/multiagent")
def multiagent(req: MultiAgentRequest) -> dict:
    """Mémoire partagée : l'agent A écrit dans une session commune, l'agent B relit."""
    shared = MemoryTools()
    shared_session = "shared-team"
    shared.memory_store(content=f"agentA: {req.fact}", session=shared_session, turn=1)
    hits = shared.memory_search(req.query, top_k=3, session=shared_session)
    return {
        "writer": "agentA",
        "reader": "agentB",
        "fact_written": req.fact,
        "query": req.query,
        "recalled": hits["results"],
    }


@app.websocket("/ws/benchmark")
async def ws_benchmark(ws: WebSocket) -> None:
    """Rejoue la conversation tour par tour : deux compteurs montent en direct."""
    await ws.accept()
    try:
        params = await ws.receive_json()
        delay = float(params.get("delay_ms", 180)) / 1000.0
    except Exception:
        delay = 0.18

    tools = MemoryTools()
    history: list[str] = []
    naive_running = 0
    memory_running = 0

    turns = SCENARIO["turns"]
    await ws.send_json({"type": "start", "total": len(turns), "embedder": tools.store.embedder.name})

    for turn in turns:
        line = f"[{turn['role']}] {turn['content']}"
        history.append(line)
        naive_ctx = count_tokens("\n".join(history))
        naive_running += naive_ctx

        tools.memory_store(
            content=f"{turn['role']}: {turn['content']}",
            tags=[turn["role"]],
            session=SESSION,
            turn=turn["turn"],
        )
        summary = tools.memory_summarize(session=SESSION)["summary"]
        search = tools.memory_search(turn["content"], top_k=3, session=SESSION)
        mem_ctx = count_tokens(summary + "\n" + "\n".join(r["content"] for r in search["results"]))
        memory_running += mem_ctx

        await ws.send_json(
            {
                "type": "turn",
                "turn": turn["turn"],
                "role": turn["role"],
                "content": turn["content"],
                "naive_turn": naive_ctx,
                "memory_turn": mem_ctx,
                "naive_cumulative": naive_running,
                "memory_cumulative": memory_running,
            }
        )
        await asyncio.sleep(delay)

    saved = naive_running - memory_running
    await ws.send_json(
        {
            "type": "done",
            "naive_total": naive_running,
            "memory_total": memory_running,
            "saved_tokens": saved,
            "savings_pct": round(100 * saved / naive_running, 1) if naive_running else 0.0,
        }
    )
    try:
        await ws.close()
    except Exception:
        pass


def main() -> None:
    import uvicorn

    uvicorn.run("webapp.server:app", host="127.0.0.1", port=8000, reload=False)


if __name__ == "__main__":
    main()
