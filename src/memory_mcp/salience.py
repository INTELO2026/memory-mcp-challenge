"""Détection de saillance : qu'est-ce qui *mérite* d'être mémorisé et résumé ?

Le cœur de la compression intelligente. Au lieu de tronquer aveuglément, on score chaque
fragment selon la densité de faits durables qu'il contient : identifiants, emails, montants,
dates, références, noms propres, chiffres. Ce score sert à la fois :

- au stockage  → champ ``importance`` (hiérarchie de pertinence) ;
- au résumé    → on garde les fragments les plus saillants, on jette le bruit.

100 % déterministe (aucun LLM) : indispensable pour une CI reproductible et anti-triche.
"""

from __future__ import annotations

import re

# --- Détecteurs de faits durables (génériques, jamais de valeur en dur) ---

_PATTERNS: list[tuple[str, re.Pattern[str], float]] = [
    ("email", re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"), 3.0),
    ("ref", re.compile(r"\b[A-Z]{2,}[-_]?\d[\w-]*\d\b"), 3.0),  # CTR-2024-8847, INV2024...
    ("money", re.compile(r"\b\d+(?:[.,]\d+)?\s?(?:€|euros?|\$|usd|eur)\b", re.I), 2.5),
    ("phone", re.compile(r"\b(?:\+\d{1,3}[\s.]?)?(?:\d{2,4}[\s.-]?){3,5}\b"), 2.0),
    ("percent", re.compile(r"\b\d+(?:[.,]\d+)?\s?%"), 1.5),
    (
        "date",
        re.compile(
            r"\b(\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?|"
            r"\d{1,2}\s+(?:janvier|février|fevrier|mars|avril|mai|juin|juillet|août|aout|"
            r"septembre|octobre|novembre|décembre|decembre))\b",
            re.I,
        ),
        2.0,
    ),
    ("number", re.compile(r"\b\d{3,}\b"), 1.0),
]

# Mots déclencheurs qui signalent une info à retenir (préférences, décisions, contraintes).
_KEYWORD_BOOST = re.compile(
    r"\b(je m'appelle|mon nom|je suis|contrat|facture|commande|référence|reference|"
    r"identifiant|mot de passe|adresse|téléphone|telephone|deadline|échéance|echeance|"
    r"préfère|prefere|important|attention|urgent|bug|erreur|problème|probleme|"
    r"rendez-vous|budget|objectif|client|premium|abonnement|api[\s_-]?key|token)\b",
    re.I,
)

# Nom propre : Mot Capitalisé pas en début de phrase (heuristique légère).
_PROPER_NOUN = re.compile(r"(?<!^)(?<![.!?]\s)\b[A-ZÀ-Ý][a-zà-ÿ]{2,}\b")

_NOISE_HINT = re.compile(r"\b(hors[- ]sujet|bruit|blabla|lorem|météo|meteo)\b", re.I)


def importance_score(text: str) -> float:
    """Score d'importance d'un fragment dans [0, ~1].

    Combine la présence de faits durables, de mots-clés signalétiques et de noms propres,
    pénalise le bruit explicite, puis compresse via une saturation douce.
    """
    if not text or not text.strip():
        return 0.0

    raw = 0.0
    for _label, pattern, weight in _PATTERNS:
        hits = len(pattern.findall(text))
        if hits:
            raw += weight * min(hits, 3)

    raw += 1.5 * len(_KEYWORD_BOOST.findall(text))
    raw += 0.8 * min(len(_PROPER_NOUN.findall(text)), 4)

    if _NOISE_HINT.search(text):
        raw -= 2.5

    # Saturation douce : 0 → 0, +∞ → 1.
    score = 1.0 - 1.0 / (1.0 + max(raw, 0.0) / 3.0)
    return round(score, 4)


def extract_salient_units(text: str) -> list[str]:
    """Extrait les empreintes factuelles d'un texte (pour dédup / vérification de couverture)."""
    units: list[str] = []
    for _label, pattern, _weight in _PATTERNS:
        units.extend(m.group(0) for m in pattern.finditer(text))
    return units


def split_clauses(text: str) -> list[str]:
    """Découpe un fragment en clauses courtes (phrases / segments) pour un résumé plus fin."""
    parts = re.split(r"(?<=[.!?;])\s+|\s+\|\s+|\n+", text.strip())
    return [p.strip() for p in parts if p.strip()]
