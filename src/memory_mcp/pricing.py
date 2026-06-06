"""Tarification réelle des modèles via models.dev.

Récupère le catalogue public models.dev (prix en USD pour 1M de tokens), le met
en cache localement (et possède une petite table de repli hors-ligne), puis
calcule le coût d'une consommation de tokens pour un slug de modèle donné.

Le slug accepté est soit l'identifiant de modèle (`claude-opus-4-8`), soit la
forme qualifiée `provider/modele` (`anthropic/claude-sonnet-4-6`) pour lever
toute ambiguïté. Il peut aussi être une expression régulière : pratique pour les
slugs peu conventionnels (ex. Opus 4.8). Slug introuvable → repli Sonnet récent.
"""

from __future__ import annotations

import json
import re
import tempfile
import time
import urllib.request
from pathlib import Path

MODELS_DEV_URL = "https://models.dev/api.json"
_CACHE_PATH = Path(tempfile.gettempdir()) / "memory_mcp_models_dev.json"
_CACHE_TTL_SECONDS = 24 * 3600  # rafraîchit le cache une fois par jour

# Modèle de repli quand un slug demandé est introuvable : un Sonnet récent.
FALLBACK_MODEL = "claude-sonnet-4-6"

_CATALOG: dict | None = None

# Repli minimal (USD / 1M tokens) si ni cache disque ni réseau ne sont
# disponibles. Volontairement court et limité à des modèles récents :
# models.dev reste la source de vérité.
_FALLBACK: dict[str, dict[str, float]] = {
    "claude-opus-4-8": {"input": 5.0, "output": 25.0},
    "claude-sonnet-4-6": {"input": 3.0, "output": 15.0},
    "claude-haiku-4-5": {"input": 1.0, "output": 5.0},
    "gemini-2.0-flash": {"input": 0.1, "output": 0.4},
}


def _cache_fresh() -> bool:
    try:
        return (time.time() - _CACHE_PATH.stat().st_mtime) < _CACHE_TTL_SECONDS
    except OSError:
        return False


