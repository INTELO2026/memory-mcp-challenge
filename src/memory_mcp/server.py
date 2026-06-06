"""Serveur MCP exposant memory_store, memory_search, memory_summarize, memory_stats."""

from __future__ import annotations

import asyncio
import json

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from memory_mcp.runtime import get_tools

app = Server("memory-mcp")
tools_handler = get_tools()


@app.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="memory_store",
            description="Stocke un fragment de mémoire avec métadonnées (session, importance, date).",
            inputSchema={
                "type": "object",
                "properties": {
                    "content": {"type": "string", "description": "Contenu à mémoriser"},
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Tags catégorisant l'information",
                    },
                    "session": {"type": "string", "description": "ID de session"},
                    "turn": {"type": "integer", "description": "Numéro de tour"},
                    "importance": {
                        "type": "number",
                        "description": "Importance (0.0-1.0, défaut 0.5)",
                        "default": 0.5,
                    },
                    "date": {
                        "type": "string",
                        "description": "Date ISO (défaut = maintenant)",
                    },
                    "model": {
                        "type": "string",
                        "description": "Slug du modèle IA de l'agent appelant "
                        "(ex. 'claude-opus-4-8'). Déclaré ici car les outils MCP "
                        "n'ont pas d'autre moyen de le connaître ; sert au chiffrage "
                        "du coût (memory_stats, tableau de bord).",
                    },
                    "key": {
                        "type": "string",
                        "description": "Étiquette courte et stable (ex. 'nom_client', "
                        "'num_contrat') pour retrouver l'info directement via "
                        "memory_keys, sans recherche sémantique floue.",
                    },
                },
                "required": ["content"],
            },
        ),
        Tool(
            name="memory_keys",
            description="Liste l'index de la mémoire : la clé (key) et la valeur "
            "(content) de chaque donnée stockée, avec ses métadonnées. À utiliser "
            "pour retrouver une info précise directement, sans recherche floue.",
            inputSchema={
                "type": "object",
                "properties": {
                    "session": {
                        "type": "string",
                        "description": "Filtrer par session (sinon toutes les sessions)",
                    },
                },
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
                        "default": 400,
                    },
                },
            },
        ),
        Tool(
            name="memory_stats",
            description="Retourne les statistiques de consommation de tokens. "
            "Si 'model' est fourni, ajoute le coût estimé (USD) via models.dev ; "
            "avec plusieurs modèles, le coût est détaillé par modèle puis additionné.",
            inputSchema={
                "type": "object",
                "properties": {
                    "model": {
                        "description": "Slug du modèle IA (ex. 'claude-opus-4-8' ou "
                        "'anthropic/claude-sonnet-4-6'), une regex, ou une liste de "
                        "slugs, pour chiffrer le coût par modèle via models.dev. "
                        "Slug introuvable → repli sur un Sonnet récent.",
                        "anyOf": [
                            {"type": "string"},
                            {"type": "array", "items": {"type": "string"}},
                        ],
                    },
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
            importance=arguments.get("importance", 0.5),
            date=arguments.get("date"),
            model=arguments.get("model"),
            key=arguments.get("key"),
        )
    elif name == "memory_keys":
        result = tools_handler.memory_keys(session=arguments.get("session"))
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
        result = tools_handler.memory_stats(model=arguments.get("model"))
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
