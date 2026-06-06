"""Courbe de rétention d'Ebbinghaus et politique d'oubli intelligent."""

from __future__ import annotations

import math
from datetime import datetime, timezone


def hours_since(dt: datetime, now: datetime | None = None) -> float:
    """Heures écoulées depuis dt."""
    now = now or datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return max(0.0, (now - dt).total_seconds() / 3600.0)


def retention(t_hours: float, stability: float) -> float:
    """R(t) = exp(-t / S) — courbe d'Ebbinghaus."""
    if stability <= 0:
        return 0.0
    return math.exp(-t_hours / stability)


def update_stability(old_stability: float, access_count: int) -> float:
    """Spacing effect : S_new = S_old × (1 + 0.2 × log(1 + access_count))."""
    return old_stability * (1.0 + 0.2 * math.log1p(access_count))


def recency_decay(t_hours: float, lam: float = 0.1) -> float:
    """Décroissance exponentielle pour le re-ranking."""
    return math.exp(-lam * t_hours)


def should_archive(retention_score: float, importance: float, threshold: float = 0.1) -> bool:
    """Archive les souvenirs faibles et peu importants."""
    return retention_score < threshold and importance < 0.3
