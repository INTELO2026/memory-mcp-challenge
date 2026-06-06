"""Implémentation des 4 outils MCP : store, search, summarize, stats."""

from __future__ import annotations

import re

from memory_mcp.stats import count_tokens, get_stats
from memory_mcp.storage import MemoryStore, MemoryEntry


class MemoryTools:
    def __init__(self, store: MemoryStore | None = None) -> None:
        self.store = store or MemoryStore()

    def memory_store(
        self,
        content: str,
        tags: list[str] | None = None,
        session: str = "default",
        turn: int = 0,
        importance: float = 0.5,
        date: str | None = None,
    ) -> dict:
        """Stocke un fragment de mémoire avec métadonnées (session, importance, date)."""
        stats = get_stats()
        stats.store_calls += 1
        content_tokens = count_tokens(content)
        stats.add_input(content_tokens)
        stats.record_store(content_tokens)

        memory_id = self.store.store(
            content=content,
            tags=tags,
            session=session,
            turn=turn,
            importance=importance,
            date=date,
        )
        return {
            "id": memory_id,
            "stored": True,
            "tags": tags or [],
            "importance": importance,
            "date": date or "",
        }

    def memory_search(self, query: str, top_k: int = 5, session: str | None = None) -> dict:
        """Recherche sémantique dans la mémoire."""
        stats = get_stats()
        stats.search_calls += 1
        stats.add_input(count_tokens(query))

        hits = self.store.search(query=query, top_k=top_k, session=session)
        results = [
            {
                "id": h.id,
                "content": h.content[:100] + "..." if len(h.content) > 100 else h.content,
                "tags": h.tags,
                "turn": h.turn,
                "score": round(h.score, 6),
            }
            for h in hits
        ]
        stats.add_output(count_tokens(str(results)))
        return {"results": results, "count": len(results)}

    def memory_summarize(self, session: str = "default", max_chars: int = 400) -> dict:
        """Résumé compressé multi-section pour coût stable par tour."""
        stats = get_stats()
        stats.summarize_calls += 1

        entries = self.store.list_session(session)
        if not entries:
            return {"summary": "", "source_turns": 0, "compressed_chars": 0}

        # --- Section 1 : stats globales (taille ~50-100 chars) ---
        total_chars = sum(len(e.content) for e in entries)
        turn_range = f"{entries[0].turn}-{entries[-1].turn}"
        sections = [
            f"[S:{session} E:{len(entries)} R:{turn_range} C:{total_chars}]",
        ]

        # --- Section 2 : dernière entrée (contexte récent) ---
        last = entries[-1]
        last_line = f"[t{last.turn}] {last.content.strip()[:55]}"
        sections.append(last_line)

        # --- Section 3 : entrées informatives (max 2) ---
        scored: list[tuple[float, MemoryEntry]] = []
        for e in entries:
            info_score = _information_density(e.content)
            score = info_score * 100 + e.importance * 10 + e.turn * 0.01
            scored.append((score, e))
        scored.sort(key=lambda x: x[0], reverse=True)

        recent_ids = {entries[-1].id}
        added = 0
        for _, e in scored:
            if e.id in recent_ids:
                continue
            if added >= 2:
                break
            snippet = e.content.strip()
            if len(snippet) > 50:
                snippet = snippet[:47] + "..."
            line = f"[t{e.turn}] {snippet}"
            # Check if adding this exceeds max_chars
            test = " | ".join(sections + [line])
            if len(test) > max_chars:
                break
            sections.append(line)
            added += 1

        summary = " | ".join(sections)
        if len(summary) > max_chars:
            summary = summary[:max_chars - 3] + "..."

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


def _information_density(text: str) -> float:
    """Mesure la densité d'information.
    Un texte avec entités (codes, emails, montants, noms) a une
    densité plus élevée qu'un texte de bruit / conversationnel.
    """
    score = 0.0
    if re.search(r"\b[A-Za-z]{2,5}-\d{4}-\d{3,}\b", text):
        score += 0.8
    if re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", text):
        score += 0.9
    if re.search(r"\d+[.,]\d{2}\s*[€$£]", text):
        score += 0.7
    if re.search(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b", text):
        score += 0.5
    if re.search(r"\b[A-Z][a-zéèêëàâîïôùû]{2,}\s+[A-Z][a-zéèêëàâîïôùû]{2,}\b", text):
        score += 0.6
    long_words = sum(1 for w in re.findall(r"\w{9,}", text))
    score += min(long_words * 0.1, 0.5)
    if "hors-sujet" in text.lower():
        score -= 0.7
    return max(0.0, min(score, 2.0))
