"""Compteur de tokens consommés (axe coût du benchmark) + série temporelle.

Toutes les statistiques sont **persistées sur disque** (~/.memory_mcp/stats.json)
et rechargées au redémarrage du serveur, comme les entrées mémoire.

Modèle de comparaison « naïf » vs MemBridge :
- **Naïf** : à chaque tour (store / search / summarize), l'agent renverrait tout
  l'historique accumulé dans le contexte → coût d'entrée qui croît de façon
  quadratique (O(n²)) sur la conversation.
- **MemBridge** : chaque tour n'envoie que l'info utile (fait stocké, requête +
  extrait récupéré, ou résumé) → coût quasi constant par tour (O(n) cumulé).
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

_BUCKET_FMT = {"hour": "%Y-%m-%d %H:00", "day": "%Y-%m-%d", "month": "%Y-%m"}


def stats_path() -> Path:
    """Fichier JSON de persistance des compteurs (surcharge : MEMORY_STATS_PATH)."""
    env = os.environ.get("MEMORY_STATS_PATH")
    if env:
        return Path(env)
    base = Path.home() / ".memory_mcp"
    base.mkdir(parents=True, exist_ok=True)
    return base / "stats.json"


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
    naive_total: int = 0
    membridge_total: int = 0
    _running_stored: int = 0
    events: list = field(default_factory=list)

    def _save(self) -> None:
        persist_stats(self)

    def set_model(self, model: str | None) -> None:
        if model:
            self.active_model = model
            self._save()

    def add_input(self, tokens: int) -> None:
        self.input_tokens += tokens
        self._save()

    def add_output(self, tokens: int) -> None:
        self.output_tokens += tokens
        self._save()

    def bump_store_calls(self) -> None:
        self.store_calls += 1
        self._save()

    def bump_search_calls(self) -> None:
        self.search_calls += 1
        self._save()

    def bump_summarize_calls(self) -> None:
        self.summarize_calls += 1
        self._save()

    def _record_turn(self, naive_turn: int, actual_turn: int) -> None:
        self.naive_total += naive_turn
        self.membridge_total += actual_turn
        self.events.append(
            {
                "ts": datetime.now(timezone.utc).isoformat(),
                "naive": naive_turn,
                "actual": actual_turn,
            }
        )
        self._save()

    def record_store(self, content_tokens: int) -> None:
        self.tokens_stored += content_tokens
        self.entries_count += 1
        self._running_stored += content_tokens
        self._record_turn(naive_turn=self._running_stored, actual_turn=content_tokens)

    def record_search(self, query_tokens: int, result_tokens: int) -> None:
        self._record_turn(
            naive_turn=self._running_stored + query_tokens,
            actual_turn=query_tokens + result_tokens,
        )

    def record_summarize(self, summary_tokens: int) -> None:
        self._record_turn(naive_turn=self._running_stored, actual_turn=summary_tokens)

    def naive_tokens(self) -> int:
        return self.naive_total

    def tokens_saved(self) -> int:
        return max(0, self.naive_total - self.membridge_total)

    def gain_pct(self) -> float:
        if self.naive_total <= 0:
            return 0.0
        return round((self.naive_total - self.membridge_total) / self.naive_total * 100, 1)

    def total(self) -> int:
        return self.input_tokens + self.output_tokens

    def timeseries(self, bucket: str = "hour") -> dict:
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
            points.append(
                {
                    "label": key,
                    "naive": agg[key]["naive"],
                    "actual": agg[key]["actual"],
                    "naive_cum": cum_n,
                    "actual_cum": cum_a,
                    "gain_pct": gain,
                }
            )
        return {"bucket": bucket, "points": points, "turns": len(self.events)}

    def context_tokens(self) -> int:
        return self._running_stored

    def to_dict(self) -> dict:
        saved = self.tokens_saved()
        turns = len(self.events)
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total(),
            "store_calls": self.store_calls,
            "search_calls": self.search_calls,
            "summarize_calls": self.summarize_calls,
            "entries_count": self.entries_count,
            "tokens_stored": self.tokens_stored,
            "tokens_saved": saved,
            "naive_tokens": self.naive_tokens(),
            "membridge_tokens": self.membridge_total,
            "context_tokens": self.context_tokens(),
            "gain_pct": self.gain_pct(),
            "turns": turns,
            "gain_ready": turns >= 2 or self.search_calls > 0 or self.summarize_calls > 0,
            "active_model": self.active_model,
        }

    def to_json_dict(self) -> dict:
        """Sérialisation complète pour persistance disque."""
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "store_calls": self.store_calls,
            "search_calls": self.search_calls,
            "summarize_calls": self.summarize_calls,
            "entries_count": self.entries_count,
            "tokens_stored": self.tokens_stored,
            "active_model": self.active_model,
            "naive_total": self.naive_total,
            "membridge_total": self.membridge_total,
            "_running_stored": self._running_stored,
            "events": self.events,
        }

    @classmethod
    def from_json_dict(cls, data: dict) -> TokenStats:
        return cls(
            input_tokens=int(data.get("input_tokens", 0)),
            output_tokens=int(data.get("output_tokens", 0)),
            store_calls=int(data.get("store_calls", 0)),
            search_calls=int(data.get("search_calls", 0)),
            summarize_calls=int(data.get("summarize_calls", 0)),
            entries_count=int(data.get("entries_count", 0)),
            tokens_stored=int(data.get("tokens_stored", 0)),
            active_model=data.get("active_model"),
            naive_total=int(data.get("naive_total", 0)),
            membridge_total=int(data.get("membridge_total", 0)),
            _running_stored=int(data.get("_running_stored", 0)),
            events=list(data.get("events") or []),
        )


def persist_stats(stats: TokenStats | None = None) -> None:
    """Écrit les stats sur disque (atomique via fichier temporaire)."""
    stats = stats or get_stats()
    path = stats_path()
    tmp = path.with_suffix(".json.tmp")
    payload = json.dumps(stats.to_json_dict(), ensure_ascii=False, indent=2)
    tmp.write_text(payload, encoding="utf-8")
    tmp.replace(path)


def load_stats() -> TokenStats:
    """Charge les stats depuis le disque, ou retourne un objet vide."""
    path = stats_path()
    if not path.exists():
        return TokenStats()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return TokenStats.from_json_dict(data)
    except (json.JSONDecodeError, OSError, TypeError, ValueError):
        return TokenStats()


def reconcile_stats_with_store(store) -> None:
    """Aligne entrées/tokens stockés sur la base SQLite (cohérence après reset partiel)."""
    stats = get_stats()
    db_entries = store.count()
    db_tokens = store.total_content_tokens()
    changed = False
    if db_entries > stats.entries_count:
        stats.entries_count = db_entries
        changed = True
    if db_tokens > stats.tokens_stored:
        stats.tokens_stored = db_tokens
        changed = True
    if db_tokens > stats._running_stored:
        stats._running_stored = db_tokens
        changed = True
    if changed:
        persist_stats(stats)


_stats: TokenStats | None = None


def get_stats() -> TokenStats:
    global _stats
    if _stats is None:
        _stats = load_stats()
    return _stats


def reset_stats() -> None:
    global _stats
    _stats = TokenStats()
    persist_stats(_stats)


def count_tokens(text: str) -> int:
    """Estimation tokens via tiktoken (cl100k_base) ou fallback caractères/4."""
    try:
        import tiktoken

        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))
    except Exception:
        return max(1, len(text) // 4)
