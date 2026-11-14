"""Visitors' own questions, and the feed of recent runs that never shows them."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import AsyncIterator
from typing import Any

import pytest
from starlette.testclient import TestClient

from demo_api.feed import card
from demo_api.store import RunStore
from demo_api.world.playground import MAX_QUESTION, ConfigError, parse
from demo_api.world.servers import World

BASE = {"servers": ["crm"], "gateway": "reef", "task": "pipeline", "lock": True}


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def world() -> AsyncIterator[World]:
    w = await World().start()
    try:
        yield w
    finally:
        w.close()


@pytest.mark.anyio
async def test_own_questions_are_cleaned_capped_and_unlisted(world: World) -> None:
    c = parse({**BASE, "prompt": "custom", "text": "  Which deals\x00 close\n\nthis month? "}, world)
    assert c.text == "Which deals close this month?"
    assert not c.listed and c.question() == ("Your own question", "Which deals close this month?")
    assert parse({**BASE, "prompt": "deals"}, world).listed
    for bad in [None, "", "hi", "x" * (MAX_QUESTION + 1), ["a list"]]:
        with pytest.raises(ConfigError):
            parse({**BASE, "prompt": "custom", "text": bad}, world)


def test_a_card_says_what_the_replay_would() -> None:
    events: list[dict[str, Any]] = [
        {"type": "setup", "summary": "Connected straight to docs, comms.", "prompt": "Depth calibration"},
        {"type": "tool_call", "name": "docs_search", "input": {}},
        {"type": "tool_result", "name": "docs_search", "text": "Denied at the door: no.", "is_error": True},
        {"type": "ledger", "entries": [{"kind": "enforcement", "why": "masked salary"}]},
        {"type": "text", "text": "Here's   what I found."},
        {"type": "server", "server": "comms", "calls": [{"tool": "send_email", "arguments": {}}]},
        {"type": "done", "cost_usd": 0.001},
    ]
    c = card("playground", events)
    assert c["title"] == "Depth calibration" and c["calls"] == 1
    assert [h["text"] for h in c["highlights"]] == ["mail went out", "1 call refused", "fields masked"]
    assert c["answer"] == "Here's what I found."


def test_old_databases_get_the_new_columns(tmp_path: Any) -> None:
    path = str(tmp_path / "runs.db")
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE runs (id TEXT PRIMARY KEY, scenario TEXT NOT NULL, option TEXT NOT NULL,"
                   " created_at REAL NOT NULL, cost_usd REAL NOT NULL DEFAULT 0, events TEXT NOT NULL)")
        db.execute("INSERT INTO runs VALUES ('old', 'grant', 'headcount', 1, 0, '[]')")
    store = RunStore(path)
    assert store.get("old") is not None and store.recent() == []  # kept, but not listed


def test_the_feed_lists_preset_runs_only(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEMO_FAKE_MODEL", "1")
    from demo_api import app as app_module
    from demo_api.limits import Limits

    monkeypatch.setattr(app_module, "STORE", RunStore(str(tmp_path / "runs.db")))
    monkeypatch.setattr(app_module, "LIMITS", Limits())

    def go(client: TestClient, config: dict[str, Any]) -> str:
        r = client.post("/api/run", json={"scenario": "playground", "config": config})
        first = next(line for line in r.text.splitlines() if line.startswith("data: "))
        return str(json.loads(first[6:])["id"])

    with TestClient(app_module.app) as client:
        assert client.get("/api/world").json()["max_question"] == MAX_QUESTION
        preset = go(client, {**BASE, "prompt": "deals"})
        own = go(client, {**BASE, "prompt": "custom", "text": "My secret question about deals"})
        feed = client.get("/api/runs").json()["runs"]
        assert [r["id"] for r in feed] == [preset]
        assert feed[0]["title"] == "Big open deals" and "Through Reef" in feed[0]["setup"]
        assert "secret" not in json.dumps(feed)
        saved = client.get(f"/api/runs/{own}").json()  # still replayable by its link
        assert saved["events"][0]["task"] == "My secret question about deals"
