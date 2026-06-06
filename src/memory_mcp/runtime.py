"""Instance partagée des outils mémoire (MCP + HTTP + chat).

Un seul MemoryTools pour tout le processus : les écritures via MCP SSE et via
l'API REST ciblent la même base SQLite sur disque.
"""

from __future__ import annotations

from memory_mcp.stats import reconcile_stats_with_store
from memory_mcp.storage import MemoryStore, default_db_path
from memory_mcp.tools import MemoryTools

_tools: MemoryTools | None = None


def get_tools() -> MemoryTools:
    """Retourne le gestionnaire mémoire singleton du processus."""
    global _tools
    if _tools is None:
        store = MemoryStore(default_db_path())
        reconcile_stats_with_store(store)
        _tools = MemoryTools(store)
    return _tools


def db_path() -> str:
    """Chemin effectif de la base SQLite."""
    return get_tools().store.db_path
