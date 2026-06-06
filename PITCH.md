# MemBridge — Pitch jury (5 min)

## Accroche (30 s)

Les agents IA renvoient **tout l'historique** à chaque appel → coût **O(T²)** en tokens.
**MemBridge** est un serveur MCP qui sert de **mémoire externe intelligente** : l'agent ne récupère que le pertinent.

## Démo live (3 min)

1. **Dashboard** : deux courbes — rouge (naïf) monte, verte (MemBridge) plate
2. **Chiffre** : « **72 % de tokens économisés** = X € évités »
3. **Claude Desktop** : question piège « Quel était l'email du client au tour 9 ? » → `memory_search` → réponse correcte
4. **Ebbinghaus** : graphe de rétention — souvenirs forts vs faibles

## Preuves mesurées

- Benchmark reproductible : `python -m benchmark.harness`
- 50 tours · mode naïf vs MemBridge · 10 questions pièges
- Objectif jury : **≥ 70 % économie + qualité maintenue**

## Différenciation

| Feature | MemBridge |
|---------|-----------|
| Protocole | MCP open-standard (agnostique LLM) |
| Recherche | Embeddings sémantiques (paraphrases) |
| Compression | Résumé incrémental O(1) |
| Oubli | Courbe d'Ebbinghaus (1885) |
| Multi-agent | Mémoire partagée par session |

## Stack

Python · MCP SDK · SQLite · sentence-transformers · Dashboard HTML

## Closing (30 s)

MemBridge prouve qu'on peut **diviser les coûts par 3+** sans sacrifier la mémoire.
Compatible avec **n'importe quel agent MCP** — Claude, Cursor, custom.
