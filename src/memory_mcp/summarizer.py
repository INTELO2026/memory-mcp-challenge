"""Pipeline résumé extractif (0 token LLM) + consolidation incrémentale."""

from __future__ import annotations

import math
import re
from datetime import datetime, timezone

import numpy as np

from memory_mcp.embeddings import cosine_similarity
from memory_mcp.llm_summarizer import llm_summarize_available, summarize_with_claude
from memory_mcp.storage import MemoryEntry, MemoryStore

CLUSTER_THRESHOLD = 0.85
ALPHA, BETA, GAMMA = 0.4, 0.4, 0.2
_NAME_RE = re.compile(r"\b([A-ZÀ-Ü][a-zà-ü]+\s+[A-ZÀ-Ü][a-zà-ü]+)\b")
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_REF_RE = re.compile(r"[A-Z]{2,}-\d{4}-\d+", re.I)


def _entry_score(entry: MemoryEntry, now: datetime) -> float:
    created = entry.created_at or now
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    hours = max(0.0, (now - created).total_seconds() / 3600.0)
    recency = math.exp(-0.05 * hours)
    freq = min(entry.access_count / 5.0, 1.0)
    early_boost = 1.0 if entry.turn <= 10 else 0.85
    return early_boost * (ALPHA * recency + BETA * entry.importance + GAMMA * freq)


def _cluster_deduplicate(
    entries: list[MemoryEntry], store: MemoryStore, top_pct: float = 0.3
) -> list[MemoryEntry]:
    if not entries:
        return []

    scored = sorted(
        ((_entry_score(e, datetime.now(timezone.utc)), e) for e in entries),
        key=lambda x: x[0],
        reverse=True,
    )
    keep_count = max(3, int(len(scored) * top_pct))
    candidates = [e for _, e in scored[: max(keep_count, len(scored))]]

    selected: list[MemoryEntry] = []
    selected_vecs: list[np.ndarray] = []

    for entry in candidates:
        vec = store.get_embedding(entry.id)
        if vec is None:
            continue
        redundant = False
        for svec in selected_vecs:
            if cosine_similarity(vec, svec) > CLUSTER_THRESHOLD:
                redundant = True
                break
        if not redundant:
            selected.append(entry)
            selected_vecs.append(vec)
        if len(selected) >= keep_count:
            break

    return sorted(selected, key=lambda e: e.turn)


def _ensure_critical_facts(
    entries: list[MemoryEntry], selected: list[MemoryEntry]
) -> list[MemoryEntry]:
    """Garantit la présence des faits à haute importance."""
    selected_ids = {e.id for e in selected}
    critical = sorted(
        [e for e in entries if e.importance >= 0.6 or e.turn <= 10],
        key=lambda e: (-e.importance, e.turn),
    )
    for entry in critical[:5]:
        if entry.id not in selected_ids:
            selected.append(entry)
            selected_ids.add(entry.id)
    return sorted(selected, key=lambda e: e.turn)


def _extract_entities(entries: list[MemoryEntry]) -> dict[str, str]:
    entities: dict[str, str] = {}
    for entry in entries:
        for match in _NAME_RE.finditer(entry.content):
            entities.setdefault("client", match.group(1))
        for match in _EMAIL_RE.finditer(entry.content):
            entities.setdefault("email", match.group(0))
        for match in _REF_RE.finditer(entry.content):
            entities.setdefault("contrat", match.group(0))
    return entities


def _structured_from_entries(entries: list[MemoryEntry], previous: str = "") -> dict:
    fact_entries = sorted([e for e in entries if "fact" in e.tags], key=lambda e: e.turn)
    critical = sorted(entries, key=lambda e: (-e.importance, e.turn))[:6]
    ordered: list[MemoryEntry] = []
    seen: set[int] = set()
    for e in fact_entries + critical:
        if e.id not in seen:
            ordered.append(e)
            seen.add(e.id)

    key_facts = [e.content.replace("\n", " ").strip()[:90] for e in ordered[:5]]
    anchors = []
    if previous:
        anchors.append(previous[:80])
    for entry in ordered[:3]:
        anchors.append(f"t{entry.turn}: {entry.content[:50]}")

    return {
        "key_facts": key_facts,
        "entities": _extract_entities(ordered),
        "open_questions": [],
        "context_anchors": anchors,
    }


