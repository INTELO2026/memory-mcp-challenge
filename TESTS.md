# Guide des tests — MemBridge

Ce document explique comment lancer les tests en local, ce que chaque test vérifie,
et comment fonctionnent les tests automatiques (CI).

---

## 1. Préparation (une seule fois)

```bash
cd ~/Bureau/memory-mcp-challenge
python -m venv .venv
source .venv/bin/activate          # Windows : .venv\Scripts\activate
pip install -e ".[dev]"            # dépendances + outils de test
```

Clé API (recommandée pour passer 100 % des tests) : copier le modèle et coller ta clé.

```bash
cp .env.example .env
# puis éditer .env :  GEMINI_API_KEY=ta_cle
```

Sans clé, le projet bascule automatiquement sur un modèle local (MiniLM) : tout
fonctionne sauf un cas de paraphrase pure (voir §5).

Repli local optionnel (hors-ligne, sans clé) :

```bash
pip install -e ".[local]"          # installe sentence-transformers (lourd : torch)
```

---

## 2. Lancer les tests en local

Tous les tests :

```bash
MEMBRIDGE_EMBEDDER=gemini PYTHONPATH=src:. pytest tests/ -v
```

Par fichier :

```bash
pytest tests/test_smoke.py -v          # API + intégrité
pytest tests/test_tools.py -v          # les 4 outils MCP
pytest tests/test_storage.py -v        # stockage + recherche sémantique
pytest tests/test_regression.py -v     # paraphrases, compression, plateau
```

Choisir le backend d'embeddings :

```bash
MEMBRIDGE_EMBEDDER=gemini  ...   # API Gemini (défaut si clé présente) -> 16/16
MEMBRIDGE_EMBEDDER=local   ...   # MiniLM local (sans clé) -> 15/16 (cf. §5)
MEMBRIDGE_EMBEDDER=hashing ...   # repli déterministe minimal
```

Vérifier quel backend est actif :

```bash
PYTHONPATH=src python -c "from memory_mcp.embeddings import get_embedder; print(get_embedder().name)"
```

---

## 3. Lint (comme la CI)

```bash
ruff check src tests benchmark demo
ruff format --check src tests benchmark demo
```

---

## 4. Benchmark + tableau de bord

Génère les mesures réelles et écrit `dashboard/results/report.json` :

```bash
MEMBRIDGE_EMBEDDER=gemini PYTHONPATH=src:. python -m benchmark.harness
```

Afficher le dashboard animé :

```bash
cd dashboard && python -m http.server 8000
# ouvrir http://localhost:8000
```

Lancer l'agent de démo (boucle store -> search/summarize -> LLM, avec questions pièges) :

```bash
MEMBRIDGE_EMBEDDER=gemini PYTHONPATH=src:. python -m demo.agent
```

---

## 5. Ce que vérifie chaque test

| Fichier | Test | Vérifie |
|---|---|---|
| `tests/test_smoke.py` | `test_integrity_marker` | marqueur d'intégrité du projet |
| | `test_tools_api_surface` | les 4 outils répondent (store/search/summarize/stats) |
| `tests/test_tools.py` | `test_memory_store` | stockage d'une entrée |
| | `test_memory_search_semantic` | recherche sémantique renvoie des résultats |
| | `test_memory_summarize_compresses` | le résumé compresse réellement |
| | `test_memory_stats` | les métriques sont exposées |
| `tests/test_storage.py` | `test_store_and_search_paraphrase` | paraphrase pure (« identité de l'interlocutrice » -> Marie Dupont) |
| | `test_list_session_ordered` | entrées triées par tour |
| | `test_count` | comptage des entrées |
| `tests/test_regression.py` | `test_semantic_paraphrase_top1` | 5 paraphrases sans mots-clés communs |
| | `test_session_isolation` | aucune fuite entre sessions |
| | `test_summarize_compression_on_long_session` | ratio de compression <= 0.25 |
| | `test_summarize_retains_critical_facts` | le résumé garde les faits clés (Marie, CTR) |
| | `test_savings_minimum_60pct_on_50_turns` | économie tokens >= 60 % |
| | `test_context_growth_plateau` | coût par tour stable (facteur <= 1.15) |
| | `test_search_empty_store` | recherche sur mémoire vide |

Note importante : `test_store_and_search_paraphrase` exige une vraie recherche
sémantique. Avec **Gemini** il passe (16/16). Avec le repli **local MiniLM**, ce
cas précis échoue (15/16) car la requête et la cible n'ont aucun mot en commun :
seule l'API gère cette paraphrase pure. C'est attendu et documenté.

---

## 6. Tests automatiques (CI GitHub Actions)

Définis dans `.github/workflows/ci.yml`, déclenchés sur push / pull request.
Quatre jobs en chaîne (chacun ne démarre que si le précédent est vert) :

```
lint  ->  smoke  ->  regression  ->  finale-eval (PR uniquement)
```

| Job | Rôle |
|---|---|
| `lint` | `ruff check` + `ruff format --check` |
| `smoke` | `tests/test_smoke.py` (démarrage + intégrité) |
| `regression` | `test_regression` + `test_storage` + `test_tools` |
| `finale-eval` | tests cachés du dépôt privé `INTELO2026/memory-mcp-eval`, avec un seed dynamique. La vraie note (tokens économisés + qualité maintenue). |

### Secrets nécessaires côté dépôt
- `GEMINI_API_KEY` (à ajouter dans *Settings -> Secrets -> Actions*) : sinon
  `regression` retombe sur le local et le cas paraphrase échoue.
- `EVAL_SEED` et `EVAL_REPO_PAT` : fournis par les organisateurs (job `finale-eval`).

### Important sur les PR depuis un fork
Une PR provenant d'un **fork** ne reçoit **pas** les secrets du dépôt cible
(sécurité GitHub), même après approbation. Donc, depuis un fork :
- `lint` et `smoke` passent,
- `regression` peut échouer (pas de clé -> repli local),
- `finale-eval` ne peut pas s'exécuter (secrets absents).

Pour une évaluation complète, l'équipe doit pousser une branche **directement dans
le dépôt de l'organisation** (où les secrets sont disponibles), puis ouvrir une PR
`develop -> main`.

---

## 7. Critères de succès (rappel du sujet)

| Axe | Objectif | Où c'est mesuré |
|---|---|---|
| Coût | >= 70 % d'économie de tokens | `benchmark.harness` (~80 % obtenu) |
| Qualité | questions pièges réussies | `evaluate_quality` (5/5) + paraphrases (6/6) |
| Plateau | coût par tour stable | `test_context_growth_plateau` (facteur ~1.1) |
| Compression | résumé compact | `test_summarize_*` (ratio ~0.05) |
