# MemBridge — Mémoire partagée pour agents IA

**Hackathon INTELO 2026 · LBS Lomé Business School**

> Serveur MCP de mémoire externe : stocke le contexte utile, le restitue à la demande, **réduit ≥ 70 % des tokens** sans rendre l'agent amnésique.

## Problème → Solution

| | Mode naïf | MemBridge |
|---|-----------|-----------|
| Contexte/tour | Tout l'historique (O(T²)) | Résumé + top-3 + 3 tours (~125 tok) |
| Qualité | OK mais coûteux | Maintenue via `memory_search` |
| Oubli | Troncature brutale | Ebbinghaus intelligent |

## Les 4 outils MCP

| Outil | Rôle |
|-------|------|
| `memory_store(content, tags)` | Stocke avec embeddings sémantiques |
| `memory_search(query, top_k)` | Recherche par similarité + Ebbinghaus |
| `memory_summarize(session)` | Résumé compressé extractif |
| `memory_stats()` | Tokens économisés, coût €, métriques |

## Installation

```powershell
cd "C:\Users\HP\Desktop\Projet\SEIC 2026\hck cursor"
python -m venv .venv
.\.venv\Scripts\pip install -e ".[dev]"
.\scripts\warmup.ps1
```

## Démarrage rapide

```powershell
# Tests
$env:PYTHONPATH="src"
.\.venv\Scripts\python -m pytest tests/test_smoke.py tests/test_tools.py -v

# Benchmark chiffré (→ benchmark/results/report.json)
$env:PYTHONPATH="src;."
.\.venv\Scripts\python -m benchmark.harness

# Agent démo support client
$env:PYTHONPATH="src;."
.\.venv\Scripts\python demo/agent.py

# Dashboard live
$env:PYTHONPATH="src;."
.\.venv\Scripts\python -m dashboard.server
# → http://localhost:8080

# Serveur MCP (Claude Desktop le lance automatiquement)
$env:PYTHONPATH="src"
.\.venv\Scripts\python -m memory_mcp.server
```

## Claude Desktop

Voir `claude_desktop_config.example.json` et `DEMO.md`.

## Architecture

```
Claude Desktop ↔ STDIO ↔ memory_mcp.server
                              ├── SQLite (~/.membridge/)
                              ├── sentence-transformers (384d)
                              ├── Ebbinghaus (rétention + purge)
                              └── Résumé incrémental
```

## Critères hackathon

- ✅ Réduction tokens ≥ 70 % (benchmark 50 tours)
- ✅ 10 questions pièges (qualité ≥ 80 %)
- ✅ Agent externe Claude Desktop connecté
- ✅ Dashboard courbes naïf vs MemBridge
- ✅ Oubli intelligent (Ebbinghaus)

## Branche Git

Travail sur `develop` → PR vers `main` quand CI vert.

## Équipe

3 personnes · Prototype + démo live · Benchmark chiffré
