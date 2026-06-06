"""Serveur MCP exposant memory_store, memory_search, memory_summarize, memory_stats."""

from __future__ import annotations

import asyncio
import json

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from memory_mcp.live import publish_live
from memory_mcp.tools import MemoryTools

app = Server("memory-mcp")
tools_handler = MemoryTools()

publish_live(status="online", detail="server_started")


@app.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="memory_store",
            description="Stocke un fragment de mémoire avec tags optionnels.",
            inputSchema={
                "type": "object",
                "properties": {
                    "content": {"type": "string", "description": "Contenu à mémoriser"},
                    "tags": {"type": "array", "items": {"type": "string"}, "description": "Tags"},
                    "session": {"type": "string", "description": "ID de session"},
                    "turn": {"type": "integer", "description": "Numéro de tour"},
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
                        "default": 200,
                    },
                },
            },
        ),
        Tool(
            name="memory_stats",
            description="Retourne les statistiques de consommation de tokens.",
            inputSchema={"type": "object", "properties": {}},
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    if name == "memory_store":
        result = tools_handler.memory_store(
            content=arguments["content"],
            tags=arguments.get("tags"),
            session=arguments.get("session", "default"),
            turn=arguments.get("turn", 0),
        )
    elif name == "memory_search":
        result = tools_handler.memory_search(
            query=arguments["query"],
            top_k=arguments.get("top_k", 5),
            session=arguments.get("session"),
        )
    elif name == "memory_summarize":
        result = tools_handler.memory_summarize(
            session=arguments.get("session", "default"),
            max_chars=arguments.get("max_chars", 200),
        )
    elif name == "memory_stats":
        result = tools_handler.memory_stats()
    else:
        raise ValueError(f"Outil inconnu : {name}")

    return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False))]


async def run_server() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


def main() -> None:
    asyncio.run(run_server())


if __name__ == "__main__":
    main()
