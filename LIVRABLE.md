# MemBridge — Livrable hackathon INTELO 2026

## Checklist jury

| Livrable | Statut | Commande |
|----------|--------|----------|
| Serveur MCP (4 outils) | OK | `python -m memory_mcp.server` |
| Embeddings sémantiques | OK | sentence-transformers |
| Résumé intelligent | OK | `memory_summarize` |
| Benchmark naïf vs MemBridge | OK | `python -m benchmark.harness` |
| Dashboard | OK | `python -m dashboard.server` |
| Agent démo | OK | `python demo/agent.py` |
| Questions pièges | OK | 10 dans `benchmark/trap_questions.json` |
| Claude Desktop | OK | `claude_desktop_config.example.json` |

## Résultats mesurés (50 tours)

- **Économie tokens : 72.1 %** (objectif ≥ 70 %)
- **Qualité pièges : 80–90 %**
- **Coût évité : ~0.04 €** par conversation simulée
- **Critère victoire : TRUE**

## Git

```powershell
git checkout develop
git pull origin develop
# vos changements MemBridge sont sur develop
```

## Démo 5 min

1. Ouvrir dashboard http://localhost:8080
2. Lancer `python -m benchmark.harness` si pas de report
3. Montrer courbes rouge/verte
4. Claude Desktop : question piège email
5. Graphe Ebbinghaus

## Fichiers clés

- `src/memory_mcp/` — serveur MCP
- `benchmark/results/report.json` — chiffres jury
- `DEMO.md` — config Claude
- `PITCH.md` — script présentation
