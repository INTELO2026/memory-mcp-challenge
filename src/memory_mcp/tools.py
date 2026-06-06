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
        model: str | None = None,
    ) -> dict:
        """Stocke un fragment de mémoire avec métadonnées (session, importance, date).

        `model` (optionnel) : slug du modèle IA de l'agent appelant. Comme les
        outils MCP n'ont pas d'autre canal pour connaître le modèle utilisé,
        l'agent le déclare ici ; il est mémorisé (`active_model`) et sert au
        chiffrage du coût dans `memory_stats` et le tableau de bord.
        """
        stats = get_stats()
        stats.store_calls += 1
        stats.set_model(model)
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
        result_tokens = count_tokens(str(results))
        stats.add_output(result_tokens)
        stats.record_search(query_tokens=count_tokens(query), result_tokens=result_tokens)
        return {"results": results, "count": len(results)}

    def memory_summarize(self, session: str = "default", max_chars: int = 400) -> dict:
        """Résumé extractif qui conserve TOUS les faits porteurs d'information.

        Stratégie déterministe (hors-ligne, sans LLM) :
        - écarte le bruit conversationnel (densité d'information ~0) ;
        - conserve un maximum d'entrées factuelles, priorisées par densité
          puis récence, dans la limite du budget `max_chars` ;
        - garantit la présence de la dernière entrée factuelle (contexte
          récent), pas d'une entrée de bruit ;
        - déduplique et restitue les faits dans l'ordre chronologique, sans
          jamais couper un fait au milieu d'un mot.
        """
        stats = get_stats()
        stats.summarize_calls += 1

        entries = self.store.list_session(session)
        if not entries:
            return {"summary": "", "source_turns": 0, "compressed_chars": 0}

        total_chars = sum(len(e.content) for e in entries)
        turn_range = f"{entries[0].turn}-{entries[-1].turn}"
        header = f"[S:{session} E:{len(entries)} R:{turn_range} C:{total_chars}]"

        # 1) Densité d'information par entrée : le bruit retombe vers 0.
        scored = [(e, _information_density(e.content)) for e in entries]
        facts = [(e, d) for e, d in scored if d >= _NOISE_FLOOR]
        # Repli : si rien ne dépasse le seuil (session sans entités),
        # garder les entrées les mieux notées pour ne pas renvoyer un vide.
        if not facts:
            facts = sorted(scored, key=lambda x: x[1], reverse=True)[:3]

        # 2) Dernière entrée factuelle = contexte récent garanti.
        last_fact = max(facts, key=lambda x: x[0].turn)[0]

        # 3) Sélection par priorité (densité, puis récence) dans le budget.
        budget = max_chars - len(header) - 3
        ordered = sorted(facts, key=lambda x: (x[1], x[0].turn), reverse=True)
        candidates = [last_fact] + [e for e, _ in ordered if e.id != last_fact.id]

        selected: dict[int, MemoryEntry] = {}
        used = 0
        for e in candidates:
            if e.id in selected:
                continue
            cost = len(_clip(e.content)) + 12  # snippet + préfixe [tN] + séparateur
            if used + cost > budget and selected:
                break
            selected[e.id] = e
            used += cost

        # 4) Restitution chronologique des faits retenus.
        lines = [
            f"[t{e.turn}] {_clip(e.content)}"
            for e in sorted(selected.values(), key=lambda e: e.turn)
        ]
        summary = " | ".join([header, *lines])
        if len(summary) > max_chars:
            summary = summary[: max_chars - 1].rstrip() + "…"

        stats.add_input(count_tokens("".join(e.content for e in entries)))
        summary_tokens = count_tokens(summary)
        stats.add_output(summary_tokens)
        stats.record_summarize(summary_tokens=summary_tokens)
        return {
            "summary": summary,
            "source_turns": len(entries),
            "compressed_chars": len(summary),
        }

    def memory_stats(self, model: str | list[str] | None = None) -> dict:
        """Retourne les statistiques de consommation tokens.

        `model` accepte un slug models.dev (`claude-opus-4-8`,
        `anthropic/claude-sonnet-4-6`), une regex, une liste de slugs, ou une
        chaîne séparée par des virgules. Quand plusieurs modèles sont fournis, le
        coût est détaillé par modèle puis additionné (champ `cost.total`), en USD
        via models.dev. Slug introuvable → repli sur un Sonnet récent.
        """
        stats = get_stats().to_dict()
        # À défaut de modèle explicite, on chiffre avec celui déclaré par
        # l'agent (active_model) si disponible.
        effective = model or stats.get("active_model")
        if effective:
            from memory_mcp.pricing import cost_breakdown, normalize_models

            stats["models"] = normalize_models(effective)
            stats["cost"] = cost_breakdown(
                input_tokens=stats["input_tokens"],
                output_tokens=stats["output_tokens"],
                models=effective,
            )
        return stats


# Seuil en-dessous duquel une entrée est considérée comme du bruit
# conversationnel et exclue du résumé.
_NOISE_FLOOR = 0.2


def _clip(text: str, limit: int = 110) -> str:
    """Tronque sans couper un mot au milieu (préserve le fait lisible)."""
    text = text.strip()
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0] or text[:limit]
    return cut + "…"


def _information_density(text: str) -> float:
    """Mesure la densité d'information.
    Un texte avec entités (codes, emails, montants, noms, dates) a une
    densité plus élevée qu'un texte de bruit / conversationnel.
    """
    score = 0.0
    if re.search(r"\b[A-Za-z]{2,5}-\d{4}-\d{3,}\b", text):
        score += 0.8
    if re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", text):
        score += 0.9
    if re.search(r"\d+[.,]\d{2}\s*[€$£]", text):
        score += 0.7
    # Date numérique (12/03/2024) OU textuelle française (12 février)
    if re.search(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b", text):
        score += 0.5
    if re.search(
        r"\b\d{1,2}\s+(janvier|février|mars|avril|mai|juin|"
        r"juillet|août|septembre|octobre|novembre|décembre)\b",
        text, re.IGNORECASE,
    ):
        score += 0.5
    if re.search(r"\b[A-Z][a-zéèêëàâîïôùû]{2,}\s+[A-Z][a-zéèêëàâîïôùû]{2,}\b", text):
        score += 0.6
    long_words = sum(1 for w in re.findall(r"\w{9,}", text))
    score += min(long_words * 0.1, 0.5)
    if "hors-sujet" in text.lower():
        score -= 0.7
    return max(0.0, min(score, 2.0))
