#!/usr/bin/env python3
"""Write MCP client config files with correct paths for this machine."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _python_exe() -> Path:
    if sys.platform == "win32":
        candidate = ROOT / ".venv" / "Scripts" / "python.exe"
    else:
        candidate = ROOT / ".venv" / "bin" / "python"
    if not candidate.exists():
        print(f"ERROR: venv not found at {candidate}")
        print("Run first: python -m venv .venv && pip install -e .")
        sys.exit(1)
    return candidate


def main() -> None:
    py = _python_exe()
    env_path = "src;." if sys.platform == "win32" else "src:."

    cursor_cfg = {
        "mcpServers": {
            "membridge": {
                "command": str(py),
                "args": ["-m", "memory_mcp.server"],
                "env": {"PYTHONPATH": env_path},
            }
        }
    }

    cursor_dir = ROOT / ".cursor"
    cursor_dir.mkdir(exist_ok=True)
    cursor_path = cursor_dir / "mcp.json"
    cursor_path.write_text(json.dumps(cursor_cfg, indent=2), encoding="utf-8")

    claude_cfg = {
        "mcpServers": {
            "membridge": {
                "command": str(py),
                "args": ["-m", "memory_mcp.server"],
                "env": {"PYTHONPATH": env_path},
            }
        }
    }
    config_dir = ROOT / "config"
    config_dir.mkdir(exist_ok=True)
    claude_path = config_dir / "claude_desktop_config.generated.json"
    claude_path.write_text(json.dumps(claude_cfg, indent=2), encoding="utf-8")

    print("MCP config written:")
    print(f"  Cursor:  {cursor_path}")
    print(f"  Claude:  {claude_path}")
    print()
    print("Next:")
    print("  1. Restart Cursor (or reload MCP servers)")
    print("  2. You should see 'membridge' with 4 tools")
    print("  3. Run: python scripts/test_mcp_connection.py")


if __name__ == "__main__":
    main()
