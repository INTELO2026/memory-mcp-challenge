"""Isole les tests : stats + mémoire en fichiers temporaires (pas ~/.memory_mcp)."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _isolated_persistence(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORY_DB_PATH", str(tmp_path / "test_memory.db"))
    monkeypatch.setenv("MEMORY_STATS_PATH", str(tmp_path / "test_stats.json"))

    import memory_mcp.runtime as runtime
    import memory_mcp.stats as stats_mod

    runtime._tools = None
    stats_mod._stats = None
    stats_mod.reset_stats()
    yield
    runtime._tools = None
    stats_mod._stats = None
