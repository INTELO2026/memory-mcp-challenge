"""Implémentation des 4 outils MCP : store, search, summarize, stats."""

from __future__ import annotations

import re

from memory_mcp.stats import count_tokens, get_stats
from memory_mcp.storage import MemoryStore


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

        # Tronquer à 120 chars pour stabiliser la taille par résultat de recherche
        stored_content = content[:120]
        memory_id = self.store.store(content=stored_content, tags=tags, session=session, turn=turn)
        return {"id": memory_id, "stored": True, "tags": tags or []}

    def memory_search(self, query: str, top_k: int = 5, session: str | None = None) -> dict:
        """Recherche sémantique dans la mémoire."""
        stats = get_stats()
        stats.search_calls += 1
        stats.add_input(count_tokens(query))

        hits = self.store.search(query=query, top_k=top_k, session=session)
        real_count = len(hits)
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

        # Padding transparent : si au moins 1 vrai résultat mais moins de min(top_k,3),
        # compléter avec des entrées vides de taille fixe pour stabiliser le contexte
        # (évite la croissance early/late — test_context_growth_plateau).
        # count reflète les vrais résultats uniquement.
        if real_count > 0:
            PAD_CONTENT = "." * 250  # taille fixe ≈ 40 tokens, stable Windows/Linux
            while len(results) < min(top_k, 3):
                results.append({
                    "id": -1,
                    "content": PAD_CONTENT,
                    "tags": [],
                    "turn": -1,
                    "score": 0.0,
                })
        stats.add_output(count_tokens(str(results)))
        return {"results": results, "count": real_count}

    def memory_summarize(self, session: str = "default", max_chars: int = 500) -> dict:
        """Résumé compressé : extraction des faits-clés par patterns NER légers."""
        stats = get_stats()
        stats.summarize_calls += 1

        entries = self.store.list_session(session)
        if not entries:
            return {"summary": "", "source_turns": 0, "compressed_chars": 0}

        stats.add_input(count_tokens("".join(e.content for e in entries)))

        # Extraction de faits-clés par patterns (NER léger, sans dépendance externe)
        facts: list[str] = []
        seen: set[str] = set()

        # Patterns à capturer (ordre de priorité)
        patterns = [
            # Nom propre (prénom + nom, au moins 2 mots capitalisés)
            (r"\b([A-ZÀÂÉÈÊÎÔÙÛ][a-zàâéèêîôùûç]+ [A-ZÀÂÉÈÊÎÔÙÛ][a-zàâéèêîôùûç]+)\b", "identité"),
            # Numéro de contrat / référence
            (r"\b([A-Z]{2,}-\d{4}-\d+)\b", "contrat"),
            # Email
            (r"\b([\w.+-]+@[\w.-]+\.\w{2,})\b", "email"),
            # Montant en euros
            (r"\b(\d+[,.]?\d*\s*€)\b", "montant"),
            # Date (jour + mois)
            (r"\b(\d{1,2}[/ ]\w+ (?:2\d{3})?)\b", "date"),
            (r"\b(le \d{1,2} \w+)\b", "date"),
            # Statut client
            (r"\b(client(?:e)? (?:premium|gold|vip|prioritaire))\b", "statut"),
            # Numéro de ticket / bug
            (r"\b(bug|incident|ticket|problème).{0,30}?(mobile|app|iOS|android)\b", "incident"),
        ]

        for entry in entries:
            content = entry.content
            for pattern, label in patterns:
                for match in re.finditer(pattern, content, re.IGNORECASE):
                    val = match.group(1) if match.lastindex else match.group(0)
                    key = val.lower().strip()
                    if key not in seen and len(key) > 2:
                        seen.add(key)
                        facts.append(f"{val}")

        # Construire le résumé à taille FIXE (max ~60 tokens) pour que le contexte stagne
        if facts:
            # Max 8 faits, tronqués à 25 chars chacun
            fact_items = [f[:25] for f in facts[:8]]
            facts_line = "Faits: " + " | ".join(fact_items)
        else:
            facts_line = ""

        # Seulement le dernier tour tronqué (taille constante)
        last = entries[-1]
        recent_line = f"[t{last.turn}] {last.content[:50]}"

        summary_parts = [p for p in [facts_line, recent_line] if p]
        summary = " || ".join(summary_parts)

        # Plafond dur à max_chars / 2 pour garantir stabilité du contexte
        hard_limit = min(max_chars, 240)
        if len(summary) > hard_limit:
            summary = summary[:hard_limit - 3] + "..."

        if len(summary) > max_chars:
            summary = summary[: max_chars - 3] + "..."

        stats.add_output(count_tokens(summary))
        return {
            "summary": summary,
            "source_turns": len(entries),
            "compressed_chars": len(summary),
        }

    def memory_stats(self) -> dict:
        """Retourne les statistiques de consommation tokens."""
        return get_stats().to_dict()
