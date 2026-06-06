"""Serveur HTTP FastAPI exposant les 4 outils Memory MCP.

Transport REST (agents HTTP) :
    POST /api/v1/store       — memory_store
    POST /api/v1/search      — memory_search
    POST /api/v1/summarize   — memory_summarize
    GET  /api/v1/stats       — memory_stats

Transport MCP natif via SSE (Cursor, Claude, agents MCP) :
    GET  /mcp/sse            — SSE endpoint (connexion MCP)
    POST /mcp/message        — messages MCP (appelé par le client)

Utilisation :
    uvicorn memory_mcp.http_server:app --host 0.0.0.0 --port 8010
    memory-mcp-http
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from starlette.requests import Request
from starlette.types import ASGIApp, Receive, Scope, Send

from memory_mcp.server import app as mcp_app
from memory_mcp.stats import reset_stats
from memory_mcp.tools import MemoryTools

# --- Schémas Pydantic (REST) ---

class StoreRequest(BaseModel):
    content: str
    tags: list[str] | None = None
    session: str = "default"
    turn: int = 0
    importance: float = 0.5
    date: str | None = None
    model: str | None = None


class SearchRequest(BaseModel):
    query: str
    top_k: int = 5
    session: str | None = None


class SummarizeRequest(BaseModel):
    session: str = "default"
    max_chars: int = 400


class StatsResponse(BaseModel):
    input_tokens: int
    output_tokens: int
    total_tokens: int
    store_calls: int
    search_calls: int
    summarize_calls: int
    entries_count: int
    tokens_stored: int
    tokens_saved: int
    naive_tokens: int = 0
    membridge_tokens: int = 0
    gain_pct: float = 0.0
    turns: int = 0
    active_model: str | None = None
    models: list[str] | None = None
    cost: dict | None = None


class StoreResponse(BaseModel):
    id: int
    stored: bool
    tags: list[str]
    importance: float
    date: str


class SearchResultItem(BaseModel):
    id: int
    content: str
    tags: list[str]
    turn: int
    score: float


class SearchResponse(BaseModel):
    results: list[SearchResultItem]
    count: int


class SummarizeResponse(BaseModel):
    summary: str
    source_turns: int
    compressed_chars: int


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str


# --- Outils MCP ---

tools_handler: MemoryTools = MemoryTools()

# --- Application FastAPI (endpoints REST) ---

fastapi_app = FastAPI(
    title="Memory MCP HTTP API",
    description="API HTTP pour interagir avec le serveur de mémoire MCP. "
                "Transport REST (endpoints /api/v1/*) et MCP natif via SSE (/mcp/sse).",
    version="0.1.0",
)

fastapi_app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    # Pas d'auth par cookie : on garde le wildcard d'origine fonctionnel pour le
    # tableau de bord live (un wildcard + credentials serait rejeté par le navigateur).
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@fastapi_app.get("/", include_in_schema=False)
async def root():
    return {"message": "Memory MCP HTTP API — voir /docs pour Swagger"}


@fastapi_app.get("/health", response_model=HealthResponse)
async def health():
    return HealthResponse(
        status="ok",
        service="memory-mcp-http",
        version="0.1.0",
    )


@fastapi_app.post("/api/v1/store", response_model=StoreResponse)
async def api_store(req: StoreRequest):
    try:
        result = tools_handler.memory_store(
            content=req.content,
            tags=req.tags,
            session=req.session,
            turn=req.turn,
            importance=req.importance,
            date=req.date,
            model=req.model,
        )
        return StoreResponse(**result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@fastapi_app.post("/api/v1/search", response_model=SearchResponse)
async def api_search(req: SearchRequest):
    try:
        result = tools_handler.memory_search(
            query=req.query,
            top_k=req.top_k,
            session=req.session,
        )
        return SearchResponse(**result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@fastapi_app.post("/api/v1/summarize", response_model=SummarizeResponse)
async def api_summarize(req: SummarizeRequest):
    try:
        result = tools_handler.memory_summarize(
            session=req.session,
            max_chars=req.max_chars,
        )
        return SummarizeResponse(**result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@fastapi_app.get("/api/v1/stats", response_model=StatsResponse)
async def api_stats(
    model: list[str] | None = Query(
        default=None,
        description="Slug(s) de modèle pour chiffrer le coût (répéter ?model=… "
        "ou valeurs séparées par des virgules).",
    )
):
    return StatsResponse(**tools_handler.memory_stats(model=model))


@fastapi_app.get("/api/v1/timeseries")
async def api_timeseries(
    bucket: str = Query(
        default="hour",
        description="Granularité d'agrégation : 'hour', 'day' ou 'month'.",
    )
):
    """Série temporelle de l'usage (naïf vs MemBridge) agrégée par tranche."""
    from memory_mcp.stats import get_stats

    if bucket not in ("hour", "day", "month"):
        bucket = "hour"
    return get_stats().timeseries(bucket)


@fastapi_app.get("/api/v1/models")
async def api_models(
    q: str | None = Query(
        default=None,
        description="Filtre (regex insensible à la casse) sur l'id, le nom ou le "
        "fournisseur. Vide = catalogue complet.",
    )
):
    """Catalogue des modèles tarifés (models.dev) pour la vue d'ensemble pricing."""
    from memory_mcp.pricing import list_models

    models = list_models(query=q)
    return {"models": models, "count": len(models)}


@fastapi_app.post("/api/v1/reset", include_in_schema=True)
async def api_reset():
    reset_stats()
    return {"reset": True}


# --- Middleware ASGI : intercepte /mcp/sse et /mcp/message ---

from mcp.server.sse import SseServerTransport

sse_transport = SseServerTransport("/mcp/message")


class _McpTransport:
    """Middleware ASGI qui intercepte les requêtes /mcp/* avant FastAPI."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            path = scope.get("path", "")
            method = scope.get("method", "GET")

            if path == "/mcp/sse" and method == "GET":
                async with sse_transport.connect_sse(scope, receive, send) as streams:
                    read_stream, write_stream = streams
                    await mcp_app.run(
                        read_stream,
                        write_stream,
                        mcp_app.create_initialization_options(),
                    )
                return

            if path == "/mcp/message" and method == "POST":
                await sse_transport.handle_post_message(scope, receive, send)
                return

        # Toutes les autres requêtes vont vers FastAPI
        await self.app(scope, receive, send)


# L'application exposée combine le middleware MCP + FastAPI
app: ASGIApp = _McpTransport(fastapi_app)


# --- CLI ---

def main() -> None:
    import uvicorn
    uvicorn.run(
        "memory_mcp.http_server:app",
        host="0.0.0.0",
        port=8010,
        reload=False,
    )


if __name__ == "__main__":
    main()
