"""MemBridge — Serveur MCP de mémoire partagée pour agents IA (Hackathon INTELO2026)."""

# Charge automatiquement les variables d'environnement depuis un fichier .env (clé Gemini, etc.)
# dès l'import du package, sans jamais échouer si python-dotenv n'est pas installé.
try:
    from dotenv import load_dotenv as _load_dotenv

    _load_dotenv()
except Exception:  # pragma: no cover - dépendance optionnelle
    pass

__version__ = "0.2.0"
