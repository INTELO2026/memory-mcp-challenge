# MemBridge — warmup avant démo
$root = "C:\Users\HP\Desktop\Projet\SEIC 2026\hck cursor"
Set-Location $root
$env:PYTHONPATH = "src"
$env:MEMBRIDGE_PERSIST = "1"
Write-Host "Pre-chargement du modele (1-2 min la 1ere fois)..."
& "$root\.venv\Scripts\python.exe" "$root\scripts\warmup.py"
Write-Host "Done. Redemarrez Claude Desktop si besoin."
