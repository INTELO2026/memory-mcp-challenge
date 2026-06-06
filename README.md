# Memory MCP Challenge — FINALE

**Hackathon INTELO2026** — Serveur MCP de mémoire avec benchmark chiffré tokens/qualité.

> Construisez un serveur MCP qui prouve qu'on peut réduire drastiquement les tokens d'un agent conversationnel **sans le rendre amnésique**.

## Finale — règles importantes

Le squelette fourni **ne suffit pas** pour merger une PR :

| Job CI | Passent avec le squelette ? |
|--------|----------------------------|
| `lint` + `smoke` | Oui |
| `regression` | **Non** — paraphrases, bruit, compression |
| `finale-eval` | **Non** — tests cachés (dépôt privé) |

Les tests cachés ne sont **pas dans ce dépôt**. Même avec l'IA, il faut une vraie recherche sémantique et une vraie compression.

## Contexte

| Mode | Comportement | Coût tokens |
|------|-------------|-------------|
| **Naïf** | Renvoie tout l'historique à chaque tour | Croissance quadratique |
| **Mémoire MCP** | Stocke, recherche, résume | Quasi plat |

## Architecture de la solution (MemBridge)

À chaque tour, l'agent n'envoie plus tout l'historique : il appelle le serveur MCP.

```
Tour N → memory_store(message)   → embedding Gemini (retrieval_document) → SQLite
       → memory_search(message)  → embedding Gemini (retrieval_query) → top-k souvenirs
       → memory_summarize(session) → résumé compressé des faits importants
       → le LLM reçoit ~résumé + k souvenirs (~700 tk) au lieu de N×500 tk
```

- **Embeddings** : `gemini-embedding-001` (768 dims) en backend principal. Fallback
  local automatique (`sentence-transformers`, modèle e5 multilingue) si aucune clé,
  puis secours lexical déterministe. Voir `src/memory_mcp/embeddings.py`.
- **Stockage vectoriel** : SQLite + similarité cosinus (numpy), avec **hiérarchie de
  pertinence** (récence + importance estimée + fréquence d'accès) en départage.
- **Résumé** : sélection extractive des tours les plus *importants* (densité
  d'entités : identifiants, emails, montants, noms) → compression forte sans perdre
  les faits clés.

## Structure

```
memory-mcp-challenge/
├── src/memory_mcp/
│   ├── server.py        # Serveur MCP (stdio) + 4 outils
│   ├── tools.py         # store / search / summarize / stats
│   ├── storage.py       # SQLite + recherche sémantique + ranking
│   ├── embeddings.py    # Gemini (principal) + fallback local + secours
│   └── stats.py         # Compteur de tokens
├── benchmark/
│   ├── scenario.json    # Conversation scriptée + questions pièges
│   ├── harness.py       # Rapport complet (tokens, €, qualité) → results/report.json
│   ├── live.py          # Rejeu live (courbes qui montent en direct)
│   └── naive.py / scoring.py
├── demo/agent.py        # Démo support client + questions pièges
├── dashboard/index.html # 2 courbes live + économie + qualité (polling 1 s)
└── tests/ + .github/workflows/
```

## Installation

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows ; sinon : source .venv/bin/activate
pip install -e ".[dev]"

# Embeddings Gemini (recommandé) :
cp .env.example .env          # puis renseigner GEMINI_API_KEY
# OU mode 100 % hors-ligne (tire torch + modèle e5) :
pip install -e ".[local]"
```

## Démo live (ce que voit le jury)

```bash
# Terminal 1 — rejoue le scénario, met à jour report.json en continu
python -m benchmark.live

# Terminal 2 — sert le dashboard puis ouvrir http://localhost:8000/dashboard/
python -m http.server 8000
```

La courbe **rouge** (naïf) explose, la **verte** (MemBridge) reste plate ; l'encadré
affiche l'économie en tokens / € et le score des questions pièges.

## Autres commandes

```bash
# Rapport chiffré one-shot (écrit benchmark/results/report.json)
python -m benchmark.harness

# Démo console (économie + questions pièges réussies)
python -m demo.agent

# Tests
pytest -v

# Serveur MCP (stdio)
memory-mcp
```

## Les 4 outils MCP

| Outil | Description |
|-------|-------------|
| `memory_store(content, tags, session, turn, importance?)` | Stocke + embed + métadonnées |
| `memory_search(query, top_k, session?)` | Recherche **sémantique** (paraphrases !) + ranking |
| `memory_summarize(session, max_chars)` | Résumé **compressé** conservant les faits |
| `memory_stats()` | Tokens consommés, nb d'entrées, backend |

## CI

Le job `regression` et `finale-eval` utilisent les embeddings Gemini : ajouter le
secret **`GEMINI_API_KEY`** dans *Settings → Secrets → Actions*. Sans clé, ajouter
`pip install -e ".[local]"` à l'étape d'install pour activer le fallback local.

## Critères de merge (PR)

1. **Régression** : paraphrases top-1, isolation sessions, compression ≤ 25 %, économie ≥ 60 % sur 50 tours
2. **Finale cachée** : économie ≥ 70 %, seed dynamique, anti-hardcoding

## Organisateurs

Voir [ADMIN.md](ADMIN.md) pour configurer le dépôt privé et les secrets CI.

## Pitch

Voir [PITCH.md](PITCH.md).
