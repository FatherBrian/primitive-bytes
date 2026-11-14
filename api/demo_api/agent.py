"""The agent loop: Claude Haiku 5.5 with the scenario's tools, every step streamed as an event.

A manual loop (rather than the SDK's tool runner) because the tools come through Reef in
process and the page needs each step as it happens.
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from typing import Any, Protocol

import anthropic
from mcp import types

from demo_api.scenarios import Setup

log = logging.getLogger("demo_api")

MODEL = "claude-haiku-5-5"
PRICE_IN = 0.10 / 1_000_000  # USD per token, prompts up to 100K tokens
PRICE_OUT = 0.50 / 1_000_000
MAX_TURNS = 6
MAX_TOKENS = 2000


class Model(Protocol):
    async def create(self, **kwargs: Any) -> Any: ...


class ClaudeModel:
    def __init__(self) -> None:
        self.client = anthropic.AsyncAnthropic(max_retries=2, timeout=60)

    async def create(self, **kwargs: Any) -> Any:
        return await self.client.messages.create(model=MODEL, **kwargs)


def cost(usage: Any) -> float:
    return usage.input_tokens * PRICE_IN + usage.output_tokens * PRICE_OUT


def _tool_param(t: types.Tool) -> dict[str, Any]:
    return {"name": t.name, "description": t.description or "", "input_schema": t.input_schema}


def _result_text(r: types.CallToolResult) -> str:
    parts = [c.text for c in r.content if isinstance(c, types.TextContent)]
    if not parts and r.structured_content is not None:
        parts = [json.dumps(r.structured_content)]
    return "\n".join(parts)[:4000]


def _ledger_line(e: Any) -> dict[str, Any]:
    b = e.body
    if e.kind == "decision":
        what = f"{'ALLOW' if b.get('allowed') else 'DENY'} {b.get('action')} {b.get('resource')}"
        why = "" if b.get("allowed") else b.get("reason", "")
    elif e.kind == "tools.listed":
        what = f"listed {', '.join(b.get('shown', [])) or 'nothing'}"
        hidden = [h.get("tool") for h in b.get("hidden", [])] + [d.get("tool") for d in b.get("drifted", [])]
        why = f"hidden: {', '.join(hidden)}" if hidden else ""
    elif e.kind == "enforcement":
        what = f"door {b.get('stage')} {b.get('server')}/{b.get('tool')}"
        why = b.get("reason", "") or (f"masked {', '.join(b['masked'])}" if b.get("masked") else "")
    else:
        what, why = e.kind, ""
    return {"seq": e.seq, "kind": e.kind, "what": what, "why": why, "hash": e.hash[:12]}


async def run(setup: Setup, model: Model) -> AsyncIterator[dict[str, Any]]:
    """Run the scenario's task once; yield events for the page."""
    seen = 0

    def new_ledger() -> list[dict[str, Any]]:
        nonlocal seen
        events = setup.ledger(seen)
        if events:
            seen = events[-1].seq
        return [_ledger_line(e) for e in events]

    yield {"type": "setup", **setup.describe, "task": setup.task}
    listed = await setup.tools.list()
    yield {
        "type": "tools",
        "tools": [{"name": t.name, "description": t.description or ""} for t in listed],
    }
    if ledger := new_ledger():
        yield {"type": "ledger", "entries": ledger}

    tools = [_tool_param(t) for t in listed]
    # MCP Apps: tools that name a view get their result drawn by it (on the page, not here).
    views = {t.name: ((t.meta or {}).get("ui") or {}).get("resourceUri") for t in listed}
    # A chat's earlier turns come first (text only), then this turn's question.
    messages: list[dict[str, Any]] = [
        {"role": h["role"], "content": h["text"]} for h in setup.history
    ] + [{"role": "user", "content": setup.task}]
    spent = 0.0
    for _turn in range(MAX_TURNS):
        params: dict[str, Any] = {
            "max_tokens": MAX_TOKENS,
            "system": setup.system,
            "messages": messages,
            "output_config": {"effort": "low"},
            "thinking": {"type": "adaptive", "display": "summarized"},
        }
        if tools:
            params["tools"] = tools
        try:
            response = await model.create(**params)
        except anthropic.APIStatusError as exc:
            # Billing, rate limits, an outage: say so plainly, don't crash the stream. The
            # detail goes to the server log, not to visitors.
            log.warning("model call failed: %s %s", exc.status_code, exc.message)
            yield {"type": "error", "message": "The model isn't available right now. Try again later."}
            break
        except anthropic.APIConnectionError:
            yield {"type": "error", "message": "Couldn't reach the model. Try again in a minute."}
            break
        spent += cost(response.usage)
        yield {"type": "usage", "cost_usd": round(spent, 6)}

        for block in response.content:
            if block.type == "thinking" and block.thinking:
                yield {"type": "thinking", "text": block.thinking}
            elif block.type == "text" and block.text:
                yield {"type": "text", "text": block.text}
            elif block.type == "tool_use":
                yield {"type": "tool_call", "id": block.id, "name": block.name, "input": block.input}

        if response.stop_reason == "refusal":
            yield {"type": "error", "message": "The model declined this request."}
            break
        if response.stop_reason == "pause_turn":
            messages.append({"role": "assistant", "content": response.content})
            continue
        if response.stop_reason != "tool_use":
            break  # end_turn, max_tokens, stop_sequence

        messages.append({"role": "assistant", "content": response.content})
        results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            view: dict[str, Any] = {}
            try:
                r = await setup.tools.call(block.name, dict(block.input or {}))
                text, is_error = _result_text(r), bool(r.is_error)
                data = r.structured_content
                if views.get(block.name) and not is_error and data is not None and len(json.dumps(data)) < 20_000:
                    view = {"ui": views[block.name], "input": block.input, "data": data}
            except Exception as exc:  # the tool layer failing is part of the story, not a crash
                text, is_error = f"Error: {exc}", True
            yield {"type": "tool_result", "id": block.id, "name": block.name, "text": text,
                   "is_error": is_error, **view}
            results.append(
                {"type": "tool_result", "tool_use_id": block.id, "content": text, "is_error": is_error}
            )
            if ledger := new_ledger():
                yield {"type": "ledger", "entries": ledger}
        messages.append({"role": "user", "content": results})
    else:
        yield {"type": "error", "message": f"Stopped after {MAX_TURNS} turns."}

    for got in setup.received():
        yield {"type": "server", **got}
    yield {"type": "done", "cost_usd": round(spent, 6)}
