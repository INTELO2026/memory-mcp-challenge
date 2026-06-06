"""Configure et valide GEMINI_API_KEY dans .env (sans secret en dur dans le code)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"


def _read_env() -> dict[str, str]:
    if not ENV_PATH.exists():
        return {}
    data: dict[str, str] = {}
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.strip().startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        data[key.strip()] = value.strip()
    return data


def _write_env(values: dict[str, str]) -> None:
    lines = ENV_PATH.read_text(encoding="utf-8").splitlines() if ENV_PATH.exists() else []
    out: list[str] = []
    seen: set[str] = set()
    for line in lines:
        if "=" in line and not line.strip().startswith("#"):
            key = line.split("=", 1)[0].strip()
            if key in values:
                out.append(f"{key}={values[key]}")
                seen.add(key)
            else:
                out.append(line)
        else:
            out.append(line)
    for key, value in values.items():
        if key not in seen:
            out.append(f"{key}={value}")
    ENV_PATH.write_text("\n".join(out).rstrip() + "\n", encoding="utf-8")


def validate_key(api_key: str) -> str:
    api_key = api_key.strip()
    if not api_key:
        raise ValueError("Clé vide.")
    if api_key.startswith("AQ."):
        raise ValueError(
            "Format AQ.* incompatible avec Gemini Developer API. "
            "Utilisez une clé AI Studio (AIzaSy...) depuis https://aistudio.google.com/apikey"
        )
    if not api_key.startswith("AIza"):
        raise ValueError("Format inattendu. Une clé AI Studio commence généralement par AIzaSy...")

    import os

    os.environ["GEMINI_API_KEY"] = api_key
    os.environ["MEMBRIDGE_USE_GEMINI"] = "1"
    sys.path.insert(0, str(ROOT / "src"))
    from memory_mcp.config import ensure_env_loaded
    from memory_mcp.gemini_client import generate_text

    ensure_env_loaded()
    reply = generate_text("Réponds uniquement par le mot OK.")
    if not reply:
        raise ValueError("Réponse Gemini vide.")
    return reply.strip()[:80]


def main() -> int:
    parser = argparse.ArgumentParser(description="Configurer GEMINI_API_KEY dans .env")
    parser.add_argument("--key", help="Clé AI Studio (AIzaSy...)")
    parser.add_argument(
        "--from-env",
        action="store_true",
        help="Lire la clé depuis la variable d'environnement GEMINI_API_KEY_NEW",
    )
    args = parser.parse_args()

    api_key = args.key
    if args.from_env:
        import os

        api_key = os.environ.get("GEMINI_API_KEY_NEW", "")
    if not api_key:
        api_key = input("Collez votre clé AI Studio (AIzaSy...) : ").strip()

    print("Validation de la clé auprès de Gemini...")
    try:
        reply = validate_key(api_key)
    except Exception as exc:
        print(f"Échec : {exc}")
        return 1

    env = _read_env()
    env["GEMINI_API_KEY"] = api_key
    env.setdefault("GEMINI_MODEL", "gemini-2.0-flash")
    env.setdefault("MEMBRIDGE_USE_GEMINI", "1")
    _write_env({"GEMINI_API_KEY": api_key, "MEMBRIDGE_USE_GEMINI": "1"})
    print(f"Clé enregistrée dans .env — test Gemini OK : {reply!r}")
    print("Lancez : python -m demo.agent")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
