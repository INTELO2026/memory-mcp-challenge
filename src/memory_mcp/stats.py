"""Compteur de tokens consommés (axe coût du benchmark) + série temporelle.

Modèle de comparaison « naïf » vs MemBridge :
- **Naïf** : à chaque tour (store / search / summarize), l'agent renverrait tout
  l'historique accumulé dans le contexte → coût d'entrée qui croît de façon
  quadratique (O(n²)) sur la conversation.
- **MemBridge** : chaque tour n'envoie que l'info utile (fait stocké, requête +
  extrait récupéré, ou résumé) → coût quasi constant par tour (O(n) cumulé).

Le gain de tokens = 1 − membridge_total / naive_total ; il dépasse vite 70 % dès
que la conversation comporte plusieurs tours.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone

_BUCKET_FMT = {"hour": "%Y-%m-%d %H:00", "day": "%Y-%m-%d", "month": "%Y-%m"}


@dataclass
class TokenStats:
    """Statistiques cumulées sur une session."""

    input_tokens: int = 0
    output_tokens: int = 0
    store_calls: int = 0
    search_calls: int = 0
    summarize_calls: int = 0
    entries_count: int = 0
    tokens_stored: int = 0
    active_model: str | None = None
    naive_total: int = 0       # tokens d'entrée cumulés en mode naïf
    membridge_total: int = 0   # tokens d'entrée cumulés réels (MemBridge)
    _running_stored: int = 0
    events: list = field(default_factory=list)  # [{ts, naive, actual}] par tour

    def set_model(self, model: str | None) -> None:
        """Mémorise le modèle IA déclaré par l'agent (le dernier déclaré gagne)."""
        if model:
            self.active_model = model

    def add_input(self, tokens: int) -> None:
        self.input_tokens += tokens

    def add_output(self, tokens: int) -> None:
        self.output_tokens += tokens

    def _record_turn(self, naive_turn: int, actual_turn: int) -> None:
        """Enregistre un tour : coût naïf (historique complet) vs coût réel."""
        self.naive_total += naive_turn
        self.membridge_total += actual_turn
        self.events.append({
            "ts": datetime.now(timezone.utc).isoformat(),
            "naive": naive_turn,
            "actual": actual_turn,
        })

    def record_store(self, content_tokens: int) -> None:
        """memory_store : naïf renverrait tout l'historique, MemBridge juste le fait."""
        self.tokens_stored += content_tokens
        self.entries_count += 1
        self._running_stored += content_tokens
        self._record_turn(naive_turn=self._running_stored, actual_turn=content_tokens)

    def record_search(self, query_tokens: int, result_tokens: int) -> None:
        """memory_search : naïf = historique + requête, MemBridge = requête + extrait."""
        self._record_turn(
            naive_turn=self._running_stored + query_tokens,
            actual_turn=query_tokens + result_tokens,
        )

    def record_summarize(self, summary_tokens: int) -> None:
        """memory_summarize : naïf = historique complet, MemBridge = résumé compact."""
        self._record_turn(naive_turn=self._running_stored, actual_turn=summary_tokens)

    def naive_tokens(self) -> int:
        """Tokens d'entrée cumulés en mode naïf (historique complet à chaque tour)."""
        return self.naive_total

    def tokens_saved(self) -> int:
        """Tokens économisés par MemBridge par rapport au mode naïf."""
        return max(0, self.naive_total - self.membridge_total)

    def gain_pct(self) -> float:
        """Gain de tokens en % (0 si aucun tour enregistré)."""
        if self.naive_total <= 0:
            return 0.0
        return round((self.naive_total - self.membridge_total) / self.naive_total * 100, 1)

    def total(self) -> int:
        return self.input_tokens + self.output_tokens

    def timeseries(self, bucket: str = "hour") -> dict:
        """Agrège les tours par tranche (hour/day/month) + cumuls naïf/MemBridge."""
        fmt = _BUCKET_FMT.get(bucket, _BUCKET_FMT["hour"])
        agg: dict[str, dict[str, int]] = {}
        order: list[str] = []
        for e in self.events:
            dt = datetime.fromisoformat(e["ts"])
            key = dt.strftime(fmt)
            if key not in agg:
                agg[key] = {"naive": 0, "actual": 0}
                order.append(key)
            agg[key]["naive"] += e["naive"]
            agg[key]["actual"] += e["actual"]
        points = []
        cum_n = cum_a = 0
        for key in order:
            cum_n += agg[key]["naive"]
            cum_a += agg[key]["actual"]
            gain = round((cum_n - cum_a) / cum_n * 100, 1) if cum_n else 0.0
            points.append({
                "label": key,
                "naive": agg[key]["naive"],
                "actual": agg[key]["actual"],
                "naive_cum": cum_n,
                "actual_cum": cum_a,
                "gain_pct": gain,
            })
        return {"bucket": bucket, "points": points, "turns": len(self.events)}

    def to_dict(self) -> dict:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total(),
            "store_calls": self.store_calls,
            "search_calls": self.search_calls,
            "summarize_calls": self.summarize_calls,
            "entries_count": self.entries_count,
            "tokens_stored": self.tokens_stored,
            "tokens_saved": self.tokens_saved(),
            "naive_tokens": self.naive_tokens(),
            "membridge_tokens": self.membridge_total,
            "gain_pct": self.gain_pct(),
            "turns": len(self.events),
            "active_model": self.active_model,
        }


# Instance globale pour la démo / benchmark
_stats = TokenStats()


def get_stats() -> TokenStats:
    return _stats


def reset_stats() -> None:
    global _stats
    _stats = TokenStats()


def count_tokens(text: str) -> int:
    """Estimation tokens via tiktoken (cl100k_base) ou fallback caractères/4."""
    try:
        import tiktoken

        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))
    except Exception:
        return max(1, len(text) // 4)
