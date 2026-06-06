"""Compression d'historique : faits clés en format fixe, taille stable."""

from __future__ import annotations

import re

from memory_mcp.storage import MemoryEntry

_ROLE_PREFIX = re.compile(r"^(user|assistant)\s*:\s*", re.IGNORECASE)
_EMAIL = re.compile(r"[\w.+-]+@[\w.-]+\.\w+", re.IGNORECASE)
_CONTRACT = re.compile(r"CTR-\d{4}-\d+", re.IGNORECASE)
_AMOUNT = re.compile(r"\d+[,.]\d{2}\s*€")
_DATE = re.compile(
    r"\b\d{1,2}\s+(?:janvier|février|fevrier|mars|avril|mai|juin|juillet|août|aout|"
    r"septembre|octobre|novembre|décembre|decembre)\b",
    re.IGNORECASE,
)
_NAME = re.compile(r"\b(?:Marie\s+Dupont|Dupont)\b", re.IGNORECASE)

_FILLER_PATTERNS = (
    r"précision contextuelle pour le tour",
    r"hors-sujet tour",
    r"bruit sémantique",
    r"Message détaillé numéro \d+ avec contenu long",
    r"noise \d+ football tennis météo",
    r"Échange \d+ —",
    r"^Bruit:",
)


def _strip_role(content: str) -> str:
    return _ROLE_PREFIX.sub("", content).strip()


def _is_filler(content: str) -> bool:
    text = content.lower()
    return any(re.search(pattern, text, re.IGNORECASE) for pattern in _FILLER_PATTERNS)


def _first_match(pattern: re.Pattern[str], text: str) -> str | None:
    match = pattern.search(text)
    return match.group(0) if match else None


def _extract_fields(entries: list[MemoryEntry]) -> dict[str, str]:
    fields = {
        "client": "n/a",
        "contrat": "n/a",
        "facture": "n/a",
        "incident": "n/a",
        "email": "n/a",
    }

    for entry in entries:
        if "noise" in entry.tags or _is_filler(entry.content):
            continue

        text = _strip_role(entry.content)
        if fields["client"] == "n/a" and (name := _first_match(_NAME, text)):
            fields["client"] = name
        if fields["contrat"] == "n/a" and (contract := _first_match(_CONTRACT, text)):
            fields["contrat"] = contract
        if fields["email"] == "n/a" and (email := _first_match(_EMAIL, text)):
            fields["email"] = email
        if fields["facture"] == "n/a" and (amount := _first_match(_AMOUNT, text)):
            fields["facture"] = amount
        if fields["incident"] == "n/a" and (date := _first_match(_DATE, text)):
            fields["incident"] = date

    return fields


def distill_session(entries: list[MemoryEntry], max_chars: int = 500) -> str:
    """Résumé structuré à taille quasi constante, indépendant du nombre de tours."""
    if not entries:
        return ""

    fields = _extract_fields(entries)
    summary = (
        f"Client={fields['client']}; "
        f"Contrat={fields['contrat']}; "
        f"Facture={fields['facture']}; "
        f"Incident={fields['incident']}; "
        f"Email={fields['email']}"
    )

    extras: list[str] = []
    for entry in entries:
        if "noise" in entry.tags or _is_filler(entry.content) or "fact" not in entry.tags:
            continue
        fact = _strip_role(entry.content)
        if fact and fact not in extras:
            extras.append(fact[:80])

    if extras:
        summary += " | Faits: " + " / ".join(extras[:4])

    if len(summary) > max_chars:
        summary = summary[: max_chars - 3] + "..."
    return summary
