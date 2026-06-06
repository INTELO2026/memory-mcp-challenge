"""Pré-charge le modèle d'embeddings avant la démo Claude Desktop."""
from memory_mcp.embeddings import encode
from memory_mcp.tools import MemoryTools

print("Chargement modèle embeddings...")
encode("warmup test")
print("OK — modèle prêt.")

tools = MemoryTools()
tools.memory_store("warmup demo", session="warmup", turn=0)
print("OK — memory_store fonctionne.")
print("Vous pouvez lancer Claude Desktop.")
