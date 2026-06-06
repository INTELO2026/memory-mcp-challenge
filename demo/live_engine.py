"""Moteur de conversation live — traite la session tour par tour via MCP."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from pathlib import Path

from benchmark.harness import generate_long_conversation, load_json
from benchmark.naive import build_naive_context
from benchmark.traps import TRAP_QUESTIONS, evaluate_trap_questions
from demo.llm import generate_reply
from memory_mcp.config import ensure_env_loaded, get_settings
from memory_mcp.stats import count_tokens, reset_stats
from memory_mcp.tools import MemoryTools

ROOT = Path(__file__).parent.parent
CONVERSATION = ROOT / "benchmark" / "conversation.json"


def _tags_for_turn(turn: dict) -> list[str]:
    if turn["turn"] <= 10:
        return [turn["role"], "fact"]
    return [turn["role"], "exchange"]


def _content_for_turn(turn: dict) -> str:
    if turn["turn"] > 10:
        return f"{turn['role']}: #{turn['turn']}"
    return f"{turn['role']}: {turn['content']}"


def _offline_reply(user_turn: dict, base_turns: list[dict]) -> str:
    next_turn = user_turn["turn"] + 1
    for base in base_turns:
        if base["turn"] == next_turn and base["role"] == "assistant":
            return base["content"]
    return f"Pris en charge — suivi du dossier au tour {user_turn['turn']}."


def _build_agent_context(
    tools: MemoryTools, session: str, user_message: str, *, use_llm: bool
) -> tuple[str, dict]:
    demo_tokens = get_settings().summary_max_tokens_demo
    summary = tools.memory_summarize(session=session, max_tokens=demo_tokens, use_llm=use_llm)
    search = tools.memory_search(query=user_message, top_k=3, session=session)
    hits = "\n".join(f"- {r['content']}" for r in search["results"])
    context = (
        f"Resume session :\n{summary['summary']}\n\n"
        f"Souvenirs pertinents :\n{hits}\n\n"
        f"Message actuel :\n{user_message}"
    )
    return context, {"summary": summary, "search": search}


@dataclass
class LiveSession:
    id: str
    name: str
    tools: MemoryTools
    turns: list[dict]
    base: list[dict]
    offline: bool
    index: int = 0
    naive_history: list[dict] = field(default_factory=list)
    naive_cumulative: int = 0
    memory_cumulative: int = 0
    messages: list[dict] = field(default_factory=list)
    finished: bool = False

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "session": self.name,
            "offline": self.offline,
            "index": self.index,
            "total_turns": len(self.turns),
            "finished": self.finished,
            "naive_cumulative": self.naive_cumulative,
            "memory_cumulative": self.memory_cumulative,
            "messages": self.messages,
            "stats": self.tools.memory_stats(session=self.name) if self.index else None,
        }


class LiveConversationManager:
    """Sessions live en memoire — un moteur MCP par conversation."""

    def __init__(self) -> None:
        self._sessions: dict[str, LiveSession] = {}

    def create(
        self,
        *,
        session_name: str | None = None,
        target_turns: int = 50,
        offline: bool = True,
    ) -> LiveSession:
        ensure_env_loaded()
        reset_stats()
        base = load_json(CONVERSATION)
        turns = generate_long_conversation(base, target_turns=target_turns)
        sid = uuid.uuid4().hex[:12]
        name = session_name or f"live-{sid}"
        live = LiveSession(
            id=sid,
            name=name,
            tools=MemoryTools(),
            turns=turns,
            base=base,
            offline=offline,
        )
        self._sessions[sid] = live
        return live

    def get(self, session_id: str) -> LiveSession | None:
        return self._sessions.get(session_id)

    def step(self, session_id: str) -> dict:
        live = self._require(session_id)
        if live.finished:
            return {"done": True, "session": live.to_dict()}

        turn = live.turns[live.index]
        live.index += 1
        role = turn["role"]
        content = turn["content"]
        event: dict = {
            "done": False,
            "turn": turn["turn"],
            "role": role,
            "content": content,
        }

        live.naive_history.append({"role": role, "content": content})
        _, naive_tokens = build_naive_context(live.naive_history)
        live.naive_cumulative += naive_tokens
        event["naive_turn_tokens"] = naive_tokens
        event["naive_cumulative"] = live.naive_cumulative

        if role != "user":
            live.tools.memory_store(
                content=_content_for_turn(turn),
                tags=_tags_for_turn(turn),
                session=live.name,
                turn=turn["turn"],
            )
            live.messages.append(
                {"turn": turn["turn"], "role": role, "content": content, "source": "script"}
            )
        else:
            use_llm = not live.offline
            context, mcp = _build_agent_context(live.tools, live.name, content, use_llm=use_llm)
            memory_tokens = count_tokens(context)
            live.memory_cumulative += memory_tokens
            event["memory_turn_tokens"] = memory_tokens
            event["memory_cumulative"] = live.memory_cumulative
            event["mcp"] = {
                "summary_excerpt": mcp["summary"]["summary"][:200],
                "search_hits": mcp["search"]["results"],
            }

            if live.offline:
                reply = _offline_reply(turn, live.base)
            else:
                try:
                    reply = generate_reply(context, content)
                except Exception as exc:
                    reply = _offline_reply(turn, live.base)
                    event["llm_fallback"] = str(exc)

            live.tools.memory_store(
                content=f"user: {content}",
                tags=_tags_for_turn(turn),
                session=live.name,
                turn=turn["turn"],
            )
            live.tools.memory_store(
                content=f"assistant: {reply}",
                tags=["assistant", "exchange"],
                session=live.name,
                turn=turn["turn"],
            )
            live.messages.append(
                {"turn": turn["turn"], "role": "user", "content": content, "source": "live"}
            )
            live.messages.append(
                {
                    "turn": turn["turn"],
                    "role": "assistant",
                    "content": reply,
                    "source": "mcp+llm" if not live.offline else "mcp+offline",
                }
            )
            event["assistant_reply"] = reply

        if live.index >= len(live.turns):
            live.finished = True
            event["done"] = True
            event["quality"] = evaluate_trap_questions(live.tools, live.name)
            event["summary"] = live.tools.memory_summarize(
                session=live.name,
                max_tokens=get_settings().summary_max_tokens_demo,
                use_llm=not live.offline,
            )
            event["stats"] = live.tools.memory_stats(session=live.name)

        event["session"] = {
            "id": live.id,
            "index": live.index,
            "total_turns": len(live.turns),
            "finished": live.finished,
            "naive_cumulative": live.naive_cumulative,
            "memory_cumulative": live.memory_cumulative,
        }
        return event

    def search_trap(self, session_id: str, query: str, top_k: int = 1) -> dict:
        live = self._require(session_id)
        result = live.tools.memory_search(query, top_k=top_k, session=live.name)
        expected = next((exp for q, exp in TRAP_QUESTIONS if q == query), None)
        passed = False
        if expected and result["results"]:
            from memory_mcp.validation import top1_contains

            passed = top1_contains(expected, result["results"])
        return {
            "query": query,
            "expected": expected,
            "passed": passed,
            "results": result["results"],
        }

    def evaluate_traps(self, session_id: str) -> dict:
        live = self._require(session_id)
        return evaluate_trap_questions(live.tools, live.name)

    def _require(self, session_id: str) -> LiveSession:
        live = self.get(session_id)
        if live is None:
            raise KeyError(f"Session inconnue : {session_id}")
        return live


MANAGER = LiveConversationManager()
