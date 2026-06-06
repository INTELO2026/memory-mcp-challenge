"""Détecte les secrets commités par erreur (clés API, tokens)."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Dossiers/fichiers versionnés à scanner
SCAN_DIRS = ("src", "tests", "benchmark", "demo", "scripts", ".github")
SCAN_FILES = ("pyproject.toml", "requirements.txt", "README.md", "PITCH.md")

# Patterns de secrets — pas de faux positifs volontaires dans les placeholders courts
SECRET_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("OpenAI project key", re.compile(r"sk-proj-[A-Za-z0-9_-]{20,}")),
    ("OpenAI API key", re.compile(r"sk-[A-Za-z0-9]{20,}")),
    ("Google AI Studio key", re.compile(r"AIza[Sy][A-Za-z0-9_-]{30,}")),
    ("Google AQ token", re.compile(r"AQ\.[A-Za-z0-9_-]{20,}")),
]

# Fichiers toujours ignorés
IGNORE_NAMES = {".env", ".env.local", ".env.production"}


def _iter_files() -> list[Path]:
    files: list[Path] = []
    for name in SCAN_FILES:
        path = ROOT / name
        if path.is_file():
            files.append(path)
    for folder in SCAN_DIRS:
        base = ROOT / folder
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if path.is_file() and path.name not in IGNORE_NAMES:
                if path.suffix in {
                    ".py",
                    ".yml",
                    ".yaml",
                    ".md",
                    ".html",
                    ".json",
                    ".toml",
                    ".txt",
                    ".ini",
                }:
                    files.append(path)
    return files


def scan() -> list[str]:
    violations: list[str] = []
    for path in _iter_files():
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        rel = path.relative_to(ROOT)
        for label, pattern in SECRET_PATTERNS:
            if pattern.search(text):
                violations.append(f"{rel}: possible {label} détectée")
    return violations


def main() -> int:
    violations = scan()
    if violations:
        print("Secrets potentiels trouvés dans le code versionné :", file=sys.stderr)
        for item in violations:
            print(f"  - {item}", file=sys.stderr)
        print(
            "\nStockez les clés uniquement dans .env (gitignoré). "
            "Utilisez .env.example sans vraies valeurs.",
            file=sys.stderr,
        )
        return 1
    print("Aucun secret détecté dans les fichiers versionnés.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
