"""Appels LLM pour l'agent de démo — API réelle uniquement."""

from __future__ import annotations

from memory_mcp.llm_client import LLMNotConfiguredError, generate_text


def generate_reply(context: str, user_message: str) -> str:
    """Génère une réponse assistant via OpenAI ou Gemini."""
    prompt = (
        "Tu es un agent support client TechCorp. Réponds brièvement en français.\n"
        "Utilise UNIQUEMENT les informations du contexte mémoire.\n"
        "Si une information manque, dis-le clairement.\n\n"
        f"Contexte mémoire :\n{context}\n\n"
        f"Message client : {user_message}\n\n"
        "Réponse :"
    )
    return generate_text(prompt, max_output_tokens=300)


def require_llm_configured() -> None:
    """Vérifie qu'un LLM est configuré avant de lancer la démo."""
    from memory_mcp.config import is_llm_configured

    if not is_llm_configured():
        raise LLMNotConfiguredError(
            "Démo agent : OPENAI_API_KEY ou GEMINI_API_KEY requise.\n"
            "1. Copiez .env.example → .env\n"
            "2. Collez votre clé\n"
            "3. Relancez : python -m demo.agent"
        )


def require_gemini_configured() -> None:
    """Alias compatibilité."""
    require_llm_configured()
