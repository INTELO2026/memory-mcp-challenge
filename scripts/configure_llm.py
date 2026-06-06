"""Configure OPENAI_API_KEY ou GEMINI_API_KEY dans .env (sans secret dans le code)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"


def _read_env_lines() -> list[str]:
    if not ENV_PATH.exists():
        return []
    return ENV_PATH.read_text(encoding="utf-8").splitlines()


def _upsert_env(key: str, value: str) -> None:
    lines = _read_env_lines()
    out: list[str] = []
    found = False
    for line in lines:
        if line.startswith(f"{key}="):
            out.append(f"{key}={value}")
            found = True
        else:
            out.append(line)
    if not found:
        out.append(f"{key}={value}")
    ENV_PATH.write_text("\n".join(out).rstrip() + "\n", encoding="utf-8")


def _validate_openai(api_key: str) -> str:
    import os

    os.environ["OPENAI_API_KEY"] = api_key
    os.environ["LLM_PROVIDER"] = "openai"
    os.environ["MEMBRIDGE_USE_LLM"] = "1"
    sys.path.insert(0, str(ROOT / "src"))
    from memory_mcp.config import ensure_env_loaded
    from memory_mcp.llm_client import generate_text

    ensure_env_loaded()
    return generate_text("Réponds uniquement par le mot OK.", max_output_tokens=10)


def _validate_gemini(api_key: str) -> str:
    import os

    os.environ["GEMINI_API_KEY"] = api_key
    os.environ["LLM_PROVIDER"] = "gemini"
    os.environ["MEMBRIDGE_USE_LLM"] = "1"
    sys.path.insert(0, str(ROOT / "src"))
    from memory_mcp.config import ensure_env_loaded
    from memory_mcp.gemini_client import generate_text

    ensure_env_loaded()
    return generate_text("Réponds uniquement par le mot OK.")


def _read_env_value(name: str) -> str:
    for line in _read_env_lines():
        if line.startswith(f"{name}="):
            return line.split("=", 1)[1].strip()
    return ""


def main() -> int:
    parser = argparse.ArgumentParser(description="Configurer une clé LLM dans .env")
    parser.add_argument("--provider", choices=("openai", "gemini"), required=True)
    parser.add_argument("--key", help="Clé API (sinon lire depuis .env avec --from-env)")
    parser.add_argument(
        "--from-env",
        action="store_true",
        help="Lire la clé depuis .env (GEMINI_API_KEY ou OPENAI_API_KEY)",
    )
    args = parser.parse_args()

    env_name = "GEMINI_API_KEY" if args.provider == "gemini" else "OPENAI_API_KEY"
    api_key = args.key.strip() if args.key else ""
    if args.from_env or not api_key:
        api_key = _read_env_value(env_name)
    if not api_key:
        print(f"Erreur : {env_name} vide dans .env", file=sys.stderr)
        return 1
    if api_key.startswith("AQ."):
        print(
            "Erreur : clé AQ.* incompatible. Créez une clé AIzaSy... sur "
            "https://aistudio.google.com/apikey",
            file=sys.stderr,
        )
        return 1

    print(f"Validation {args.provider}…")
    try:
        if args.provider == "openai":
            reply = _validate_openai(api_key)
            _upsert_env("OPENAI_API_KEY", api_key)
            _upsert_env("LLM_PROVIDER", "openai")
        else:
            reply = _validate_gemini(api_key)
            _upsert_env("GEMINI_API_KEY", api_key)
            _upsert_env("LLM_PROVIDER", "gemini")
        _upsert_env("MEMBRIDGE_USE_LLM", "1")
    except Exception as exc:
        print(f"Échec : {exc}")
        return 1

    print(f"Clé enregistrée dans .env — test OK : {reply!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