def _truncate_to_tokens(text: str, max_tokens: int = 300) -> str:
    """Limite le résumé à max_tokens (master prompt §13 risque 3)."""
    from memory_mcp.stats import count_tokens

    if count_tokens(text) <= max_tokens:
        return text
    words = text.split()
    lo, hi = 0, len(words)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        chunk = " ".join(words[:mid])
        if count_tokens(chunk) <= max_tokens:
            lo = mid
        else:
            hi = mid - 1
    trimmed = " ".join(words[:lo])
    return trimmed + "..." if lo < len(words) else trimmed


def _format_structured(structured: dict, max_chars: int = 500) -> str:
    parts: list[str] = []
    for fact in structured.get("key_facts", [])[:4]:
        parts.append(fact[:70])
    entities = structured.get("entities") or {}
    if entities:
        parts.append(" | ".join(f"{k}: {v}" for k, v in list(entities.items())[:4]))
    text = " | ".join(parts)
    if len(text) > max_chars:
        text = text[: max_chars - 3] + "..."
    return _truncate_to_tokens(text, max_tokens=300)


def build_structured_summary(
    store: MemoryStore,
    session: str,
    max_chars: int = 500,
    include_rolling: bool = True,
    use_llm: bool = True,
) -> tuple[str, dict, int]:
    """Résumé texte + JSON structuré (LLM optionnel si ANTHROPIC_API_KEY)."""
    entries = store.list_session(session)
    previous = store.get_session_summary(session) if include_rolling else ""
    if not entries and not previous:
        empty = {"key_facts": [], "entities": {}, "open_questions": [], "context_anchors": []}
        return "", empty, 0

    structured = _structured_from_entries(entries, previous=previous)
    subset = "\n".join(e.content for e in entries[-8:])
    if use_llm and llm_summarize_available():
        llm_result = summarize_with_claude(subset, previous_summary=previous)
        if llm_result:
            structured = {
                "key_facts": llm_result.get("key_facts", structured["key_facts"]),
                "entities": llm_result.get("entities", structured["entities"]),
                "open_questions": llm_result.get("open_questions", []),
                "context_anchors": llm_result.get("context_anchors", structured["context_anchors"]),
            }

    summary, source_turns = build_extractive_summary(
        store, session, max_chars=max_chars, include_rolling=include_rolling
    )
    formatted = _format_structured(structured, max_chars=max_chars)
    if formatted:
        summary = formatted
    summary = _truncate_to_tokens(summary, max_tokens=300)

    return summary, structured, source_turns


def build_extractive_summary(
    store: MemoryStore,
    session: str,
    max_chars: int = 500,
    include_rolling: bool = True,
) -> tuple[str, int]:
    """
    Étape 1 extractive locale (0 token LLM).
    Retourne (résumé, nombre de tours sources).
    """
    entries = store.list_session(session)
    if not entries:
        rolling = store.get_session_summary(session)
        return rolling, 0

    previous = store.get_session_summary(session) if include_rolling else ""
    fact_entries = sorted([e for e in entries if "fact" in e.tags], key=lambda e: e.turn)
    selected = _cluster_deduplicate(entries, store, top_pct=0.25)
    selected = _ensure_critical_facts(entries, selected)
    ordered: list[MemoryEntry] = []
    seen: set[int] = set()
    for e in fact_entries + selected:
        if e.id not in seen:
            ordered.append(e)
            seen.add(e.id)

    parts: list[str] = []
    if previous:
        clean = previous.replace("[rolling]", "").strip()
        if clean:
            parts.append(clean[:80])

    for entry in ordered:
        snippet = entry.content.replace("\n", " ").strip()
        if len(snippet) > 55:
            snippet = snippet[:52] + "..."
        parts.append(f"[t{entry.turn}] {snippet}")

    summary = " | ".join(parts)
    if len(summary) > max_chars:
        summary = summary[: max_chars - 3] + "..."
    summary = _truncate_to_tokens(summary, max_tokens=300)

    return summary, len(entries)


def consolidate_session(store: MemoryStore, session: str, max_chars: int = 500) -> str:
    """Consolidation : le résumé remplace les entrées archivées."""
    summary, _ = build_extractive_summary(
        store, session, max_chars=max_chars, include_rolling=False
    )
    store.set_session_summary(session, summary)

    active = store.list_session(session)
    keep_ids = {e.id for e in active if e.importance >= 0.55 or e.turn <= 10}
    keep_ids |= {e.id for e in active if "fact" in e.tags}
    store.archive_entries(session, keep_ids=keep_ids)
    return summary
