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

# Config MCP pour Cursor / Claude (étape jury)
python scripts/setup_mcp_config.py
python scripts/test_mcp_connection.py
```

## Connecter un agent externe (MCP)

Après `pip install -e .` :

```bash
python scripts/setup_mcp_config.py
```

Cela écrit `.cursor/mcp.json` (Cursor) et `config/claude_desktop_config.generated.json` (Claude Desktop).

Puis **redémarrez Cursor** → serveur **membridge** avec les 4 outils.

Vérifier la connexion :

```bash
python scripts/test_mcp_connection.py
```

Vous devez voir : `memory_store`, `memory_search`, `memory_summarize`, `memory_stats`.

## Les 4 outils MCP

| Outil | Description |
|-------|-------------|
| `memory_store(content, tags)` | Stocke un fragment de mémoire |
| `memory_search(query, top_k)` | Recherche **sémantique** (paraphrases !) |
| `memory_summarize(session)` | Résumé **compressé** conservant les faits |
| `memory_stats()` | Tokens consommés |

## Critères de merge (PR)

1. **Régression** : paraphrases top-1, isolation sessions, compression ≤ 25 %, économie ≥ 60 % sur 50 tours
2. **Finale cachée** : économie ≥ 70 %, seed dynamique, anti-hardcoding

## Organisateurs

Voir [ADMIN.md](ADMIN.md) pour configurer le dépôt privé et les secrets CI.

## Pitch

Voir [PITCH.md](PITCH.md).
