"""Compteur de tokens consommés (axe coût du benchmark)."""

from dataclasses import dataclass


@dataclass
class TokenStats:
    """Statistiques cumulées sur une session."""

    input_tokens: int = 0
    output_tokens: int = 0
    store_calls: int = 0
    search_calls: int = 0
    summarize_calls: int = 0
    tokens_stored: int = 0
    tokens_saved: int = 0

    def add_input(self, tokens: int) -> None:
        self.input_tokens += tokens

    def add_output(self, tokens: int) -> None:
        self.output_tokens += tokens

    def total(self) -> int:
        return self.input_tokens + self.output_tokens

    def to_dict(self, entry_count: int = 0) -> dict:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total(),
            "tokens_stored": self.tokens_stored,
            "tokens_saved": self.tokens_saved,
            "entry_count": entry_count,
            "store_calls": self.store_calls,
            "search_calls": self.search_calls,
            "summarize_calls": self.summarize_calls,
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


def truncate_to_tokens(text: str, max_tokens: int) -> str:
    """Tronque un texte pour respecter une limite de tokens."""
    if count_tokens(text) <= max_tokens:
        return text
    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if count_tokens(text[:mid]) <= max_tokens:
            lo = mid
        else:
            hi = mid - 1
    trimmed = text[:lo].rstrip()
    if lo < len(text):
        trimmed = trimmed[: max(0, len(trimmed) - 3)] + "..."
    return trimmed
