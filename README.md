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

### Embeddings Gemini (recherche sémantique réelle)

La recherche utilise l'API Gemini (`gemini-embedding-001`). Définissez une clé,
sinon le serveur retombe automatiquement sur un embedding lexical local (utile
hors-ligne / en CI) :

```bash
export GEMINI_API_KEY="votre_clé"   # ou GOOGLE_API_KEY
# Optionnel : export GEMINI_EMBED_MODEL=gemini-embedding-001 ; export GEMINI_EMBED_DIM=768
```

## Utilisation

```bash
# Tests fumée (doivent passer)
pytest tests/test_smoke.py -v

# Tests régression (doivent passer pour merger)
PYTHONPATH=src:. pytest tests/test_regression.py tests/test_storage.py tests/test_tools.py tests/test_quality.py -v

# Benchmark complet (coût + qualité) → écrit benchmark/results/report.json
# Coût chiffré au tarif réel via models.dev (slug exact OU regex ; slug
# introuvable → repli Sonnet récent). Usage : [tours] [slug1,slug2,...]
python -m benchmark.harness                                   # 50 tours, claude-opus-4-8
python -m benchmark.harness 50 anthropic/claude-sonnet-4-6    # un modèle
python -m benchmark.harness 50 "claude-opus-4-8,claude-sonnet-4-6,gemini-2.0-flash"  # multi-modèles, coûts additionnés
python -m benchmark.harness 50 "opus.*4.8"                    # slug par expression régulière

# Démo agent : 40 tours puis questions pièges via memory_search
python -m demo.agent                        # ou : python -m demo.agent 50 support claude-opus-4-8

# Serveur MCP (stdio) / HTTP+SSE
# Chatbot IA : la clé reste côté serveur (PowerShell : $env:GEMINI_API_KEY="...")
# Modèle par défaut : gemma-4-31b-it (surcharge : MEMORY_CHAT_MODEL)
memory-mcp
memory-mcp-http        # écoute sur http://localhost:8010
# Persistance complète sur disque (~/.memory_mcp/) :
#   memory.db  — entrées mémoire (MEMORY_DB_PATH)
#   stats.json — TOUS les compteurs (tokens économisés, appels store/search/
#                summarize, courbes temporelles, gain %, modèle actif…)
#                (MEMORY_STATS_PATH)
# Tout est rechargé au redémarrage. Vérifiez via GET /health (db_path,
# stats_path, entries_count). POST /api/v1/reset remet les compteurs à zéro
# par défaut ; ?clear=true vide aussi la mémoire.
# (Astuce dev : lancer uvicorn avec --reload pour recharger le code modifié.)

# Tableau de bord LIVE (données réelles du MCP, aucune simulation)
#   1) lancer le serveur :  memory-mcp-http
#   2) servir le dashboard : python -m http.server -d dashboard 8080
#   3) ouvrir http://localhost:8080
# Affiche : le GAIN DE TOKENS en % (objectif ≥ 70 %, vert si atteint), le coût
# attendu (mode naïf) vs réel (MemBridge) vs économie (chiffres + barres), et une
# COURBE D'UTILISATION dans le temps (naïf vs MemBridge cumulés + gain %),
# agrégeable par heure / jour / mois (GET /api/v1/timeseries?bucket=…).
# Par défaut : modèles tendance (opus, sonnet, gpt 5.5, gemini) + tout modèle
# dont la consommation MCP est non nulle. Case « Afficher tous les modèles » →
# catalogue complet models.dev. Recherche (regex acceptée) pour filtrer.
# Le gain croît avec le nombre de tours : il dépasse 70 % sur une vraie
# conversation (mémoire ciblée vs historique complet renvoyé à chaque tour).
# Le coin inférieur droit contient aussi un chatbot IA qui répond depuis la
# mémoire via POST /api/v1/chat, sans exposer la clé API au navigateur.
```

## Les trois chantiers (sprints du sujet §3.4)

| Chantier | État | Où |
|----------|------|----|
| **Embeddings** — vrais embeddings sémantiques | ✅ Gemini + repli lexical | `src/memory_mcp/storage.py` |
| **Résumé intelligent** — compresser sans perdre les faits | ✅ extractif, garde tous les faits porteurs d'info | `src/memory_mcp/tools.py` |
| **Benchmark** — contexte stable + comparaison fiable | ✅ courbes par tour, questions pièges, coût €, `report.json` | `benchmark/` + `dashboard/` |

## Les outils MCP

| Outil | Description |
|-------|-------------|
| `memory_store(content, tags, key?, model?)` | Stocke un fragment. `key` (optionnel) = étiquette stable pour un accès direct ; `model` = slug du modèle IA de l'agent |
| `memory_keys(session?)` | **Index clé→valeur** de toute la mémoire : retrouve l'info directement, sans recherche floue |
| `memory_search(query, top_k)` | Recherche **sémantique** (paraphrases !) |
| `memory_summarize(session)` | Résumé **compressé** conservant les faits |
| `memory_stats(model?)` | Tokens consommés + coût ; à défaut de `model`, utilise celui déclaré |

> **Quel modèle est utilisé ?** Les outils MCP n'ont pas de canal natif pour
> connaître le modèle de l'agent appelant. L'agent le **déclare** donc via
> `memory_store(model="claude-opus-4-8")` ; le serveur le mémorise (`active_model`)
> et s'en sert pour chiffrer le coût dans `memory_stats` et le tableau de bord.
> Si rien n'est déclaré, un modèle récent par défaut est utilisé (clairement
> signalé). Le tableau de bord affiche le **coût attendu (mode naïf) vs économie**
> en chiffres puis en graphe, pour ce modèle.

## Critères de merge (PR)

1. **Régression** : paraphrases top-1, isolation sessions, compression ≤ 25 %, économie ≥ 60 % sur 50 tours
2. **Finale cachée** : économie ≥ 70 %, seed dynamique, anti-hardcoding

## Organisateurs

Voir [ADMIN.md](ADMIN.md) pour configurer le dépôt privé et les secrets CI.

## Pitch

Voir [PITCH.md](PITCH.md).
