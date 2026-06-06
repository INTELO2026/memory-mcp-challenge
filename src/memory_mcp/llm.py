"""Client LLM Gemini pour l'agent de démonstration (avec repli déterministe).

L'agent ne *raisonne* que sur le contexte qu'on lui fournit :
- en mode naïf : tout l'historique (cher) ;
- en mode MemBridge : résumé + souvenirs pertinents (léger).

Si aucune clé Gemini n'est disponible, on bascule sur un répondeur extractif déterministe :
la démo reste fonctionnelle hors-ligne, et la CI ne dépend jamais d'un appel réseau.
"""

from __future__ import annotations

import os
import re

SYSTEM_PROMPT = (
    "Tu es un assistant de support client. Réponds à la question UNIQUEMENT à partir du "
    "contexte fourni, de façon concise et factuelle (une phrase). Si l'information est absente, "
    "réponds : « Information non disponible »."
)


class GeminiChat:
    def __init__(self, model: str | None = None, api_key: str | None = None) -> None:
        self.model = model or os.getenv("MEMBRIDGE_GEMINI_CHAT_MODEL", "gemini-flash-latest")
        self._api_key = api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        self._client = None

    def available(self) -> bool:
        return bool(self._api_key)

    def _ensure(self) -> None:
        if self._client is None:
            from google import genai

            self._client = genai.Client(api_key=self._api_key)

    def generate(self, question: str, context: str, max_retries: int = 3) -> str:
        self._ensure()
        assert self._client is not None
        import time

        from google.genai import types

        prompt = f"Contexte :\n{context}\n\nQuestion : {question}"
        delay = 1.0
        for attempt in range(max_retries):
            try:
                resp = self._client.models.generate_content(
                    model=self.model,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        system_instruction=SYSTEM_PROMPT, temperature=0.0
                    ),
                )
                return (resp.text or "").strip()
            except Exception as exc:
                msg = str(exc).lower()
                transient = any(k in msg for k in ("429", "rate", "quota", "503", "timeout"))
                if attempt == max_retries - 1 or not transient:
                    raise
                time.sleep(delay)
                delay *= 2
        return ""


def deterministic_answer(question: str, context: str) -> str:
    """Répondeur extractif sans LLM : renvoie la phrase la plus pertinente du contexte."""
    lines = [line.strip(" -•\t") for line in re.split(r"[\n|]+", context) if line.strip()]
    if not lines:
        return "Information non disponible"
    q_words = {w for w in re.findall(r"\w+", question.lower()) if len(w) > 3}
    best, best_score = lines[0], -1
    for line in lines:
        score = len({w for w in re.findall(r"\w+", line.lower()) if len(w) > 3} & q_words)
        if score > best_score:
            best, best_score = line, score
    return best


class Agent:
    """Agent de support qui répond via la mémoire (ou l'historique en mode naïf)."""

    def __init__(self, prefer_llm: bool = True) -> None:
        self.chat = GeminiChat()
        self.use_llm = prefer_llm and self.chat.available()
        self.backend = "gemini" if self.use_llm else "déterministe"

    def answer(self, question: str, context: str) -> str:
        if self.use_llm:
            try:
                out = self.chat.generate(question, context)
                if out:
                    return out
            except Exception:
                pass
        return deterministic_answer(question, context)
