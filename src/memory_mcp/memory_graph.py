"""Graphe de souvenirs liés (inspiré A-MEM, Xu et al. 2025)."""

from __future__ import annotations

from memory_mcp.embeddings import cosine_similarity
from memory_mcp.storage import MemoryStore

LINK_THRESHOLD = 0.7


def link_memory_to_similar(
    store: MemoryStore,
    memory_id: int,
    session: str,
    threshold: float = LINK_THRESHOLD,
    max_links: int = 5,
) -> int:
    """Crée des liens sémantiques entre le nouveau souvenir et les existants."""
    vec = store.get_embedding(memory_id)
    if vec is None:
        return 0

    rows = store.iter_active_embeddings(session, memory_id)

    from memory_mcp.embeddings import deserialize

    created = 0
    candidates: list[tuple[float, int]] = []
    for mem_id, blob in rows:
        other_vec = deserialize(blob)
        sim = cosine_similarity(vec, other_vec)
        if sim >= threshold:
            candidates.append((sim, mem_id))

    candidates.sort(reverse=True)
    for sim, target_id in candidates[:max_links]:
        store.add_link(memory_id, target_id, sim)
        created += 1
    return created


def expand_with_linked(store: MemoryStore, memory_ids: list[int], max_extra: int = 2) -> list[int]:
    """Étend les résultats de recherche avec des souvenirs liés (1-hop)."""
    extra: list[int] = []
    seen = set(memory_ids)
    for mid in memory_ids:
        for link in store.get_links(mid):
            other = link["target"] if link["source"] == mid else link["source"]
            if other not in seen and len(extra) < max_extra:
                extra.append(other)
                seen.add(other)
    return extra
