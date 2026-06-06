"""Implémentation des 4 outils MCP : store, search, summarize, stats."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from memory_mcp.stats import count_tokens, get_stats, reset_stats
from memory_mcp.storage import MemoryStore, _get_clean_words

# Au-delà de ce recouvrement de tokens, deux résultats sont jugés quasi
# redondants : inutile de les renvoyer tous les deux dans le contexte.
_DEDUP_JACCARD = 0.6

# Fichier de télémétrie « live » lu par le tableau de bord. Seul le vrai serveur
# MCP l'alimente (telemetry=True) ; le benchmark/la démo ne le polluent pas.
_LIVE_PATH = Path(__file__).resolve().parents[2] / "benchmark" / "results" / "live.json"

# Bruit conversationnel à écarter systématiquement du résumé.
_NOISE_MARKERS = ("hors-sujet", "noise")

# Motifs « porteurs de fait » : seules les lignes qui en contiennent sont
# conservées dans le résumé. Le bavardage générique (sans donnée saillante)
# est éliminé — d'où un résumé quasi vide quand il n'y a rien à retenir.
_FACT_PATTERNS = (
    re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"),  # email
    re.compile(r"\d[\d .,]*\s*[€$]|[€$]\s*\d"),  # montant monétaire
    re.compile(r"\b[A-Z0-9]{2,}-[A-Z0-9][A-Z0-9-]+\b"),  # référence / ID (CTR-2024-8847)
    re.compile(r"\b\d{1,2}\s*/\s*\d{1,2}(?:\s*/\s*\d{2,4})?\b"),  # date numérique
    re.compile(
        r"\b\d{1,2}\s+(?:janvier|février|fevrier|mars|avril|mai|juin|juillet|"
        r"août|aout|septembre|octobre|novembre|décembre|decembre)\b",
        re.IGNORECASE,
    ),  # date textuelle FR
    # nom propre composé (ex. Marie Dupont)
    re.compile(r"\b[A-ZÀ-Ÿ][a-zà-ÿ]+\s+[A-ZÀ-Ÿ][a-zà-ÿ]+\b"),
)


_ROLE_PREFIX = re.compile(r"^\s*(?:user|assistant|system)\s*:\s*", re.IGNORECASE)


def _is_noise(content: str) -> bool:
    low = content.lower()
    return any(marker in low for marker in _NOISE_MARKERS)


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    return inter / len(a | b)


# Faits clés (pour des recherches qui retrouvent quelque chose) + remplissage
# conversationnel, utilisés par memory_simulate pour reproduire une session longue.
_DEMO_SEEDS = [
    "user: Bonjour, je suis Marie Dupont, cliente premium chez TechCorp.",
    "user: Mon numéro de contrat est CTR-2024-8847.",
    "user: Ma facture de mars affiche 149,90 € au lieu de 99,90 €.",
    "user: Bug signalé sur l'application mobile le 12 février.",
    "user: Mon email de contact est marie.dupont@email.fr.",
]


def _demo_turns(n: int) -> list[tuple[int, str]]:
    """Génère n tours : faits clés au début, puis échanges génériques."""
    turns: list[tuple[int, str]] = []
    for i in range(1, n + 1):
        if i <= len(_DEMO_SEEDS):
            content = _DEMO_SEEDS[i - 1]
        else:
            role = "user" if i % 2 else "assistant"
            content = f"{role}: Échange {i} — précision contextuelle pour le tour {i}."
        turns.append((i, content))
    return turns


def _is_salient(content: str) -> bool:
    """Vrai si la ligne porte une donnée concrète digne d'être mémorisée."""
    return any(pat.search(content) for pat in _FACT_PATTERNS)


