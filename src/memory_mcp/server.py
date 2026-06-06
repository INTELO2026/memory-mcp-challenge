"""Serveur MCP exposant memory_store, memory_search, memory_summarize, memory_stats.

Un agent externe (Claude Desktop, un client MCP maison, etc.) se connecte en
stdio et appelle les 4 outils. La mémoire vit en RAM par défaut ; si la variable
d'environnement ``MEMORY_DB_PATH`` est définie, elle est persistée sur disque
(piste bonus « persistance entre sessions »).
"""

from __future__ import annotations

import asyncio
import json
import os

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from memory_mcp.storage import MemoryStore
from memory_mcp.tools import MemoryTools

# Budget par défaut du résumé, aligné sur le cœur mémoire (tools.memory_summarize).
SUMMARY_DEFAULT_MAX_CHARS = 180

_DB_PATH = os.getenv("MEMORY_DB_PATH", ":memory:")
app = Server("memory-mcp")
tools_handler = MemoryTools(MemoryStore(_DB_PATH))


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
            description="Recherche sémantique dans la mémoire (comprend les paraphrases).",
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
            description="Résumé compressé de l'historique d'une session, conservant les faits.",
            inputSchema={
                "type": "object",
                "properties": {
                    "session": {"type": "string", "description": "ID de session"},
                    "max_chars": {
                        "type": "integer",
                        "description": "Taille max du résumé",
                        "default": SUMMARY_DEFAULT_MAX_CHARS,
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


def _dispatch(name: str, arguments: dict) -> dict:
    """Aiguille un appel d'outil vers le handler mémoire correspondant.

    Lève ``KeyError`` si un argument requis manque, ``ValueError`` si l'outil
    est inconnu — ces cas sont transformés en réponse d'erreur propre par
    ``call_tool`` (le serveur ne doit jamais planter sur une entrée invalide).
    """
    if name == "memory_store":
        if "content" not in arguments:
            raise KeyError("content")
        return tools_handler.memory_store(
            content=arguments["content"],
            tags=arguments.get("tags"),
            session=arguments.get("session", "default"),
            turn=arguments.get("turn", 0),
        )
    if name == "memory_search":
        if "query" not in arguments:
            raise KeyError("query")
        return tools_handler.memory_search(
            query=arguments["query"],
            top_k=arguments.get("top_k", 5),
            session=arguments.get("session"),
        )
    if name == "memory_summarize":
        return tools_handler.memory_summarize(
            session=arguments.get("session", "default"),
            max_chars=arguments.get("max_chars", SUMMARY_DEFAULT_MAX_CHARS),
        )
    if name == "memory_stats":
        return tools_handler.memory_stats()
    raise ValueError(f"Outil inconnu : {name}")


@app.call_tool()
async def call_tool(name: str, arguments: dict | None) -> list[TextContent]:
    try:
        result = _dispatch(name, arguments or {})
    except KeyError as exc:
        result = {"error": f"Argument requis manquant : {exc.args[0]}", "tool": name}
    except ValueError as exc:
        result = {"error": str(exc), "tool": name}
    return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False))]


async def run_server() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


def main() -> None:
    asyncio.run(run_server())


if __name__ == "__main__":
    main()
