"""Compteur de tokens + métriques MemBridge pour benchmark et dashboard."""

from __future__ import annotations

from dataclasses import dataclass, field

# Prix Claude Sonnet (input) — USD per 1M tokens, taux EUR/USD
INPUT_PRICE_USD_PER_M = 3.0
EUR_USD = 0.92

# Estimation contexte MemBridge par tour (tokens)
SYSTEM_PROMPT_TOKENS = 300
SLIDING_WINDOW_TURNS = 3
AVG_TURN_TOKENS = 50


@dataclass
class SessionMetrics:
    turn_count: int = 0
    token_naive: int = 0
    token_membridge: int = 0

    @property
    def reduction_pct(self) -> float:
        if self.token_naive == 0:
            return 0.0
        return round(100 * (1 - self.token_membridge / self.token_naive), 1)


@dataclass
class TokenStats:
    """Statistiques cumulées sur une session."""

    input_tokens: int = 0
    output_tokens: int = 0
    store_calls: int = 0
    search_calls: int = 0
    summarize_calls: int = 0
    tokens_stored_naive: int = 0
    tokens_used_membridge: int = 0
    sessions: dict[str, SessionMetrics] = field(default_factory=dict)

    def add_input(self, tokens: int) -> None:
        self.input_tokens += tokens

    def add_output(self, tokens: int) -> None:
        self.output_tokens += tokens

    def record_turn(self, session: str, naive_tokens: int, membridge_tokens: int) -> None:
        if session not in self.sessions:
            self.sessions[session] = SessionMetrics()
        sm = self.sessions[session]
        sm.turn_count += 1
        sm.token_naive += naive_tokens
        sm.token_membridge += membridge_tokens
        self.tokens_stored_naive += naive_tokens
        self.tokens_used_membridge += membridge_tokens

    def total(self) -> int:
        return self.input_tokens + self.output_tokens

    @property
    def tokens_saved(self) -> int:
        return max(0, self.tokens_stored_naive - self.tokens_used_membridge)

    @property
    def savings_percentage(self) -> float:
        if self.tokens_stored_naive == 0:
            return 0.0
        return round(100 * self.tokens_saved / self.tokens_stored_naive, 1)

    @property
    def cost_saved_euros(self) -> float:
        usd = (self.tokens_saved / 1_000_000) * INPUT_PRICE_USD_PER_M
        return round(usd * EUR_USD, 4)

    def to_dict(self) -> dict:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total(),
            "store_calls": self.store_calls,
            "search_calls": self.search_calls,
            "summarize_calls": self.summarize_calls,
            "total_entries": 0,
            "archived_entries": 0,
            "active_entries": 0,
            "tokens_stored_naive": self.tokens_stored_naive,
            "tokens_used_membridge": self.tokens_used_membridge,
            "tokens_saved": self.tokens_saved,
            "savings_percentage": self.savings_percentage,
            "cost_saved_euros": self.cost_saved_euros,
            "avg_retrieval_time_ms": 0.0,
            "sessions": {
                sid: {
                    "turn_count": sm.turn_count,
                    "token_naive": sm.token_naive,
                    "token_membridge": sm.token_membridge,
                    "reduction_pct": sm.reduction_pct,
                }
                for sid, sm in self.sessions.items()
            },
        }


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


def enrich_stats_dict(base: dict, store) -> dict:
    """Enrichit le dict stats avec données live du store."""
    base["total_entries"] = store.count()
    base["archived_entries"] = store.count_archived()
    base["active_entries"] = store.count(active_only=True)
    base["avg_retrieval_time_ms"] = round(store.avg_retrieval_time_ms(), 2)
    return base
