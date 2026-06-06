# MemBridge — FINALISÉ ✅

## Avant la démo (2 min)

```powershell
cd "C:\Users\HP\Desktop\Projet\SEIC 2026\hck cursor"
.\scripts\warmup.ps1
```

Puis **quitter et relancer Claude Desktop**.

## Config Claude (déjà en place)

Fichier : `%LOCALAPPDATA%\Packages\Claude_pzs8sxrjxfjjc\LocalCache\Roaming\Claude\claude_desktop_config.json`

→ Pointe vers `hck cursor` + `memory_mcp.server` (PAS HCK gemini).

## Prompt démo jury

```
Tu es connecté au MCP MemBridge. Exécute dans l'ordre :

1. memory_store — session "demo", tags ["client","fact"], content :
   "Marie Dupont, premium TechCorp. Email: marie.dupont@email.fr. Contrat: CTR-2024-8847. Facture mars: 149,90€ au lieu de 99,90€."

2. memory_search — session "demo", query "email du client", top_k=3

3. memory_summarize — session "demo"

4. memory_stats

Question piège : "Quel était mon email au début ?" → réponds via memory_search uniquement.
Affiche les JSON de chaque outil.
```

## Chiffres benchmark

```powershell
$env:PYTHONPATH="src;."
.\.venv\Scripts\python -m benchmark.harness
```

→ **~72 % d'économie tokens** sur 50 tours.

## Dashboard

```powershell
$env:PYTHONPATH="src;."
.\.venv\Scripts\python -m dashboard.server
```

→ http://localhost:8080

## Logs si problème

```
type "%LOCALAPPDATA%\Packages\Claude_pzs8sxrjxfjjc\LocalCache\Roaming\Claude\logs\mcp-server-membridge.log"
```

Doit afficher : `hck cursor` et `[membridge] stdio transport ready`