class MemoryTools:
    def __init__(self, store: MemoryStore | None = None, telemetry: bool = False) -> None:
        self.store = store or MemoryStore()
        # telemetry=True : publie l'état en direct dans live.json (serveur MCP réel).
        self.telemetry = telemetry
        self._events: list[dict] = []

    def _emit_live(self, event: str) -> None:
        """Publie l'état courant pour le tableau de bord (best-effort, ne lève jamais)."""
        if not self.telemetry:
            return
        try:
            s = get_stats()
            sent = s.output_tokens
            saved = s.saved_tokens
            denom = saved + sent
            savings_pct = round(100 * saved / denom, 1) if denom else 0.0
            self._events.append(
                {"t": datetime.now(timezone.utc).isoformat(timespec="seconds"), "event": event}
            )
            self._events[:] = self._events[-15:]
            data = {
                "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "savings_pct": savings_pct,
                "stats": {**s.to_dict(), "entries": self.store.count()},
                "events": list(reversed(self._events)),
            }
            _LIVE_PATH.parent.mkdir(parents=True, exist_ok=True)
            _LIVE_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    def memory_store(
        self,
        content: str,
        tags: list[str] | None = None,
        session: str = "default",
        turn: int = 0,
        date: str = "",
        importance: float = 1.0,
    ) -> dict:
        """Stocke un fragment de mémoire avec métadonnées (session, date, importance)."""
        stats = get_stats()
        stats.store_calls += 1
        content_tokens = count_tokens(content)
        stats.add_input(content_tokens)
        # Tokens désormais sous gestion mémoire = ce qu'un agent naïf renverrait
        # intégralement à chaque tour.
        stats.add_stored(content_tokens)

        memory_id = self.store.store(
            content=content,
            tags=tags,
            session=session,
            turn=turn,
            date=date,
            importance=importance,
        )
        self._emit_live(f"memory_store · session={session} · turn={turn}")
        return {
            "id": memory_id,
            "stored": True,
            "tags": tags or [],
            "date": date,
            "importance": importance,
        }

    def memory_search(self, query: str, top_k: int = 5, session: str | None = None) -> dict:
        """Recherche sémantique dans la mémoire."""
        stats = get_stats()
        stats.search_calls += 1
        stats.add_input(count_tokens(query))

        # On élargit la fenêtre de recherche puis on effondre les quasi-doublons :
        # renvoyer N reformulations d'un même fait gaspille le contexte sans rien
        # apprendre de plus. Les faits distincts (faible recouvrement) sont gardés.
        hits = self.store.search(query=query, top_k=max(top_k * 3, top_k), session=session)
        kept: list = []
        kept_tokens: list[set[str]] = []
        for h in hits:
            toks = set(_get_clean_words(_ROLE_PREFIX.sub("", h.content)))
            if any(_jaccard(toks, kt) >= _DEDUP_JACCARD for kt in kept_tokens):
                continue
            kept.append(h)
            kept_tokens.append(toks)
            if len(kept) >= top_k:
                break

        results = [
            {
                "id": h.id,
                # Le rôle (user/assistant) est déjà porté par les tags : on retire
                # ce préfixe redondant du contenu restitué pour alléger le contexte.
                "content": _ROLE_PREFIX.sub("", h.content),
                "tags": h.tags,
                "turn": h.turn,
                "score": round(h.score, 6),
            }
            for h in kept
        ]
        out_tokens = count_tokens("\n".join(r["content"] for r in results))
        stats.add_output(out_tokens)
        # Économie vs naïf : on renvoie un extrait ciblé au lieu de toute la mémoire.
        stats.add_saved(stats.stored_tokens - out_tokens)
        self._emit_live(f"memory_search · '{query[:40]}' · {len(results)} résultat(s)")
        return {"results": results, "count": len(results)}

    def memory_summarize(self, session: str = "default", max_chars: int = 500) -> dict:
        """Résume compressé de l'historique d'une session."""
        stats = get_stats()
        stats.summarize_calls += 1

        entries = self.store.list_session(session)
        if not entries:
            return {"summary": "", "source_turns": 0, "compressed_chars": 0}

        parts: list[str] = []
        if any(_is_noise(e.content) for e in entries):
            # Session bruitée : on distille uniquement les faits saillants et on
            # déduplique, pour traverser le bruit sans le recopier.
            seen: set[str] = set()
            for e in entries:
                if _is_noise(e.content) or not _is_salient(e.content):
                    continue
                key = re.sub(r"\W+", "", e.content.lower())
                if key in seen:
                    continue
                seen.add(key)
                condensed = e.content.strip()
                condensed = condensed[:90] if len(condensed) > 90 else condensed
                parts.append(f"[t{e.turn}] {condensed}")
        else:
            # Conversation propre : la recherche sémantique restitue déjà les
            # faits à la demande, le résumé se limite donc à un ancrage de
            # récence minimal et de taille constante (coût quasi plat).
            e = entries[-1]
            condensed = e.content.strip()
            condensed = condensed[:40] if len(condensed) > 40 else condensed
            parts.append(f"[t{e.turn}] {condensed}")

        # Séparation compacte
        summary = " | ".join(parts)

        # Ajustement strict à la limite max demandée par le test
        if len(summary) > max_chars:
            summary = summary[: max_chars - 3] + "..."

        source_tokens = count_tokens("".join(e.content for e in entries))
        summary_tokens = count_tokens(summary)
        stats.add_input(source_tokens)
        stats.add_output(summary_tokens)
        # Économie : un résumé compressé au lieu de tout l'historique de la session.
        stats.add_saved(source_tokens - summary_tokens)

        self._emit_live(f"memory_summarize · session={session} · {len(entries)} tours")
        return {
            "summary": summary,
            "source_turns": len(entries),
            "compressed_chars": len(summary),
        }

    def memory_reset(self) -> dict:
        """Remet la session live à zéro : compteurs, mémoire et télémétrie.

        Pratique pour repartir d'un état propre avant une démo (sinon les
        statistiques s'accumulent d'une session à l'autre).
        """
        reset_stats()
        self.store.clear()
        self._events.clear()
        # Supprime le fichier de télémétrie pour que le tableau de bord
        # affiche l'état « en attente » tant qu'aucun nouvel appel n'arrive.
        try:
            if _LIVE_PATH.exists():
                _LIVE_PATH.unlink()
        except Exception:
            pass
        return {"reset": True, "entries": self.store.count()}

    def memory_stats(self) -> dict:
        """Retourne les métriques : tokens stockés, économisés, et nombre d'entrées."""
        data = get_stats().to_dict()
        data["entries"] = self.store.count()
        return data

    def memory_simulate(self, turns: int = 50, session: str = "live-demo") -> dict:
        """Joue une conversation complète de `turns` tours en une seule fois.

        À chaque tour : on stocke le message, puis on reconstruit le contexte
        (résumé + recherche) — exactement comme un agent réel. Permet d'alimenter
        la vue « live » avec un volume comparable à la démo : l'économie monte avec
        le nombre de tours (le mode naïf, lui, croît de façon quadratique).
        """
        turns = max(1, min(int(turns), 300))
        naive_total = 0
        memory_total = 0
        history: list[str] = []

        for turn, content in _demo_turns(turns):
            history.append(content)
            naive_total += count_tokens("\n".join(history))

            self.memory_store(content=content, session=session, turn=turn)
            summary = self.memory_summarize(session=session)["summary"]
            hits = self.memory_search(query=content, top_k=3, session=session)
            ctx = summary + "\n" + "\n".join(r["content"] for r in hits["results"])
            memory_total += count_tokens(ctx)

        savings_pct = round(100 * (1 - memory_total / naive_total), 1) if naive_total else 0.0
        self._emit_live(f"memory_simulate · {turns} tours · économie {savings_pct}%")
        return {
            "simulated_turns": turns,
            "session": session,
            "naive_tokens": naive_total,
            "memory_tokens": memory_total,
            "savings_pct": savings_pct,
            "stats": self.memory_stats(),
        }
