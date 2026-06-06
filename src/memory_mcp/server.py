"""Serveur MCP — 4 outils avancés avec métadonnées complètes."""

from __future__ import annotations

import asyncio
import json

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from memory_mcp.config import ensure_env_loaded
from memory_mcp.tools import MemoryTools

ensure_env_loaded()

app = Server("memory-mcp")
tools_handler = MemoryTools()


@app.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="memory_store",
            description=(
                "Enregistre une information dans la mémoire avec métadonnées "
                "(session, date ISO, importance 0-3, tags). Déduplication automatique."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "content": {"type": "string", "description": "Contenu à mémoriser"},
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Tags sémantiques (fact, exchange, noise…)",
                    },
                    "session": {"type": "string", "description": "Identifiant de session"},
                    "turn": {"type": "integer", "description": "Numéro de tour conversation"},
                    "importance": {
                        "type": "integer",
                        "description": "Importance explicite 0-3 (sinon déduite des tags)",
                        "minimum": 0,
                        "maximum": 3,
                    },
                },
                "required": ["content"],
            },
        ),
        Tool(
            name="memory_search",
            description=(
                "Récupère par similarité sémantique les k souvenirs pertinents. "
                "Ranking hybride : sémantique + lexical + domaine + hiérarchie."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Requête en langage naturel"},
                    "top_k": {"type": "integer", "default": 5},
                    "session": {"type": "string", "description": "Filtrer par session"},
                    "tag": {"type": "string", "description": "Exiger un tag"},
                    "min_importance": {
                        "type": "integer",
                        "default": 0,
                        "description": "Importance minimale",
                    },
                    "exclude_tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Tags à exclure",
                    },
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="memory_summarize",
            description=(
                "Renvoie un résumé compressé de l'historique d'une session — "
                "cerveau de la compression avec ratio et faits préservés."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "session": {"type": "string", "default": "default"},
                    "max_chars": {"type": "integer"},
                    "max_tokens": {"type": "integer", "default": 200},
                    "use_llm": {
                        "type": "boolean",
                        "default": False,
                        "description": "Utiliser LLM si MEMBRIDGE_USE_LLM=1",
                    },
                },
            },
        ),
        Tool(
            name="memory_stats",
            description=(
                "Métriques : tokens stockés, tokens économisés, nombre d'entrées, "
                "sessions actives, moteur embeddings, features avancées."
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
    if name == "memory_store":
        result = tools_handler.memory_store(
            content=arguments["content"],
            tags=arguments.get("tags"),
            session=arguments.get("session", "default"),
            turn=arguments.get("turn", 0),
            importance=arguments.get("importance"),
        )
    elif name == "memory_search":
        result = tools_handler.memory_search(
            query=arguments["query"],
            top_k=arguments.get("top_k", 5),
            session=arguments.get("session"),
            tag=arguments.get("tag"),
            min_importance=arguments.get("min_importance", 0),
            exclude_tags=arguments.get("exclude_tags"),
        )
    elif name == "memory_summarize":
        result = tools_handler.memory_summarize(
            session=arguments.get("session", "default"),
            max_chars=arguments.get("max_chars"),
            max_tokens=arguments.get("max_tokens"),
            use_llm=arguments.get("use_llm", False),
        )
    elif name == "memory_stats":
        result = tools_handler.memory_stats(session=arguments.get("session"))
    else:
        raise ValueError(f"Outil inconnu : {name}")

    return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False))]


async def run_server() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


def main() -> None:
    ensure_env_loaded()
    asyncio.run(run_server())


if __name__ == "__main__":
    main()
