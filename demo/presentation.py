"""Orchestrateur démo jury — benchmark + bonus + exports dashboard."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent


def main() -> None:
    import os

    base_env = os.environ.copy()
    base_env["PYTHONPATH"] = f"src{Path.pathsep}."
    os.environ.update(base_env)

    def run_module(module: str, *args: str) -> None:
        cmd = [sys.executable, "-m", module, *args]
        print(f"\n>>> {' '.join(cmd)}\n")
        subprocess.run(cmd, cwd=ROOT, check=True, env=base_env)

    print("=" * 60)
    print("MemBridge — Preparation demo jury (sujet complet)")
    print("=" * 60)

    run_module("benchmark.harness")
    run_module("demo.agent", "--offline", "--export")
    run_module("demo.multi_agent")
    run_module("demo.persistence")

    print("\n" + "=" * 60)
    print("Pret. Lancez : python dashboard/server.py --open")
    print("  - Benchmark  : /dashboard/index.html")
    print("  - Demo live  : /dashboard/live.html")
    print("  - Bonus §10  : /dashboard/bonus.html")
    print("=" * 60)


if __name__ == "__main__":
    main()
