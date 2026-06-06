"""Tests de régression publics — le squelette DOIT échouer ici.

Ces tests sont volontairement exigeants : paraphrases, bruit, compression,
isolation de session. La validation finale complète est dans le dépôt privé.
"""

from __future__ import annotations

from benchmark.harness import CONVERSATION_PATH, generate_long_conversation, load_json
from benchmark.naive import simulate_naive_conversation
from benchmark.scoring import compression_ratio, context_growth_factor, per_turn_context_tokens
from memory_mcp.stats import reset_stats
from memory_mcp.tools import MemoryTools
from memory_mcp.validation import top1_contains


def _seed_session(tools: MemoryTools, session: str) -> None:
    """Conversation réaliste avec faits clés éparpillés."""
    facts = [
        (1, "user: Bonjour, je suis Marie Dupont, cliente premium chez TechCorp."),
        (3, "user: Mon numéro de contrat est CTR-2024-8847."),
        (5, "user: La facture de mars devrait être 99,90 € mais affiche 149,90 €."),
        (7, "user: Bug mobile signalé le 12 février sur l'application iOS."),
        (9, "user: Email de contact : marie.dupont@email.fr."),
    ]
    for turn, content in facts:
        tools.memory_store(content, tags=["fact"], session=session, turn=turn)


def _add_noise(tools: MemoryTools, session: str, count: int = 30) -> None:
    noise_topics = [
        "météo Paris 18°C vent faible",
        "recette tarte aux pommes sans gluten",
        "match PSG 2-1 fin de saison",
        "taux change EUR USD 1.08",
        "sortie cinéma blockbuster mars",
    ]
    for i in range(count):
        topic = noise_topics[i % len(noise_topics)]
        tools.memory_store(
            f"assistant: hors-sujet tour {i} — {topic} — bruit sémantique {i * 17}",
            tags=["noise"],
            session=session,
            turn=100 + i,
        )


# --- Recherche sémantique (paraphrases sans mots-clés communs) ---

PARAPHRASE_CASES = [
    ("identité de l'interlocutrice premium", "Marie Dupont"),
    ("référence légale du dossier client", "CTR-2024-8847"),
    ("coordonnées électroniques de contact", "marie.dupont@email.fr"),
    ("écart tarifaire facturation printemps", "149,90"),
    ("incident application mobile date", "12 février"),
]


def test_semantic_paraphrase_top1():
    """La recherche doit comprendre des paraphrases, pas matcher des mots-clés."""
    for query, expected in PARAPHRASE_CASES:
        reset_stats()
        tools = MemoryTools()
        _seed_session(tools, "para")
        _add_noise(tools, "para", count=25)
        result = tools.memory_search(query, top_k=1, session="para")
        assert result["count"] >= 1, f"Aucun résultat pour '{query}' (similarité nulle)"
        assert result["results"][0].get("score", 0) > 0.01
        assert top1_contains(expected, result["results"]), (
            f"Échec paraphrase '{query}' → attendu '{expected}'"
        )


def test_session_isolation():
    """Aucune fuite entre sessions distinctes."""
    tools = MemoryTools()
    tools.memory_store("secret session alpha: ZEBRA-ALPHA-991", session="alpha", turn=1)
    tools.memory_store("secret session beta: ZEBRA-BETA-442", session="beta", turn=1)

    alpha_hits = tools.memory_search("ZEBRA", top_k=5, session="alpha")
    beta_hits = tools.memory_search("ZEBRA", top_k=5, session="beta")

    assert all("BETA" not in h["content"] for h in alpha_hits["results"])
    assert all("ALPHA" not in h["content"] for h in beta_hits["results"])


def test_summarize_compression_on_long_session():
    """Le résumé doit compresser réellement une longue session."""
    reset_stats()
    tools = MemoryTools()
    _seed_session(tools, "compress")
    _add_noise(tools, "compress", count=35)
    ratio = compression_ratio(tools, "compress")
    assert ratio <= 0.25, f"Ratio compression trop élevé : {ratio:.2f} (max 0.25)"


def test_summarize_retains_critical_facts():
    """Le résumé compressé doit garder les faits critiques du début."""
    tools = MemoryTools()
    _seed_session(tools, "facts")
    _add_noise(tools, "facts", count=40)
    summary = tools.memory_summarize(session="facts", max_chars=400)
    text = summary["summary"].lower()
    assert "marie" in text or "dupont" in text
    assert "ctr-2024-8847" in text


# --- Benchmark coût ---


def test_savings_minimum_60pct_on_50_turns():
    """Économie tokens ≥ 60 % sur 50 tours."""
    from benchmark.harness import simulate_memory_conversation

    base = load_json(CONVERSATION_PATH)
    turns = generate_long_conversation(base, target_turns=50)
    naive = simulate_naive_conversation(turns)
    memory = simulate_memory_conversation(turns, session="savings-50")
    savings = 100 * (1 - memory["total_tokens"] / naive["total_tokens"])
    assert savings >= 60.0, f"Économie insuffisante : {savings:.1f}% (min 60%)"


def test_context_growth_plateau():
    """Le coût par tour doit stagner, pas croître linéairement."""
    base = load_json(CONVERSATION_PATH)
    turns = generate_long_conversation(base, target_turns=50)
    reset_stats()
    tools = MemoryTools()
    per_turn: list[int] = []

    for turn in turns:
        tools.memory_store(
            f"{turn['role']}: {turn['content']}",
            session="plateau",
            turn=turn["turn"],
        )
        per_turn.append(
            per_turn_context_tokens(tools, "plateau", turn["content"], turn=turn["turn"])
        )

    factor = context_growth_factor(per_turn)
    assert factor <= 1.15, f"Contexte encore croissant : facteur {factor:.2f} (max 1.15)"


def test_search_empty_store():
    tools = MemoryTools()
    result = tools.memory_search("anything", session="empty-session")
    assert result["count"] == 0
    assert result["results"] == []
