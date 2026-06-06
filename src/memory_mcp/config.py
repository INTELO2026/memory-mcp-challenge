"""Configuration MemBridge — variables d'environnement uniquement, jamais de secrets en dur."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

_env_loaded = False


@dataclass(frozen=True)
class Settings:
    llm_provider: str
    openai_api_key: str | None
    openai_model: str
    gemini_api_key: str | None
    gemini_model: str
    summary_max_tokens: int
    summary_max_tokens_demo: int
    token_price_eur_per_m: float
    use_llm: bool
    google_cloud_project: str | None
    google_cloud_location: str
    db_path: str | None

    @property
    def active_model(self) -> str:
        if self.llm_provider == "openai":
            return self.openai_model
        return self.gemini_model


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def ensure_env_loaded() -> None:
    """Charge le fichier .env local s'il existe (ignoré par git)."""
    global _env_loaded
    if _env_loaded:
        return
    try:
        from dotenv import load_dotenv

        load_dotenv(_project_root() / ".env", override=False)
    except ImportError:
        pass
    _env_loaded = True


def _use_llm_flag() -> bool:
    for name in ("MEMBRIDGE_USE_LLM", "MEMBRIDGE_USE_GEMINI"):
        if os.environ.get(name, "").strip().lower() in ("1", "true", "yes"):
            return True
    return False


def _resolve_provider(openai_key: str | None, gemini_key: str | None) -> str:
    explicit = os.environ.get("LLM_PROVIDER", "").strip().lower()
    if explicit in ("openai", "gemini"):
        return explicit
    if openai_key:
        return "openai"
    if gemini_key:
        return "gemini"
    return "openai"


def get_settings() -> Settings:
    ensure_env_loaded()
    openai_key = os.environ.get("OPENAI_API_KEY", "").strip() or None
    gemini_raw = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    gemini_key = gemini_raw.strip() if gemini_raw and gemini_raw.strip() else None
    project = os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("GEMINI_PROJECT")
    project = project.strip() if project and project.strip() else None
    provider = _resolve_provider(openai_key, gemini_key)
    db_raw = os.environ.get("MEMBRIDGE_DB_PATH", "").strip()
    db_path = db_raw if db_raw else None
    return Settings(
        llm_provider=provider,
        openai_api_key=openai_key,
        openai_model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
        gemini_api_key=gemini_key,
        gemini_model=os.environ.get("GEMINI_MODEL", "gemini-2.0-flash"),
        summary_max_tokens=int(os.environ.get("SUMMARY_MAX_TOKENS", "80")),
        summary_max_tokens_demo=int(os.environ.get("SUMMARY_MAX_TOKENS_DEMO", "200")),
        token_price_eur_per_m=float(os.environ.get("TOKEN_PRICE_EUR_PER_M", "0.15")),
        use_llm=_use_llm_flag(),
        google_cloud_project=project,
        google_cloud_location=os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1"),
        db_path=db_path,
    )


def is_llm_configured() -> bool:
    settings = get_settings()
    if settings.llm_provider == "openai":
        return bool(settings.openai_api_key)
    if settings.gemini_api_key:
        return True
    use_vertex = os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )
    return bool(use_vertex and settings.google_cloud_project)


def is_gemini_configured() -> bool:
    """Compatibilité — préférez is_llm_configured()."""
    return is_llm_configured()
