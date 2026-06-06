"""Client MCP de validation : prouve qu'un agent externe se connecte au serveur.

Démarre le serveur ``memory-mcp`` dans un sous-processus, dialogue avec lui en
stdio (le protocole MCP standard), liste les outils puis appelle les quatre.
C'est la preuve concrète, exigée par le sujet, qu'« un vrai agent peut s'y
connecter ».

Usage :
    python scripts/mcp_smoke_client.py
"""

from __future__ import annotations

import asyncio
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def _text(result) -> str:
    """Concatène le contenu texte d'une réponse d'outil MCP."""
    return " ".join(block.text for block in result.content if getattr(block, "text", None))


async def main() -> None:
    # On lance le serveur via le module, indépendamment de l'installation du
    # script console « memory-mcp ».
    params = StdioServerParameters(command=sys.executable, args=["-m", "memory_mcp.server"])

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = await session.list_tools()
            print("Outils exposés :", [t.name for t in tools.tools])

            print("\n— memory_store —")
            r = await session.call_tool(
                "memory_store",
                {
                    "content": "user: Je m'appelle Marie Dupont, cliente premium.",
                    "tags": ["fact"],
                    "session": "demo-client",
                    "turn": 1,
                },
            )
            print(_text(r))

            print("\n— memory_search (paraphrase) —")
            r = await session.call_tool(
                "memory_search",
                {"query": "identité de la cliente", "top_k": 1, "session": "demo-client"},
            )
            print(_text(r))

            print("\n— memory_summarize —")
            r = await session.call_tool("memory_summarize", {"session": "demo-client"})
            print(_text(r))

            print("\n— memory_stats —")
            r = await session.call_tool("memory_stats", {})
            print(_text(r))

            print("\n— gestion d'erreur (outil inconnu) —")
            r = await session.call_tool("memory_unknown", {})
            print(_text(r))

    print("\nOK : le serveur a répondu aux 4 outils via stdio.")


if __name__ == "__main__":
    asyncio.run(main())
