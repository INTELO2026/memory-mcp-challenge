"""Client Gemini centralisé — appels API réels via google-genai, credentials via .env."""

from __future__ import annotations

import logging
import os

from memory_mcp.config import get_settings, is_gemini_configured

logger = logging.getLogger(__name__)


class GeminiNotConfiguredError(RuntimeError):
    """Levée quand les credentials Gemini sont absents ou invalides."""


def _build_client():
    from google import genai

    settings = get_settings()
    use_vertex = os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )

    if settings.gemini_api_key:
        return genai.Client(api_key=settings.gemini_api_key)

    if use_vertex and settings.google_cloud_project:
        return genai.Client(
            vertexai=True,
            project=settings.google_cloud_project,
            location=settings.google_cloud_location,
        )

    raise GeminiNotConfiguredError(
        "Gemini non configuré.\n"
        "Option 1 : GEMINI_API_KEY=AIzaSy... (AI Studio)\n"
        "Option 2 : GOOGLE_GENAI_USE_VERTEXAI=1 + GOOGLE_CLOUD_PROJECT + gcloud auth"
    )


def generate_text(prompt: str) -> str:
    if not is_gemini_configured():
        raise GeminiNotConfiguredError(
            "GEMINI_API_KEY absente. Lancez : python scripts/configure_gemini.py"
        )

    settings = get_settings()
    try:
        client = _build_client()
        response = client.models.generate_content(
            model=settings.gemini_model,
            contents=prompt,
        )
        text = (response.text or "").strip()
        if not text:
            raise RuntimeError("Réponse Gemini vide.")
        return text
    except GeminiNotConfiguredError:
        raise
    except Exception as exc:
        logger.exception("Erreur appel Gemini")
        message = str(exc)
        if "401" in message or "UNAUTHENTICATED" in message or "ACCESS_TOKEN" in message:
            raise GeminiNotConfiguredError(
                "Authentification Gemini refusée (401).\n"
                "Utilisez une clé AI Studio (AIzaSy...) — PAS une clé Google Cloud (AQ.*).\n"
                "Créez-la sur : https://aistudio.google.com/apikey\n"
                "Puis : python scripts/configure_llm.py --provider gemini --key AIzaSy..."
            ) from exc
        raise RuntimeError(f"Appel Gemini échoué : {exc}") from exc
