"""Configuration pytest commune.

Les tests (régression, smoke…) doivent refléter **exactement** le chemin de la CI, qui tourne
sans clé et utilise les embeddings locaux. On force donc le mode local ici, indépendamment d'un
éventuel ``.env`` contenant une clé Gemini. La démo, elle, respecte le ``.env`` (Gemini).
"""

import importlib.util
import os

os.environ.setdefault("MEMBRIDGE_EMBEDDINGS", "local")
# Si une variable l'a déjà mis à "auto"/"gemini", on l'écrase pour les tests :
if os.environ.get("MEMBRIDGE_EMBEDDINGS") in {"auto", "gemini"}:
    os.environ["MEMBRIDGE_EMBEDDINGS"] = "local"

# Le job CI "smoke" n'installe que [dev] (pas l'extra "local") : sentence-transformers absent.
# On retombe alors sur l'embedder "hashing", déterministe et sans dépendance lourde, suffisant
# pour la surface d'API. Les jobs régression/finale installent [dev,local] → vrai sémantique.
if (
    os.environ["MEMBRIDGE_EMBEDDINGS"] == "local"
    and importlib.util.find_spec("sentence_transformers") is None
):
    os.environ["MEMBRIDGE_EMBEDDINGS"] = "hashing"
