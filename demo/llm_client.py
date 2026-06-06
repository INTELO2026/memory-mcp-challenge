"""Interface LLM pour l'agent de démo (Phase 2).

Sélection via env ``MEMBRIDGE_LLM`` :
- ``gemini`` (défaut) -> Google ``gemini-2.0-flash`` si ``GEMINI_API_KEY`` présente.
- ``mock``            -> réponse déterministe déduite du contexte (sans réseau).

Tout import réseau est paresseux : importer ce module ne déclenche aucun appel.
"""

from __future__ import annotations

import os
import re
from abc import ABC, abstractmethod

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    pass


class LLMClient(ABC):
    name: str = "base"

    @abstractmethod
    def generate(self, system: str, user: str) -> str: ...


class MockClient(LLMClient):
    """Réponse déterministe : renvoie la ligne du contexte la plus pertinente.

    Permet de faire tourner la démo (et la CI) sans clé ni réseau.
    """

    name = "mock"

    def generate(self, system: str, user: str) -> str:
        parts = user.split("Question:")
        context = parts[0]
        question = parts[-1] if len(parts) > 1 else ""
        q_words = {w for w in re.findall(r"\w+", question.lower()) if len(w) > 3}
        best, best_score = "", 0
        for line in context.splitlines():
            line = line.strip("- ").strip()
            # Ne garde que les souvenirs (lignes factuelles), pas les en-têtes.
            if not line or line.endswith(":") or line.lower().startswith("résumé"):
                continue
            score = len(q_words & {w for w in re.findall(r"\w+", line.lower())})
            if score > best_score:
                best, best_score = line, score
        return (
            f"(mock) D'après ma mémoire : {best}" if best else "(mock) Je n'ai pas l'information."
        )


class GeminiClient(LLMClient):
    name = "gemini"
    _MODEL = os.getenv("MEMBRIDGE_GEMINI_CHAT_MODEL", "models/gemini-2.0-flash")

    def __init__(self, api_key: str | None = None) -> None:
        import google.generativeai as genai

        key = api_key or os.getenv("GEMINI_API_KEY")
        if not key:
            raise RuntimeError("GEMINI_API_KEY manquante")
        genai.configure(api_key=key)
        self._model = genai.GenerativeModel(self._MODEL)

    def generate(self, system: str, user: str) -> str:
        resp = self._model.generate_content(f"{system}\n\n{user}")
        return (getattr(resp, "text", "") or "").strip()


class ResilientClient(LLMClient):
    """Essaie un client principal (Gemini) puis bascule sur le mock en cas d'erreur.

    Garantit que la démo tourne toujours (quota épuisé, hors-ligne, etc.).
    """

    def __init__(self, primary: LLMClient, fallback: LLMClient) -> None:
        self.primary = primary
        self.fallback = fallback
        self.name = primary.name

    def generate(self, system: str, user: str) -> str:
        try:
            out = self.primary.generate(system, user)
            if out:
                return out
        except Exception:
            self.name = f"{self.primary.name}->mock"
        return self.fallback.generate(system, user)


def get_llm_client() -> LLMClient:
    choice = os.getenv("MEMBRIDGE_LLM", "gemini").strip().lower()
    if choice == "mock":
        return MockClient()
    if os.getenv("GEMINI_API_KEY"):
        try:
            return ResilientClient(GeminiClient(), MockClient())
        except Exception:
            pass
    return MockClient()
