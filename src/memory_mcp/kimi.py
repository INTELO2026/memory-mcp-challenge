"""Client Kimi via OpenRouter."""

from __future__ import annotations

import os
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MODEL = "moonshotai/kimi-k2.6"
DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
MAX_RETRIES = 5
RETRY_DELAY = 3.0


def _load_env() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(ROOT / ".env")


def get_kimi_config() -> dict:
    _load_env()
    return {
        "api_key": os.environ.get("OPENROUTER_API_KEY"),
        "model": os.environ.get("KIMI_MODEL", DEFAULT_MODEL),
        "base_url": os.environ.get("OPENROUTER_BASE_URL", DEFAULT_BASE_URL),
        "site_url": os.environ.get("OPENROUTER_SITE_URL", "http://localhost:8080"),
        "app_name": os.environ.get("OPENROUTER_APP_NAME", "MemBridge"),
    }


def kimi_available() -> bool:
    return bool(get_kimi_config()["api_key"])


def kimi_chat(
    messages: list[dict[str, str]],
    *,
    max_tokens: int = 300,
    temperature: float = 0.3,
) -> str | None:
    """Appelle Kimi via OpenRouter."""
    config = get_kimi_config()
    if not config["api_key"]:
        print("[Kimi] Cle manquante : OPENROUTER_API_KEY dans .env")
        return None

    try:
        from openai import OpenAI
    except ImportError:
        print("[Kimi] Installez les deps : pip install -e \".[kimi]\"")
        return None

    client = OpenAI(
        api_key=config["api_key"],
        base_url=config["base_url"],
        default_headers={
            "HTTP-Referer": config["site_url"],
            "X-Title": config["app_name"],
        },
    )

    for attempt in range(MAX_RETRIES):
        try:
            response = client.chat.completions.create(
                model=config["model"],
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
            )
            return response.choices[0].message.content or ""
        except Exception as exc:
            err = str(exc).lower()
            if ("429" in err or "rate" in err) and attempt < MAX_RETRIES - 1:
                delay = RETRY_DELAY * (attempt + 1)
                print(f"[Kimi] Rate limit — retry dans {delay:.0f}s")
                time.sleep(delay)
                continue
            print(f"[Kimi] Erreur OpenRouter : {exc}")
            return None
    return None
