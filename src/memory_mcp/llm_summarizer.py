"""Résumé abstractif optionnel via Claude (fallback extractif si pas de clé API)."""

from __future__ import annotations

import json
import os


def llm_summarize_available() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def summarize_with_claude(
    subset_text: str, previous_summary: str = "", max_tokens: int = 400
) -> dict | None:
    """
    Appel Claude ciblé sur subset filtré uniquement (pas l'historique complet).
    Retourne JSON structuré ou None si indisponible.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return None

    try:
        import anthropic

        client = anthropic.Anthropic(api_key=api_key)
        prompt = f"""Tu compresses une mémoire de session agent IA.
Résumé précédent (déjà compressé): {previous_summary or "aucun"}

Nouveaux fragments à intégrer:
{subset_text[:3000]}

Réponds UNIQUEMENT en JSON valide:
{{
  "key_facts": ["fait1", "fait2"],
  "entities": {{"nom": "attribut"}},
  "open_questions": ["question sans réponse"],
  "context_anchors": ["éléments stables"]
}}
Max 300 tokens total."""

        msg = client.messages.create(
            model=os.environ.get("MEMBRIDGE_CLAUDE_MODEL", "claude-sonnet-4-20250514"),
            max_tokens=max_tokens,
            temperature=0,
            messages=[{"role": "user", "content": prompt}],
        )
        text = msg.content[0].text.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        return json.loads(text)
    except Exception:
        return None
