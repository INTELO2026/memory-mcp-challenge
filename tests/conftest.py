"""Configuration pytest commune.

Les tests (régression, smoke…) doivent refléter **exactement** le chemin de la CI, qui tourne
sans clé et utilise les embeddings locaux. On force donc le mode local ici, indépendamment d'un
éventuel ``.env`` contenant une clé Gemini. La démo, elle, respecte le ``.env`` (Gemini).
"""

import os

os.environ.setdefault("MEMBRIDGE_EMBEDDINGS", "local")
# Si une variable l'a déjà mis à "auto"/"gemini", on l'écrase pour les tests :
if os.environ.get("MEMBRIDGE_EMBEDDINGS") in {"auto", "gemini"}:
    os.environ["MEMBRIDGE_EMBEDDINGS"] = "local"
