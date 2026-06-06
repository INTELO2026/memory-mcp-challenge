"""Tests fonctionnalités avancées MemBridge."""

from __future__ import annotations

from memory_mcp.stats import reset_stats
from memory_mcp.tools import MemoryTools


def test_store_metadata_and_dedupe():
    reset_stats()
    tools = MemoryTools()
    first = tools.memory_store(
        "Contrat CTR-2024-8847",
        tags=["fact"],
        session="adv",
        turn=1,
        importance=3,
    )
    second = tools.memory_store(
        "Contrat CTR-2024-8847",
        tags=["fact"],
        session="adv",
        turn=2,
        importance=3,
    )
    assert first["id"] == second["id"]
    assert second["deduplicated"] is True
    assert "date" in first
    assert first["importance"] == 3


def test_search_ranking_breakdown():
    reset_stats()
    tools = MemoryTools()
    tools.memory_store("Marie Dupont premium TechCorp", tags=["fact"], session="rank", turn=1)
    tools.memory_store("bruit meteo football", tags=["noise"], session="rank", turn=99)
    result = tools.memory_search("identite interlocutrice premium", top_k=1, session="rank")
    assert result["count"] == 1
    assert "ranking" in result["results"][0]
    assert result["results"][0]["ranking"]["semantic"] > 0


def test_search_tag_filter():
    reset_stats()
    tools = MemoryTools()
    tools.memory_store("fait important", tags=["fact"], session="filt", turn=1)
    tools.memory_store("echange", tags=["exchange"], session="filt", turn=2)
    result = tools.memory_search("important", session="filt", tag="fact", top_k=5)
    assert all("fact" in r["tags"] for r in result["results"])


def test_summarize_report_rich():
    reset_stats()
    tools = MemoryTools()
    for i in range(15):
        tools.memory_store(
            f"fait {i} contrat CTR-2024 — detail contextuel repetitif " * 4,
            tags=["fact"],
            session="sum",
            turn=i,
        )
    report = tools.memory_summarize(session="sum", max_tokens=40)
    assert report["source_tokens"] > report["summary_tokens"]
    assert report["compression_ratio"] < 1.0
    assert report["facts_preserved"] >= 1
    assert report["method"] == "heuristic"


def test_stats_advanced_payload():
    reset_stats()
    tools = MemoryTools()
    tools.memory_store("alpha", session="s-a", turn=1)
    tools.memory_store("beta", session="s-b", turn=1)
    stats = tools.memory_stats()
    assert stats["engine"]["vector_index"] == "FAISS IndexFlatIP"
    assert stats["features"]["deduplication"] is True
    assert len(stats["sessions"]) >= 2
