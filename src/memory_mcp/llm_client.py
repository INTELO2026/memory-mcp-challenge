"""Client LLM unifié — OpenAI ou Gemini, credentials via .env uniquement."""

from __future__ import annotations

import logging

from memory_mcp.config import get_settings, is_llm_configured

logger = logging.getLogger(__name__)


class LLMNotConfiguredError(RuntimeError):
    """Levée quand aucune clé LLM valide n'est configurée."""


def _generate_openai(prompt: str, max_output_tokens: int | None = None) -> str:
    from openai import OpenAI

    settings = get_settings()
    if not settings.openai_api_key:
        raise LLMNotConfiguredError("OPENAI_API_KEY absente dans .env")

    client = OpenAI(api_key=settings.openai_api_key)
    kwargs: dict = {
        "model": settings.openai_model,
        "messages": [{"role": "user", "content": prompt}],
    }
    if max_output_tokens is not None:
        kwargs["max_tokens"] = max_output_tokens

    response = client.chat.completions.create(**kwargs)
    text = (response.choices[0].message.content or "").strip()
    if not text:
        raise RuntimeError("Réponse OpenAI vide.")
    return text


def _generate_gemini(prompt: str) -> str:
    from memory_mcp.gemini_client import generate_text as gemini_generate

    return gemini_generate(prompt)


def generate_text(prompt: str, max_output_tokens: int | None = None) -> str:
    """Génère du texte via le provider configuré (OpenAI par défaut si clé présente)."""
    if not is_llm_configured():
        raise LLMNotConfiguredError(
            "LLM non configuré. Définissez OPENAI_API_KEY ou GEMINI_API_KEY dans .env"
        )

    settings = get_settings()
    try:
        if settings.llm_provider == "openai":
            return _generate_openai(prompt, max_output_tokens=max_output_tokens)
        return _generate_gemini(prompt)
    except LLMNotConfiguredError:
        raise
    except Exception as exc:
        logger.exception("Erreur appel LLM (%s)", settings.llm_provider)
        message = str(exc)
        if "401" in message or "invalid_api_key" in message.lower():
            raise LLMNotConfiguredError(
                f"Authentification {settings.llm_provider} refusée. Vérifiez votre clé dans .env."
            ) from exc
        if "429" in message or "insufficient_quota" in message.lower():
            raise RuntimeError(
                f"Quota {settings.llm_provider} épuisé (429). "
                "Vérifiez votre facturation sur platform.openai.com."
            ) from exc
        raise RuntimeError(f"Appel LLM échoué ({settings.llm_provider}) : {exc}") from exc
