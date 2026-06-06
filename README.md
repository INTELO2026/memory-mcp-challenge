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

## Structure

```
memory-mcp-challenge/
├── src/memory_mcp/     # Serveur MCP + 4 outils
├── benchmark/          # Harnais naïf vs mémoire
├── demo/               # Agent de démo (stub)
├── dashboard/          # Visualisation benchmark
├── tests/
│   ├── test_smoke.py       # API OK
│   └── test_regression.py  # Barre finale (dur)
└── .github/workflows/  # CI multi-niveaux
```

## Installation

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -e ".[dev]"
```

> Au premier appel de recherche/stockage, le modèle d'embeddings (BGE-M3) est
> téléchargé puis mis en cache. Pour des tests rapides sans modèle, exporter
> `MEMORY_EMBEDDER=bow` (repli lexical).

## Utilisation

```bash
# Tests fumée (doivent passer)
pytest tests/test_smoke.py -v

# Tests régression (doivent passer pour merger)
PYTHONPATH=src:. pytest tests/test_regression.py tests/test_storage.py tests/test_tools.py -v

# Benchmark
python -m benchmark.harness

# Serveur MCP
memory-mcp

# Vérifier qu'un agent externe peut se connecter (client MCP en stdio)
python scripts/mcp_smoke_client.py
```

## Les 4 outils MCP

| Outil | Description |
|-------|-------------|
| `memory_store(content, tags, session, turn)` | Stocke un fragment de mémoire |
| `memory_search(query, top_k, session)` | Recherche **sémantique** (paraphrases !) |
| `memory_summarize(session, max_chars)` | Résumé **compressé** conservant les faits |
| `memory_stats()` | Tokens consommés |

## Connexion d'un agent externe (MCP)

Le serveur parle le protocole MCP en **stdio** : n'importe quel client MCP peut
le lancer et appeler les outils. Le script `scripts/mcp_smoke_client.py` en est
la preuve (il démarre le serveur, liste les outils, appelle les quatre).

Exemple de configuration pour un client type (Claude Desktop / agent MCP) :

```json
{
  "mcpServers": {
    "memory-mcp": {
      "command": "python",
      "args": ["-m", "memory_mcp.server"]
    }
  }
}
```

Variables d'environnement reconnues par le serveur :

| Variable | Effet |
|----------|-------|
| `MEMORY_EMBEDDER` | `auto` (défaut), `st` (sentence-transformers), `bow` (repli rapide) |
| `MEMORY_EMBEDDER_MODEL` | Nom du modèle d'embeddings (défaut : BGE-M3) |
| `MEMORY_DB_PATH` | Chemin SQLite pour **persister** la mémoire entre sessions (défaut : RAM) |

## Critères de merge (PR)

1. **Régression** : paraphrases top-1, isolation sessions, compression ≤ 25 %, économie ≥ 60 % sur 50 tours
2. **Finale cachée** : économie ≥ 70 %, seed dynamique, anti-hardcoding

## Organisateurs

Voir [ADMIN.md](ADMIN.md) pour configurer le dépôt privé et les secrets CI.

## Pitch

Voir [PITCH.md](PITCH.md).
