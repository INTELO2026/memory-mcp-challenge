"""Tests moteur conversation live."""

from __future__ import annotations

from demo.live_engine import MANAGER


def test_live_session_step_by_step():
    live = MANAGER.create(target_turns=12, offline=True)
    events = []
    while True:
        event = MANAGER.step(live.id)
        events.append(event)
        if event["done"]:
            break

    assert len(events) == 12
    assert events[-1]["quality"]["total"] == 9
    assert events[-1]["session"]["naive_cumulative"] > events[-1]["session"]["memory_cumulative"]
    assert len(live.messages) >= 10


def test_live_trap_search():
    live = MANAGER.create(target_turns=10, offline=True)
    while not live.finished:
        MANAGER.step(live.id)

    result = MANAGER.search_trap(live.id, "référence légale du dossier client")
    assert result["passed"] is True
    assert "CTR-2024-8847" in (result["results"][0]["content"] if result["results"] else "")
