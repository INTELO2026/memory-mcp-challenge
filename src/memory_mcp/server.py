"""Serveur MCP exposant memory_store, memory_search, memory_summarize, memory_stats."""

from __future__ import annotations

import asyncio
import json

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from memory_mcp.tools import MemoryTools

app = Server("memory-mcp")
# telemetry=True : le serveur publie son activité en direct pour le tableau de bord.
tools_handler = MemoryTools(telemetry=True)


@app.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="memory_store",
            description="Stocke une information en mémoire (session, date, importance).",
            inputSchema={
                "type": "object",
                "properties": {
                    "content": {"type": "string", "description": "Contenu à mémoriser"},
                    "tags": {"type": "array", "items": {"type": "string"}, "description": "Tags"},
                    "session": {"type": "string", "description": "ID de session"},
                    "turn": {"type": "integer", "description": "Numéro de tour"},
                    "date": {"type": "string", "description": "Date/horodatage du souvenir (ISO)"},
                    "importance": {
                        "type": "number",
                        "description": "Score d'importance (1.0 = normal)",
                        "default": 1.0,
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
            name="memory_reset",
            description="Remet la session live à zéro (compteurs, mémoire, télémétrie).",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="memory_simulate",
            description="Joue une conversation de N tours pour alimenter la vue live "
            "(démo : l'économie monte avec le nombre de tours).",
            inputSchema={
                "type": "object",
                "properties": {
                    "turns": {
                        "type": "integer",
                        "description": "Nombre de tours à simuler",
                        "default": 50,
                    },
                    "session": {"type": "string", "description": "ID de session"},
                },
            },
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
            date=arguments.get("date", ""),
            importance=arguments.get("importance", 1.0),
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
            max_chars=arguments.get("max_chars", 500),
        )
    elif name == "memory_stats":
        result = tools_handler.memory_stats()
    elif name == "memory_reset":
        result = tools_handler.memory_reset()
    elif name == "memory_simulate":
        result = tools_handler.memory_simulate(
            turns=arguments.get("turns", 50),
            session=arguments.get("session", "live-demo"),
        )
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