def _load_catalog(refresh: bool = False) -> dict:
    """Charge le catalogue models.dev (mémoire → cache disque → réseau)."""
    global _CATALOG
    if _CATALOG is not None and not refresh:
        return _CATALOG

    if not refresh and _cache_fresh():
        try:
            _CATALOG = json.loads(_CACHE_PATH.read_text(encoding="utf-8"))
            return _CATALOG
        except (OSError, json.JSONDecodeError):
            pass

    try:
        req = urllib.request.Request(MODELS_DEV_URL, headers={"User-Agent": "memory-mcp"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        try:
            _CACHE_PATH.write_text(json.dumps(data), encoding="utf-8")
        except OSError:
            pass
        _CATALOG = data
        return data
    except Exception:
        # Réseau indisponible : tente un cache périmé, sinon catalogue vide.
        if _CACHE_PATH.exists():
            try:
                _CATALOG = json.loads(_CACHE_PATH.read_text(encoding="utf-8"))
                return _CATALOG
            except (OSError, json.JSONDecodeError):
                pass
        _CATALOG = {}
        return _CATALOG


def _entry(prov_id: str, model_id: str, model: dict, *, match: str, requested: str) -> dict | None:
    cost = model.get("cost") or {}
    if cost.get("input") is None or cost.get("output") is None:
        return None
    return {
        "provider": prov_id,
        "model": model_id,
        "requested": requested,
        "match": match,  # "exact" | "regex"
        "input": float(cost["input"]),
        "output": float(cost["output"]),
        "cache_read": cost.get("cache_read"),
        "currency": "USD",
        "source": "models.dev",
    }


def get_model_pricing(slug: str, refresh: bool = False) -> dict | None:
    """Résout le tarif d'un modèle, slug exact OU expression régulière.

    Les slugs models.dev ne sont pas toujours conventionnels (ex. Opus 4.8).
    On tente donc : (1) correspondance exacte de l'id, puis (2) recherche par
    regex (insensible à la casse) sur l'id et le nom — en gardant le modèle le
    plus récent en cas d'égalité —, puis (3) la table de repli statique.
    `input`/`output` sont en USD pour 1M de tokens.
    """
    if not slug:
        return None
    if "/" in slug:
        provider_hint, model_q = slug.split("/", 1)
    else:
        provider_hint, model_q = "", slug

    catalog = _load_catalog(refresh=refresh)

    def _models():
        for prov_id, prov in catalog.items():
            if provider_hint and prov_id != provider_hint:
                continue
            for mid, m in (prov.get("models") or {}).items():
                yield prov_id, mid, m

    # 1) Correspondance exacte de l'identifiant.
    for prov_id, mid, m in _models():
        if mid == model_q:
            hit = _entry(prov_id, mid, m, match="exact", requested=slug)
            if hit:
                return hit

    # 2) Correspondance par regex (id ou nom), modèle le plus récent d'abord.
    try:
        rx = re.compile(model_q, re.IGNORECASE)
    except re.error:
        rx = re.compile(re.escape(model_q), re.IGNORECASE)
    candidates: list[tuple[str, str, str, dict]] = []
    for prov_id, mid, m in _models():
        name = m.get("name") or ""
        if rx.search(mid) or rx.search(name):
            cost = m.get("cost") or {}
            if cost.get("input") is not None and cost.get("output") is not None:
                recency = m.get("last_updated") or m.get("release_date") or ""
                candidates.append((recency, prov_id, mid, m))
    if candidates:
        candidates.sort(key=lambda x: x[0], reverse=True)
        _, prov_id, mid, m = candidates[0]
        return _entry(prov_id, mid, m, match="regex", requested=slug)

    # 3) Repli statique (réseau + cache indisponibles).
    fb = _FALLBACK.get(model_q)
    if fb:
        return {
            "provider": provider_hint or "?",
            "model": model_q,
            "requested": slug,
            "match": "fallback-table",
            "input": fb["input"],
            "output": fb["output"],
            "cache_read": None,
            "currency": "USD",
            "source": "fallback",
        }
    return None


def price_for(slug: str, refresh: bool = False) -> dict | None:
    """Comme get_model_pricing, mais retombe sur un Sonnet récent si introuvable."""
    hit = get_model_pricing(slug, refresh=refresh)
    if hit is not None:
        return hit
    if FALLBACK_MODEL and slug != FALLBACK_MODEL:
        fb = get_model_pricing(FALLBACK_MODEL, refresh=refresh)
        if fb is not None:
            return {**fb, "requested": slug, "fallback_used": True, "match": "default-fallback"}
    return None


def list_models(query: str | None = None, refresh: bool = False) -> list[dict]:
    """Liste tous les modèles tarifés du catalogue models.dev.

    Renvoie [{provider, model, name, input, output, release_date}], trié par
    fournisseur puis modèle. `query` filtre (regex insensible à la casse) sur
    l'id, le nom et le fournisseur — vide = catalogue complet.
    """
    catalog = _load_catalog(refresh=refresh)
    out: list[dict] = []
    for prov_id, prov in catalog.items():
        for mid, m in (prov.get("models") or {}).items():
            cost = m.get("cost") or {}
            if cost.get("input") is None or cost.get("output") is None:
                continue
            out.append(
                {
                    "provider": prov_id,
                    "model": mid,
                    "name": m.get("name") or mid,
                    "input": float(cost["input"]),
                    "output": float(cost["output"]),
                    "release_date": m.get("release_date") or m.get("last_updated") or "",
                }
            )
    if query:
        try:
            rx = re.compile(query, re.IGNORECASE)
        except re.error:
            rx = re.compile(re.escape(query), re.IGNORECASE)
        out = [
            m
            for m in out
            if rx.search(m["model"]) or rx.search(m["name"]) or rx.search(m["provider"])
        ]
    out.sort(key=lambda x: (x["provider"], x["model"]))
    return out


def normalize_models(models: str | list[str] | None) -> list[str]:
    """Normalise l'entrée en liste de slugs (accepte str, CSV ou liste)."""
    if not models:
        return []
    if isinstance(models, str):
        return [m.strip() for m in models.split(",") if m.strip()]
    out: list[str] = []
    for m in models:
        if isinstance(m, str) and m.strip():
            out.append(m.strip())
    return out


def estimate_cost(
    input_tokens: int,
    output_tokens: int,
    model: str,
    refresh: bool = False,
) -> dict:
    """Coût estimé (USD) d'une consommation de tokens pour un modèle donné.

    Si le slug est introuvable, retombe sur un Sonnet récent (champ
    `fallback_used`). La correspondance peut être exacte ou par regex (`match`).
    """
    pricing = price_for(model, refresh=refresh)
    if pricing is None:
        return {
            "model": model,
            "currency": "USD",
            "pricing_found": False,
            "input_cost": None,
            "output_cost": None,
            "total_cost": None,
        }
    input_cost = input_tokens / 1_000_000 * pricing["input"]
    output_cost = output_tokens / 1_000_000 * pricing["output"]
    return {
        "requested": pricing.get("requested", model),
        "model": pricing["model"],
        "provider": pricing["provider"],
        "match": pricing.get("match", "exact"),
        "fallback_used": pricing.get("fallback_used", False),
        "currency": pricing["currency"],
        "source": pricing["source"],
        "pricing_found": True,
        "input_price_per_1m": pricing["input"],
        "output_price_per_1m": pricing["output"],
        "input_cost": round(input_cost, 6),
        "output_cost": round(output_cost, 6),
        "total_cost": round(input_cost + output_cost, 6),
    }


def cost_breakdown(
    input_tokens: int,
    output_tokens: int,
    models: str | list[str] | None,
    refresh: bool = False,
) -> dict:
    """Coût par modèle (USD) + total additionné sur tous les modèles fournis.

    Permet de chiffrer un pipeline qui s'appuie sur plusieurs modèles : chaque
    modèle facture la même consommation de tokens, et le coût total est la somme
    des coûts par modèle.
    """
    slugs = normalize_models(models)
    per_model = [estimate_cost(input_tokens, output_tokens, m, refresh=refresh) for m in slugs]

    t_in = sum(c["input_cost"] for c in per_model if c.get("pricing_found"))
    t_out = sum(c["output_cost"] for c in per_model if c.get("pricing_found"))
    return {
        "currency": "USD",
        "models": slugs,
        "per_model": per_model,
        "pricing_found": any(c.get("pricing_found") for c in per_model),
        "total": {
            "input_cost": round(t_in, 6),
            "output_cost": round(t_out, 6),
            "total_cost": round(t_in + t_out, 6),
        },
    }
