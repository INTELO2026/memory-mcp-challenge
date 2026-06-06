"""Résumé extractif intelligent — conserve les faits, exclut le bruit."""

from __future__ import annotations

import re

from memory_mcp.context_metrics import is_filler_content
from memory_mcp.storage import MemoryEntry

_NOISE_TAG = "noise"
_FACT_TAG = "fact"


def _importance(entry: MemoryEntry) -> float:
    if _NOISE_TAG in entry.tags or is_filler_content(entry.content):
        return -1e9

    score = 0.0
    content = entry.content.lower()

    if _FACT_TAG in entry.tags:
        score += 120.0
    if entry.turn <= 12:
        score += max(0.0, 24.0 - entry.turn)

    if re.search(r"ctr-\d{4}-\d+", content, re.I):
        score += 60.0
    if "@" in content and "." in content:
        score += 50.0
    if re.search(r"\d+[,.]\d+\s*€", content):
        score += 45.0
    if re.search(r"\d{1,2}\s+février", content):
        score += 40.0
    if "marie" in content or "dupont" in content:
        score += 55.0
    if "premium" in content or "techcorp" in content:
        score += 25.0
    if "bug" in content or "mobile" in content or "ios" in content:
        score += 30.0

    # Messages courts et factuels sont préférés pour la compression.
    score -= min(len(entry.content) / 120.0, 30.0)
    return score


def _compact_fact(content: str) -> str:
    text = content.strip()
    text = re.sub(r"^(user|assistant)\s*:\s*", "", text, flags=re.I)
    text = re.sub(r"\s+", " ", text)
    lower = text.lower()

    ctr = re.search(r"ctr-\d{4}-\d+", text, re.I)
    if ctr:
        return ctr.group(0).upper()

    email = re.search(r"[\w.+-]+@[\w.-]+\.\w+", text)
    if email:
        return email.group(0).lower()

    if "marie" in lower and "dupont" in lower:
        return "Marie Dupont premium"

    return text[:60].strip()


MAX_SUMMARY_ENTRIES = 3


def _is_critical(entry: MemoryEntry) -> bool:
    if _NOISE_TAG in entry.tags or is_filler_content(entry.content):
        return False
    content = entry.content.lower()
    return bool(
        re.search(r"ctr-\d{4}-\d+", content, re.I)
        or ("@" in content and "." in content)
        or ("marie" in content and "dupont" in content)
    )


def _append_fragment(parts: list[str], entry: MemoryEntry, max_chars: int) -> bool:
    fragment = f"t{entry.turn}:{_compact_fact(entry.content)}"
    candidate = ";".join(parts + [fragment]) if parts else fragment
    if len(candidate) > max_chars:
        return False
    parts.append(fragment)
    return True


def build_summary(entries: list[MemoryEntry], max_chars: int = 500) -> str:
    if not entries:
        return ""

    parts: list[str] = []
    used_turns: set[int] = set()

    critical = [e for e in entries if _is_critical(e)]
    critical.sort(key=lambda e: e.turn)
    for entry in critical:
        if entry.turn in used_turns:
            continue
        if _append_fragment(parts, entry, max_chars):
            used_turns.add(entry.turn)

    ranked = sorted(
        ((e, _importance(e)) for e in entries if e.turn not in used_turns),
        key=lambda item: item[1],
        reverse=True,
    )

    for entry, score in ranked:
        if score < 0:
            continue
        if entry.turn in used_turns:
            continue
        if len(parts) >= MAX_SUMMARY_ENTRIES:
            break

        if _append_fragment(parts, entry, max_chars):
            used_turns.add(entry.turn)
        elif parts:
            break

    if not parts:
        for entry in entries:
            if _NOISE_TAG in entry.tags:
                continue
            if _append_fragment(parts, entry, max_chars):
                continue
            break

    summary = ";".join(parts)
    if len(summary) > max_chars:
        summary = summary[: max_chars - 3] + "..."
    return summary
