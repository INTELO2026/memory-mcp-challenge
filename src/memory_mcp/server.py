"""Serveur MCP : memory_store, memory_search, memory_summarize, memory_stats, memory_graph."""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime, timezone

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from memory_mcp.tools import MemoryTools


def _log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[membridge] {ts} {msg}", file=sys.stderr, flush=True)


app = Server("membridge")
_tools: MemoryTools | None = None


def _tools_handler() -> MemoryTools:
    global _tools
    if _tools is None:
        _tools = MemoryTools()
        _log("MemoryTools initialized")
    return _tools


@app.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="memory_store",
            description=(
                "Stocke une info en mémoire externe (embeddings sémantiques). "
                "Params: content (requis), tags, session, turn."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "content": {"type": "string", "description": "Contenu à mémoriser"},
                    "tags": {"type": "array", "items": {"type": "string"}, "description": "Tags"},
                    "session": {"type": "string", "description": "ID de session"},
                    "turn": {"type": "integer", "description": "Numéro de tour"},
                    "agent_id": {
                        "type": "string",
                        "description": "ID agent (mémoire partagée multi-agents)",
                        "default": "default",
                    },
                },
                "required": ["content"],
            },
        ),
        Tool(
            name="memory_search",
            description="Recherche sémantique dans la mémoire.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Requête de recherche"},
                    "top_k": {
                        "type": "integer",
                        "description": "Nombre de résultats",
                        "default": 5,
                    },
                    "session": {"type": "string", "description": "Filtrer par session"},
                    "agent_id": {
                        "type": "string",
                        "description": "Filtrer par agent (omit = mémoire partagée)",
                    },
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="memory_summarize",
            description="Résume compressé de l'historique d'une session.",
            inputSchema={
                "type": "object",
                "properties": {
                    "session": {"type": "string", "description": "ID de session"},
                    "max_chars": {
                        "type": "integer",
                        "description": "Taille max du résumé",
                        "default": 500,
                    },
                },
            },
        ),
        Tool(
            name="memory_stats",
            description="Retourne les statistiques de consommation de tokens.",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="memory_graph",
            description=(
                "Graphe sémantique A-MEM : nœuds (souvenirs) et liens (similarité > 0.7)."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "session": {"type": "string", "description": "Filtrer par session"},
                },
            },
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    _log(f"tool={name} args_keys={list(arguments.keys())}")
    try:
        if name == "memory_store":
            result = _tools_handler().memory_store(
                content=arguments["content"],
                tags=arguments.get("tags"),
                session=arguments.get("session", "default"),
                turn=arguments.get("turn", 0),
                agent_id=arguments.get("agent_id", "default"),
            )
        elif name == "memory_search":
            result = _tools_handler().memory_search(
                query=arguments["query"],
                top_k=arguments.get("top_k", 5),
                session=arguments.get("session"),
                agent_id=arguments.get("agent_id"),
            )
        elif name == "memory_summarize":
            result = _tools_handler().memory_summarize(
                session=arguments.get("session", "default"),
                max_chars=arguments.get("max_chars", 500),
            )
        elif name == "memory_stats":
            result = _tools_handler().memory_stats()
        elif name == "memory_graph":
            result = _tools_handler().memory_graph(session=arguments.get("session"))
        else:
            raise ValueError(f"Outil inconnu : {name}")
        _log(f"tool={name} ok")
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False))]
    except Exception as exc:
        _log(f"tool={name} ERROR: {exc}")
        return [
            TextContent(
                type="text",
                text=json.dumps({"error": str(exc), "tool": name}, ensure_ascii=False),
            )
        ]


async def run_server() -> None:
    _log("server starting (memory_mcp.server)")
    _log("preloading embedding model — please wait 30-90s on first run...")
    try:
        from memory_mcp.embeddings import encode

        encode("membridge ready")
        _log("embedding model ready")
    except Exception as exc:
        _log(f"WARNING: model preload failed ({exc}) — will retry on first tool call")

    async with stdio_server() as (read_stream, write_stream):
        _log("stdio transport ready")
        await app.run(read_stream, write_stream, app.create_initialization_options())


def main() -> None:
    try:
        asyncio.run(run_server())
    except Exception as exc:
        _log(f"FATAL: {exc}")
        raise


if __name__ == "__main__":
    main()
