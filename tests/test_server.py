"""Tests serveur MCP — surface des outils et gestion d'erreurs (sans modèle).

Ces tests n'appellent ni store ni search, donc ne chargent pas le modèle
d'embeddings : ils restent rapides et adaptés au job `smoke`.
"""

import json

from memory_mcp import server


async def test_list_tools_exposes_four():
    tools = await server.list_tools()
    names = {t.name for t in tools}
    assert names == {"memory_store", "memory_search", "memory_summarize", "memory_stats"}


async def test_unknown_tool_returns_clean_error():
    out = await server.call_tool("memory_unknown", {})
    payload = json.loads(out[0].text)
    assert "error" in payload
    assert payload["tool"] == "memory_unknown"


async def test_missing_required_arg_returns_clean_error():
    out = await server.call_tool("memory_store", {})
    payload = json.loads(out[0].text)
    assert "error" in payload
    assert "content" in payload["error"]


async def test_stats_through_server():
    out = await server.call_tool("memory_stats", {})
    payload = json.loads(out[0].text)
    assert "total_tokens" in payload
