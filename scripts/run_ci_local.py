"""Execute la meme pipeline que GitHub Actions (lint + smoke + regression)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(cmd: list[str]) -> None:
    print(f"\n>>> {' '.join(cmd)}\n")
    subprocess.run(cmd, cwd=ROOT, check=True)


def main() -> int:
    env = {"PYTHONPATH": f"src{Path.pathsep}."}
    import os

    base = os.environ.copy()
    base.update(env)

    steps = [
        ["ruff", "check", "src", "tests", "benchmark", "demo"],
        ["ruff", "format", "--check", "src", "tests", "benchmark", "demo"],
        [sys.executable, "scripts/check_secrets.py"],
        [sys.executable, "-m", "pytest", "tests/test_smoke.py", "-v", "--tb=short"],
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/test_regression.py",
            "tests/test_storage.py",
            "tests/test_tools.py",
            "tests/test_live_engine.py",
            "-v",
            "--tb=short",
        ],
    ]

    for cmd in steps:
        subprocess.run(cmd, cwd=ROOT, check=True, env=base)

    print("\n=== CI locale OK (lint + smoke + regression) ===")
    print("finale-eval : declenche sur PR vers main (tests caches prives).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
