"""LLM brain — uses memory context + API key to generate intelligent replies."""

from __future__ import annotations

import os

import httpx

_DEFAULT_MODELS = {
    "gemini": "gemini-1.5-flash",
    "openai": "gpt-4o-mini",
    "groq": "llama-3.1-8b-instant",
}


def _provider() -> str:
    return os.environ.get("LLM_PROVIDER", "gemini").lower()


def _model() -> str:
    return os.environ.get("LLM_MODEL") or _DEFAULT_MODELS.get(_provider(), "gemini-1.5-flash")


def _api_key() -> str | None:
    keys = {
        "gemini": os.environ.get("GEMINI_API_KEY"),
        "openai": os.environ.get("OPENAI_API_KEY"),
        "groq": os.environ.get("GROQ_API_KEY"),
    }
    return keys.get(_provider()) or os.environ.get("LLM_API_KEY")


def is_configured() -> bool:
    return bool(_api_key())


def brain_status() -> dict:
    provider = _provider()
    on = is_configured()
    return {
        "on": on,
        "provider": provider,
        "model": _model() if on else None,
        "label": f"{provider.upper()} ON" if on else "Brain OFF — add API key to .env",
    }


def generate_reply(user_message: str, memory_context: str) -> str:
    """Call LLM with compressed memory context. Falls back if no key."""
    key = _api_key()
    if not key:
        raise RuntimeError("No API key configured")

    system = (
        "You are a friendly, helpful AI assistant in a live chat. "
        "You receive a compressed MEMORY CONTEXT from an MCP memory server — use it to remember "
        "facts the user shared earlier (exams, plans, names, preferences). "
        "Respond naturally in the same language the user writes in. "
        "Never repeat or echo the user's message. Never say 'according to memory' or quote raw memory lines. "
        "Give a real, helpful reply in 1-3 sentences.\n\n"
        f"MEMORY CONTEXT:\n{memory_context or '(empty — first message)'}"
    )

    if _provider() == "gemini":
        return _gemini(key, system, user_message)
    return _openai_compatible(key, system, user_message)


def _gemini(key: str, system: str, user_message: str) -> str:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{_model()}:generateContent"
    payload = {
        "contents": [{"parts": [{"text": f"{system}\n\nUser: {user_message}"}]}],
        "generationConfig": {"maxOutputTokens": 300, "temperature": 0.7},
    }
    with httpx.Client(timeout=60.0) as client:
        r = client.post(url, params={"key": key}, json=payload)
        r.raise_for_status()
        data = r.json()
    return data["candidates"][0]["content"]["parts"][0]["text"].strip()


def _openai_compatible(key: str, system: str, user_message: str) -> str:
    provider = _provider()
    base = os.environ.get(
        "LLM_BASE_URL",
        "https://api.openai.com/v1" if provider == "openai" else "https://api.groq.com/openai/v1",
    )
    payload = {
        "model": _model(),
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user_message},
        ],
        "max_tokens": 300,
        "temperature": 0.7,
    }
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    with httpx.Client(timeout=60.0) as client:
        r = client.post(f"{base}/chat/completions", json=payload, headers=headers)
        r.raise_for_status()
        data = r.json()
    return data["choices"][0]["message"]["content"].strip()


def fallback_reply(user_message: str, memory_context: str) -> str:
    status = brain_status()
    if not status["on"]:
        return (
            "I saved your message to MCP memory, but the AI brain is OFF. "
            "Add GROQ_API_KEY (or GEMINI_API_KEY) to .env and restart the server."
        )
    return (
        f"I heard you, but the AI call failed. Your message is saved in memory. "
        f"Try again in a moment."
    )
