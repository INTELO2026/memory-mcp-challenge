"""Implémentation des 4 outils MCP : store, search, summarize, stats."""

from __future__ import annotations

import re

from memory_mcp.stats import count_tokens, get_stats
from memory_mcp.storage import MemoryEntry, MemoryStore

# Budget de tokens du résumé : petit et FIXE pour garantir compression + plateau.
SUMMARY_TOKEN_BUDGET = 40
# Longueur max d'un fragment de fait retenu (caractères).
FACT_SNIPPET_CHARS = 90

# Détection d'entités « factuelles » : codes, emails, montants, dates, noms propres.
_ENTITY_PATTERNS = [
    re.compile(r"\b[A-Z]{2,}[-_]?\d[\w-]*\b"),  # CTR-2024-8847, REF12...
    re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"),  # emails
    re.compile(r"\b\d+[.,]\d+\s*(?:€|eur|euros?)?\b", re.I),  # montants 149,90 €
    re.compile(
        r"\b\d{1,2}\s+(?:janvier|février|fevrier|mars|avril|mai|juin|juillet|"
        r"août|aout|septembre|octobre|novembre|décembre|decembre)\b",
        re.I,
    ),  # dates "12 février"
    re.compile(r"\b[A-ZÀ-Ÿ][a-zà-ÿ]+\s+[A-ZÀ-Ÿ][a-zà-ÿ]+\b"),  # Noms propres "Marie Dupont"
]

_NOISE_TAGS = frozenset({"noise"})


def _has_entity(text: str) -> bool:
    return any(p.search(text) for p in _ENTITY_PATTERNS)


def _fact_priority(entry: MemoryEntry) -> int:
    """Plus petit = plus prioritaire dans le résumé."""
    tags = {t.lower() for t in entry.tags}
    if "fact" in tags:
        return 0
    if _has_entity(entry.content):
        return 1
    return 2


# Préfixe de rôle conversationnel en tête de fragment ("user:", "assistant:", ...).
_ROLE_PREFIX = re.compile(r"^\s*(?:user|assistant|système|systeme|system)\s*:\s*", re.I)


def strip_role(text: str) -> str:
    """Retire le préfixe de rôle non informatif (densification du contexte)."""
    return _ROLE_PREFIX.sub("", text.strip())


def _snippet(content: str) -> str:
    # Résumé dense : on retire le préfixe de rôle (non informatif) et on normalise.
    snippet = _ROLE_PREFIX.sub("", " ".join(content.split()))
    if len(snippet) > FACT_SNIPPET_CHARS:
        snippet = snippet[: FACT_SNIPPET_CHARS - 1].rstrip() + "…"
    return snippet


def _select_facts(entries: list[MemoryEntry]) -> list[MemoryEntry]:
    """Sélectionne les entrées informatives (faits + entités), bruit exclu."""
    candidates = [e for e in entries if not ({t.lower() for t in e.tags} & _NOISE_TAGS)]
    # Tri par priorité (fait > entité > autre), puis ordre chronologique (turn, id).
    candidates.sort(key=lambda e: (_fact_priority(e), e.turn, e.id))
    return candidates


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

    def memory_search(self, query: str, top_k: int = 5, session: str | None = None) -> dict:
        """Recherche sémantique dans la mémoire."""
        stats = get_stats()
        stats.search_calls += 1
        stats.add_input(count_tokens(query))

        hits = self.store.search(query=query, top_k=top_k, session=session)
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

    def memory_summarize(self, session: str = "default", max_chars: int = 500) -> dict:
        """Résumé compressé à budget de tokens fixe, conservant les faits clés.

        Stratégie déterministe (sans réseau) : on garde les fragments porteurs de
        faits/entités, ordonnés par importance puis chronologie, jusqu'à un budget
        de tokens fixe. Le bruit est écarté. Cela garantit à la fois une forte
        compression et un coût par tour stable (plateau).
        """
        stats = get_stats()
        stats.summarize_calls += 1

        entries = self.store.list_session(session)
        if not entries:
            return {"summary": "", "source_turns": 0, "compressed_chars": 0}

        selected = _select_facts(entries)

        parts: list[str] = []
        used_tokens = 0
        for entry in selected:
            fragment = _snippet(entry.content)
            frag_tokens = count_tokens(fragment)
            if parts and used_tokens + frag_tokens > SUMMARY_TOKEN_BUDGET:
                break
            parts.append(fragment)
            used_tokens += frag_tokens

        summary = " | ".join(parts)
        if len(summary) > max_chars:
            summary = summary[: max_chars - 1].rstrip() + "…"

        stats.add_input(count_tokens("".join(e.content for e in entries)))
        stats.add_output(count_tokens(summary))
        return {
            "summary": summary,
            "source_turns": len(entries),
            "compressed_chars": len(summary),
        }

    def memory_stats(self) -> dict:
        """Retourne les statistiques de consommation tokens."""
        return get_stats().to_dict()
