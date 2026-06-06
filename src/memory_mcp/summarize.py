"""Résumé compressé : heuristique tag-aware (CI) + Gemini via API (démo)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from memory_mcp.config import get_settings, is_llm_configured
from memory_mcp.llm_client import generate_text
from memory_mcp.stats import count_tokens, truncate_to_tokens

if TYPE_CHECKING:
    from memory_mcp.storage import MemoryEntry

NOISE_TAG = "noise"
FACT_TAG = "fact"

COMPRESSOR_PROMPT = (
    "Tu es un compresseur de mémoire. Résume les échanges suivants en conservant "
    "TOUS les faits précis (noms, chiffres, décisions, préférences). "
    "Maximum {max_tokens} tokens. Réponse en français, sans introduction."
)


def _strip_role_prefix(content: str) -> str:
    for prefix in ("user: ", "assistant: ", "User: ", "Assistant: "):
        if content.startswith(prefix):
            return content[len(prefix) :].strip()
    return content.strip()


def _heuristic_summary(entries: list[MemoryEntry], max_tokens: int) -> str:
    """Compression sans LLM — priorise les faits tagués, agrège le bruit."""
    max_chars = max_tokens * 4
    facts = [e for e in entries if FACT_TAG in e.tags]
    noise = [e for e in entries if NOISE_TAG in e.tags]
    other = [e for e in entries if e not in facts and e not in noise]

    lines: list[str] = []

    for entry in facts:
        lines.append(_strip_role_prefix(entry.content))

    for entry in other[-1:]:
        text = _strip_role_prefix(entry.content)
        if len(text) > 80:
            text = text[:77] + "..."
        lines.append(text)

    if noise:
        lines.append(f"[{len(noise)} échanges hors-sujet omis]")

    if not lines:
        return ""

    summary = " | ".join(lines)
    if len(summary) > max_chars:
        kept: list[str] = []
        used = 0
        sep = " | "
        for line in lines:
            extra = len(line) if not kept else len(sep) + len(line)
            if used + extra > max_chars - 3:
                break
            kept.append(line)
            used += extra
        summary = sep.join(kept) if kept else lines[0][: max_chars - 3] + "..."

    return truncate_to_tokens(summary, max_tokens)


def _llm_summary(source_text: str, max_tokens: int) -> str | None:
    """Appelle le LLM si activé via MEMBRIDGE_USE_LLM."""
    settings = get_settings()
    if not settings.use_llm or not is_llm_configured():
        return None

    try:
        prompt = COMPRESSOR_PROMPT.format(max_tokens=max_tokens) + f"\n\n{source_text}"
        text = generate_text(prompt, max_output_tokens=max_tokens)
        return truncate_to_tokens(text, max_tokens)
    except Exception:
        return None


def build_summary(
    entries: list[MemoryEntry],
    max_tokens: int | None = None,
    use_llm: bool = False,
) -> str:
    """Résumé hybride — retourne le texte compressé."""
    return build_summary_report(entries, max_tokens=max_tokens, use_llm=use_llm)["summary"]


def build_summary_report(
    entries: list[MemoryEntry],
    max_tokens: int | None = None,
    use_llm: bool = False,
) -> dict:
    """Rapport complet de compression (cerveau memory_summarize)."""
    if not entries:
        return {
            "summary": "",
            "source_turns": 0,
            "compressed_chars": 0,
            "source_tokens": 0,
            "summary_tokens": 0,
            "compression_ratio": 0.0,
            "facts_preserved": 0,
            "noise_omitted": 0,
            "method": "none",
        }

    if max_tokens is None:
        max_tokens = get_settings().summary_max_tokens

    source_text = "".join(e.content for e in entries)
    source_tokens = count_tokens(source_text)
    facts = [e for e in entries if FACT_TAG in e.tags]
    noise = [e for e in entries if NOISE_TAG in e.tags]

    heuristic = _heuristic_summary(entries, max_tokens)
    method = "heuristic"
    summary = heuristic

    if use_llm and len(entries) >= 8:
        source_lines = "\n".join(
            f"[t{e.turn}] {_strip_role_prefix(e.content)}" for e in entries[:80]
        )
        llm = _llm_summary(source_lines, max_tokens)
        if llm:
            summary = llm
            method = "llm"

    summary_tokens = count_tokens(summary)
    return {
        "summary": summary,
        "source_turns": len(entries),
        "compressed_chars": len(summary),
        "source_tokens": source_tokens,
        "summary_tokens": summary_tokens,
        "compression_ratio": round(summary_tokens / source_tokens, 4) if source_tokens else 0.0,
        "facts_preserved": len(facts),
        "noise_omitted": len(noise),
        "method": method,
    }
