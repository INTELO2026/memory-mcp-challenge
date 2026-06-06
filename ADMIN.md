# Guide organisateurs — Finale Memory MCP

## Architecture anti-triche

| Couche | Visible participants | Rôle |
|--------|---------------------|------|
| `tests/test_smoke.py` | Oui | Vérifie que l'API existe |
| `tests/test_regression.py` | Oui | Barre élevée — paraphrases, bruit, compression |
| `INTELO2026/memory-mcp-eval` | **Non (privé)** | Seuils stricts + seed dynamique + anti-triche |

## Configuration GitHub (une fois)

### 1. Dépôt privé `memory-mcp-eval`

```bash
cd eval-private
git init
git add .
git commit -m "Tests cachés finale memory-mcp"
gh repo create INTELO2026/memory-mcp-eval --private --source=. --push
```

### 2. Secrets repo `memory-mcp-challenge`

Dans **Settings → Secrets and variables → Actions** du repo (ou org si admin) :

| Secret | Valeur |
|--------|--------|
| `EVAL_REPO_PAT` | PAT fine-grained, accès lecture sur `memory-mcp-eval` uniquement |
| `EVAL_SEED` | Entier aléatoire — **ne pas communiquer aux équipes** |

```bash
gh secret set EVAL_SEED --repo INTELO2026/memory-mcp-challenge --body "847291"
gh secret set EVAL_REPO_PAT --repo INTELO2026/memory-mcp-challenge --body "ghp_..."
```

### 3. Branch protection sur `main`

Exiger les checks :
- `lint`
- `smoke`
- `regression`
- `finale-eval` (sur PR)

## Tester localement comme la CI

```bash
# Tests publics (régression doit échouer sur le squelette)
PYTHONPATH=src:. pytest tests/test_regression.py -v

# Tests cachés (organisateurs)
FINALE_EVAL=1 EVAL_SEED=847291 PYTHONPATH=src:. pytest eval-private/hidden_tests/ -v
```

## Modifier les seuils

- Seuils **publics** : `tests/test_regression.py`
- Seuils **cachés** : pousser sur `memory-mcp-eval` (les équipes ne voient pas le diff)

## Rotation du seed entre sessions

Changer `EVAL_SEED` dans les secrets org invalide toute triche hardcodée.
