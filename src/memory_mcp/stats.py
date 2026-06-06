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
    entries_count: int = 0
    tokens_stored: int = 0
    _naive_equivalent: int = 0
    _running_stored: int = 0

    def add_input(self, tokens: int) -> None:
        self.input_tokens += tokens

    def add_output(self, tokens: int) -> None:
        self.output_tokens += tokens

    def record_store(self, content_tokens: int) -> None:
        """Appelé à chaque memory_store pour suivre l'équivalent naïf."""
        self.tokens_stored += content_tokens
        self.entries_count += 1
        self._running_stored += content_tokens
        # En mode naïf, tout l'historique est renvoyé à chaque tour
        self._naive_equivalent += self._running_stored

    def tokens_saved(self) -> int:
        """Estimation des tokens économisés par rapport au mode naïf."""
        return max(0, self._naive_equivalent - self.output_tokens)

    def total(self) -> int:
        return self.input_tokens + self.output_tokens

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
        }


# Instance globale pour la démo / benchmark
_stats = TokenStats()


def get_stats() -> TokenStats:
    return _stats


def reset_stats() -> None:
    global _stats
    _stats = TokenStats()


def count_tokens(text: str) -> int:
    """Estimation tokens via tiktoken (gpt-4o-mini) ou fallback caractères/4."""
    try:
        import tiktoken

        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))
    except Exception:
        return max(1, len(text) // 4)
