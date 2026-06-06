"""Compteur de tokens consommés (axe coût du benchmark)."""

from dataclasses import dataclass


@dataclass
class TokenStats:
    """Statistiques cumulées sur une session."""

    input_tokens: int = 0
    output_tokens: int = 0
    stored_tokens: int = 0
    saved_tokens: int = 0
    store_calls: int = 0
    search_calls: int = 0
    summarize_calls: int = 0

    def add_input(self, tokens: int) -> None:
        self.input_tokens += tokens

    def add_output(self, tokens: int) -> None:
        self.output_tokens += tokens

    def add_stored(self, tokens: int) -> None:
        """Tokens entrés en mémoire (ce qu'un agent naïf renverrait à chaque tour)."""
        self.stored_tokens += tokens

    def add_saved(self, tokens: int) -> None:
        """Tokens économisés en restituant un extrait plutôt que toute la mémoire."""
        self.saved_tokens += max(0, tokens)

    def total(self) -> int:
        return self.input_tokens + self.output_tokens

    def to_dict(self) -> dict:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total(),
            "stored_tokens": self.stored_tokens,
            "saved_tokens": self.saved_tokens,
            "store_calls": self.store_calls,
            "search_calls": self.search_calls,
            "summarize_calls": self.summarize_calls,
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
