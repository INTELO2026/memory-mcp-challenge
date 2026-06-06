"""Tests des pistes bonus (§10) : persistance, hiérarchie, oubli, mémoire partagée."""

from memory_mcp.storage import MemoryStore
from memory_mcp.tools import MemoryTools

# --- Persistance entre sessions -------------------------------------------


def test_persistence_across_reopen(tmp_path):
    """La mémoire écrite sur disque est retrouvée après réouverture (§10)."""
    db = tmp_path / "mem.db"
    s1 = MemoryStore(str(db))
    s1.store("La cliente s'appelle Marie Dupont, statut premium", session="p", turn=1)
    s1.close()

    s2 = MemoryStore(str(db))
    assert s2.count() == 1
    hits = s2.search("identité de la cliente", top_k=1, session="p")
    assert hits and "Marie Dupont" in hits[0].content
    s2.close()


# --- Oubli intelligent -----------------------------------------------------


def test_intelligent_forgetting_removes_duplicates():
    """Les souvenirs quasi redondants sont purgés, les faits distincts conservés."""
    s = MemoryStore()
    s.store("Le rendez-vous est fixé à lundi 10h", session="f", turn=1)
    s.store("Le rendez-vous est fixé à lundi 10h", session="f", turn=2)  # doublon
    s.store("La facture s'élève à 149,90 euros", session="f", turn=3)  # distinct

    removed = s.prune_redundant("f", threshold=0.97)
    assert removed == 1
    assert s.count() == 2


def test_memory_forget_tool():
    tools = MemoryTools()
    tools.memory_store("Code d'accès : 4821", session="g", turn=1)
    tools.memory_store("Code d'accès : 4821", session="g", turn=2)
    out = tools.memory_forget(session="g")
    assert out["forgotten"] == 1
    assert out["remaining"] == 1


# --- Hiérarchie de pertinence ---------------------------------------------


def test_relevance_hierarchy_recency_breaks_tie():
    """À pertinence sémantique égale, la récence départage (§10)."""
    s = MemoryStore()
    s.store("Le code d'accès est 4821", session="h", turn=1)
    s.store("Le code d'accès est 4821", session="h", turn=9)  # même contenu, plus récent

    top = s.search("quel est le code d'accès", top_k=1, session="h", recency_weight=0.5)
    assert top[0].turn == 9


def test_frequency_is_tracked_on_search():
    """La fréquence d'accès est comptabilisée à chaque recherche (§10)."""
    s = MemoryStore()
    mid = s.store("Le numéro de contrat est CTR-2024-8847", session="q", turn=1)
    for _ in range(3):
        s.search("référence du contrat", top_k=1, session="q")
    row = s._conn.execute("SELECT access_count FROM memories WHERE id = ?", (mid,)).fetchone()
    assert row["access_count"] == 3


# --- Mémoire partagée entre agents ----------------------------------------


def test_shared_memory_between_agents():
    """Un agent écrit dans la mémoire partagée, un autre agent la relit (§10)."""
    store = MemoryStore()
    agent_a = MemoryTools(store)
    agent_b = MemoryTools(store)

    agent_a.memory_store("Politique de retour : 30 jours", session="shared", turn=1)

    relu = agent_b.memory_search("délai de retour", top_k=1, session="shared")
    assert relu["count"] == 1
    assert "30 jours" in relu["results"][0]["content"]

    # L'agent B garde sa session privée tout en lisant l'espace partagé.
    agent_b.memory_store("Préférence agent B", session="agent-b", turn=1)
    mixte = agent_b.memory_search(
        "politique de retour", top_k=3, session="agent-b", shared_session="shared"
    )
    contenus = " ".join(r["content"] for r in mixte["results"])
    assert "30 jours" in contenus
