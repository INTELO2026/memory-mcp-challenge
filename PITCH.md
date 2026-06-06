# MemBridge — Pitch jury (5 min)

## 1. Problème (30 s)

Les agents IA renvoient tout l'historique à chaque tour → coût **quadratique**, latence, saturation contexte. Tronquer = amnésie.

## 2. Solution — serveur MCP mémoire (45 s)

4 outils : `memory_store`, `memory_search`, `memory_summarize`, `memory_stats`.

Boucle agent : **stocker → résumer → chercher → répondre** au lieu de renvoyer 50 tours.

## 3. Preuve chiffrée — démo live (90 s) ★ money shot

```bash
python -m demo.presentation
python dashboard/server.py --open
```

Ouvrir **/dashboard/live.html** :

1. **Conversation MCP live** — chaque tour appelle `store → summarize → search` (API `/api/live/sessions`)
2. Compteurs **rouge** (naïf) et **vert** (MemBridge) calculés en direct, pas en dur
3. Question piège → `memory_search` top-1 → **9/9** possible
4. **/dashboard/demo.html** — mode manuel tour par tour

## Workflow Git (§7 sujet)

```bash
git checkout develop
# ... commits ...
git push -u origin develop
gh pr create --base main --head develop
```

CI requise pour merger : `lint` → `smoke` → `regression` → `finale-eval` (tests cachés sur PR).
Vérifier en local : `python scripts/run_ci_local.py`

## 4. Deux axes de succès (45 s) — §2 et §4 sujet

| Axe | Résultat |
|-----|----------|
| **Coût** | **≈ 71 %** d'économie sur 50 tours |
| **Qualité** | **9/9** pièges MemBridge — qualité intégralement maintenue |

Comparaison bi-mode : naïf garde l'historique complet, MemBridge compresse sans perdre les faits.

**Ranking honnête & généralisable** : aucune réponse n'est codée en dur. Le classement combine
embeddings sémantiques + recouvrement lexical + détection d'intention (email / montant / date /
identifiant / entité) + hiérarchie (récence × importance × fréquence) + préférence à la source
(l'utilisateur prime sur la confirmation de l'assistant). → robuste au seed caché du `finale-eval`.

## 5. Au-delà du minimum — bonus §10 (60 s)

| Piste | Démo |
|-------|------|
| **Mémoire partagée** | Agent support écrit → superviseur relit (`python -m demo.multi_agent`) |
| **Hiérarchie pertinence** | Sémantique + récence + importance + fréquence d'accès |
| **Oubli intelligent** | `prune_stale()` archive les exchanges obsolètes |
| **Persistance** | SQLite sur disque — contexte retrouvé J+1 (`python -m demo.persistence`) |

Page **/dashboard/bonus.html**

## 6. Stack & CI (30 s)

- Python, SDK MCP, SQLite + FAISS + sentence-transformers
- CI : lint, smoke, regression (14 tests), finale-eval conditionnelle
- Agent externe : `python -m memory_mcp.server` (stdio MCP)

## 7. Conclusion (20 s)

MemBridge prouve qu'une **mémoire externe MCP** divise les tokens par ~3 **sans amnésie** — mesurable, rejouable, extensible multi-agents.
