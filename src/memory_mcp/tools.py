"""Implémentation des 4 outils MCP : store, search, summarize, stats."""

from __future__ import annotations

import re

from memory_mcp.stats import count_tokens, get_stats
from memory_mcp.storage import MemoryEntry, MemoryStore

# Motifs d'entités génériques (aucune valeur métier codée en dur) : repèrent les
# fragments porteurs de faits à préserver lors de la compression.
_ENTITY_PATTERNS = (
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"), 3.0),  # emails
    (re.compile(r"\b[A-Z]{2,}[-_]?\d[\w-]*\b"), 3.0),  # références (CTR-2024-8847)
    (re.compile(r"\d+[.,]\d{2}\s*€|\b\d+\s*€"), 2.0),  # montants
    (re.compile(r"\b\d{1,2}[/\s]\w+|\b\d{1,2}[/-]\d{1,2}"), 2.0),  # dates
    # noms propres : deux mots capitalisés consécutifs
    (re.compile(r"\b[A-ZÀ-Ý][a-zà-ÿ]+\s+[A-ZÀ-Ý][a-zà-ÿ]+"), 1.5),
)


def _importance(entry: MemoryEntry) -> float:
    """Score d'importance d'un fragment : densité d'entités + tag + récence.

    Purement structurel et générique — ne dépend d'aucune réponse attendue.
    """
    content = entry.content
    score = 0.0
    for pattern, weight in _ENTITY_PATTERNS:
        score += weight * len(pattern.findall(content))
    if "fact" in entry.tags:
        score += 1.0
    # Léger bonus de récence pour départager à importance entité égale.
    score += min(entry.turn, 1000) * 1e-4
    return score


class MemoryTools:
    def __init__(self, store: MemoryStore | None = None) -> None:
        self.store = store or MemoryStore()

    def memory_store(
        self, content: str, tags: list[str] | None = None, session: str = "default", turn: int = 0
    ) -> dict:
        """Stocke un fragment de mémoire avec tags optionnels."""
        stats = get_stats()
        stats.store_calls += 1
        stats.add_input(count_tokens(content))

        memory_id = self.store.store(content=content, tags=tags, session=session, turn=turn)
        return {"id": memory_id, "stored": True, "tags": tags or []}

    def memory_search(
        self,
        query: str,
        top_k: int = 5,
        session: str | None = None,
        *,
        shared_session: str | None = None,
        recency_weight: float = 0.0,
        frequency_weight: float = 0.0,
    ) -> dict:
        """Recherche sémantique dans la mémoire.

        Options bonus (§10) : ``shared_session`` pour une mémoire partagée entre
        agents, ``recency_weight``/``frequency_weight`` pour une hiérarchie de
        pertinence (récence + fréquence d'accès). Inactives par défaut.
        """
        stats = get_stats()
        stats.search_calls += 1
        stats.add_input(count_tokens(query))

        hits = self.store.search(
            query=query,
            top_k=top_k,
            session=session,
            shared_session=shared_session,
            recency_weight=recency_weight,
            frequency_weight=frequency_weight,
        )
        results = [
            {
                "id": h.id,
                "content": h.content,
                "tags": h.tags,
                "turn": h.turn,
                "score": round(h.score, 6),
            }
            for h in hits
        ]
        stats.add_output(count_tokens(str(results)))
        return {"results": results, "count": len(results)}

    def memory_summarize(self, session: str = "default", max_chars: int = 180) -> dict:
        """Résumé compressé d'une session, borné par budget de caractères.

        Extrait les fragments les plus porteurs de faits (entités), déduplique,
        et plafonne la sortie : le contexte reste stable même quand l'historique
        enfle, ce qui est la clé de l'économie de tokens.
        """
        stats = get_stats()
        stats.summarize_calls += 1

        entries = self.store.list_session(session)
        if not entries:
            return {"summary": "", "source_turns": 0, "compressed_chars": 0}

        # Trie par importance décroissante (les faits clés d'abord), en gardant
        # une trace de l'ordre chronologique pour la restitution.
        ranked = sorted(entries, key=_importance, reverse=True)

        selected: list[MemoryEntry] = []
        seen: set[str] = set()
        used = 0
        for entry in ranked:
            snippet = entry.content.strip()
            key = re.sub(r"\s+", " ", snippet.lower())
            if key in seen:  # déduplication exacte
                continue
            piece = f"[t{entry.turn}] {snippet}"
            cost = len(piece) + 3  # séparateur " | "
            if used + cost > max_chars and selected:
                break
            selected.append(entry)
            seen.add(key)
            used += cost

        # Restitue dans l'ordre chronologique pour la lisibilité.
        selected.sort(key=lambda e: (e.turn, e.id))
        summary = " | ".join(f"[t{e.turn}] {e.content.strip()}" for e in selected)
        if len(summary) > max_chars:
            summary = summary[: max_chars - 3] + "..."

        stats.add_input(count_tokens("".join(e.content for e in entries)))
        stats.add_output(count_tokens(summary))
        return {
            "summary": summary,
            "source_turns": len(entries),
            "compressed_chars": len(summary),
        }

    def memory_forget(self, session: str = "default", threshold: float = 0.97) -> dict:
        """Oubli intelligent (§10) : purge les souvenirs redondants d'une session."""
        before = self.store.count()
        forgotten = self.store.prune_redundant(session=session, threshold=threshold)
        return {"forgotten": forgotten, "remaining": before - forgotten, "session": session}

    def memory_stats(self) -> dict:
        """Retourne les statistiques de consommation tokens."""
        return get_stats().to_dict()
