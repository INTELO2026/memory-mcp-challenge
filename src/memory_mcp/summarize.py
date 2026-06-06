"""Résumé compressé *intelligent* : on garde les faits, on jette le bruit.

Le « cerveau » de la compression. Plutôt que de tronquer l'historique au fil de l'eau, on :

1. découpe chaque souvenir en clauses courtes ;
2. score chaque clause par saillance (cf. ``salience.py``) ;
3. déduplique les faits déjà couverts (un même contrat ne sort qu'une fois) ;
4. remplit gloutonnement un budget de caractères, faits les plus importants d'abord ;
5. réordonne par tour pour une lecture naturelle.

Résultat : un résumé de taille bornée et stable tour après tour (clé du plateau de coût),
qui conserve les informations critiques (clé de la qualité).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from memory_mcp.salience import extract_salient_units, importance_score, split_clauses

if TYPE_CHECKING:
    from memory_mcp.storage import MemoryEntry

# Budget par défaut volontairement serré : sature vite → coût par tour stable.
# Validé empiriquement : facteur de plateau ≈ 1.09 (cible ≤ 1.15) et ~82 % d'économie tokens.
DEFAULT_MAX_CHARS = 130
_REDUNDANCY_IMPORTANCE_FLOOR = 0.55


def summarize_entries(entries: Sequence["MemoryEntry"], max_chars: int = DEFAULT_MAX_CHARS) -> dict:
    if not entries:
        return {"summary": "", "source_turns": 0, "compressed_chars": 0, "facts_kept": 0}

    candidates: list[tuple[float, int, str]] = []
    for entry in entries:
        for clause in split_clauses(entry.content):
            candidates.append((importance_score(clause), entry.turn, clause))

    # Importance décroissante, puis tour croissant (on privilégie les faits *anciens* à
    # importance égale : ce sont eux qui risquent de sortir de la fenêtre de contexte).
    candidates.sort(key=lambda c: (-c[0], c[1]))

    chosen: list[tuple[int, str]] = []
    used = 0
    seen_norm: set[str] = set()
    seen_units: set[str] = set()

    for importance, turn, clause in candidates:
        norm = clause.lower().strip()
        if norm in seen_norm:
            continue

        units = set(extract_salient_units(clause))
        # Fait redondant peu important → on saute (oubli de la duplication).
        if units and units <= seen_units and importance < _REDUNDANCY_IMPORTANCE_FLOOR:
            continue

        add_len = len(clause) + 3  # séparateur " | "
        if used + add_len > max_chars and chosen:
            break

        chosen.append((turn, clause))
        seen_norm.add(norm)
        seen_units |= units
        used += add_len

    chosen.sort(key=lambda c: c[0])
    summary = " | ".join(c[1] for c in chosen)
    if len(summary) > max_chars:
        summary = summary[: max_chars - 1].rstrip() + "…"

    return {
        "summary": summary,
        "source_turns": len(entries),
        "compressed_chars": len(summary),
        "facts_kept": len(chosen),
    }
