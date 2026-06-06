#!/usr/bin/env python3
"""Quick check: spawn MCP server over stdio and list tools."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def _server_params() -> StdioServerParameters:
    if sys.platform == "win32":
        py = ROOT / ".venv" / "Scripts" / "python.exe"
        env = {"PYTHONPATH": "src;."}
    else:
        py = ROOT / ".venv" / "bin" / "python"
        env = {"PYTHONPATH": "src:."}
    return StdioServerParameters(
        command=str(py),
        args=["-m", "memory_mcp.server"],
        env=env,
        cwd=str(ROOT),
    )


async def main() -> None:
    params = _server_params()
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            names = [t.name for t in tools.tools]
            print("MCP connection OK")
            print("Tools:", ", ".join(names))
            assert names == [
                "memory_store",
                "memory_search",
                "memory_summarize",
                "memory_stats",
            ], f"Unexpected tools: {names}"

            print("SUCCESS — external agent can connect via MCP stdio")


if __name__ == "__main__":
    asyncio.run(main())
