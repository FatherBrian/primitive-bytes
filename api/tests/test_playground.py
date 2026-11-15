"""Playground runs over the sample company, with the scripted model (no key, no spend)."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import pytest
from starlette.testclient import TestClient

from demo_api.agent import run
from demo_api.fake import FakeModel
from demo_api.world.playground import PRESETS, ConfigError, parse, playground
from demo_api.world.servers import World

PRESET = {p["id"]: p["config"] for p in PRESETS}


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


async def go(world: World, preset: str) -> list[dict[str, Any]]:
    async with playground(world, parse(PRESET[preset], world)) as setup:
        return [e async for e in run(setup, FakeModel())]


def of(kind: str, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [e for e in events if e["type"] == kind]


def sent(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [c for e in of("server", events) if e["server"] == "comms" for c in e["calls"]]


def test_every_preset_is_a_valid_config() -> None:
    import anyio

    async def check() -> None:
        w = await World().start()
        try:
            for p in PRESETS:
                parse(p["config"], w)
                if "compare" in p:
                    parse(p["compare"], w)
        finally:
            w.close()

    anyio.run(check)


@pytest.mark.anyio
async def test_bad_configs_are_refused(world: World) -> None:
    for bad in [None, {}, {"servers": ["nope"], "gateway": "direct", "prompt": "deals"},
                {"servers": ["crm"], "gateway": "reef", "task": "root", "prompt": "deals"},
                {"servers": ["crm"], "gateway": "direct", "prompt": "write me a poem"}]:
        with pytest.raises(ConfigError):
            parse(bad, world)


@pytest.mark.anyio
async def test_the_rug_pull_three_ways(world: World) -> None:
    open_run = await go(world, "rug-pull-open")
    assert sent(open_run) and sent(open_run)[0]["tool"] == "send_email"  # it obeyed

    unlocked = await go(world, "rug-pull-unlocked")
    names = [t["name"] for t in of("tools", unlocked)[0]["tools"]]
    assert "docs_search" in names and sent(unlocked)  # a gateway alone doesn't help

    locked = await go(world, "rug-pull-locked")
    names = [t["name"] for t in of("tools", locked)[0]["tools"]]
    assert "docs_search" not in names and sent(locked) == []


@pytest.mark.anyio
async def test_a_run_sees_only_its_own_calls_and_ledger(world: World) -> None:
    first = await go(world, "rug-pull-open")
    second = await go(world, "rug-pull-open")
    assert len(sent(first)) == 1 and len(sent(second)) == 1
    a = await go(world, "payroll-headcount")
    b = await go(world, "payroll-headcount")
    seqs_a = {line["seq"] for e in of("ledger", a) for line in e["entries"]}
    seqs_b = {line["seq"] for e in of("ledger", b) for line in e["entries"]}
    assert seqs_a and seqs_b and not seqs_a & seqs_b


@pytest.mark.anyio
async def test_only_connected_servers_show(world: World) -> None:
    events = await go(world, "injected-ticket-no-mail")
    names = {t["name"].split("_")[0] for t in of("tools", events)[0]["tools"]}
    assert names <= {"support", "crm"} and "support" in names
    assert {e["server"] for e in of("server", events)} == {"support", "crm"}
    listed = [line for e in of("ledger", events) for line in e["entries"] if line["kind"] == "tools.listed"]
    assert listed and "hr_" not in listed[0]["what"]  # the ledger lists only what's connected


def test_the_endpoint_runs_and_saves_a_playground(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEMO_FAKE_MODEL", "1")
    from demo_api import app as app_module
    from demo_api.limits import Limits
    from demo_api.store import RunStore

    monkeypatch.setattr(app_module, "STORE", RunStore(str(tmp_path / "runs.db")))
    monkeypatch.setattr(app_module, "LIMITS", Limits())
    with TestClient(app_module.app) as client:
        world = client.get("/api/world").json()
        assert world["presets"] and world["prompts"]
        r = client.post("/api/run", json={"scenario": "playground", "config": PRESET["rug-pull-locked"]})
        events = [json.loads(line[6:]) for line in r.text.splitlines() if line.startswith("data: ")]
        assert events[1]["type"] == "setup" and "with the lock" in events[1]["summary"]
        saved = client.get(f"/api/runs/{events[0]['id']}").json()
        assert saved["scenario"] == "playground" and json.loads(saved["option"])["lock"] is True
        bad = client.post("/api/run", json={"scenario": "playground", "config": {"servers": []}})
        assert bad.status_code == 400


@pytest.mark.anyio
async def test_views_ride_along_through_reef(world: World) -> None:
    config = parse({"servers": ["pal"], "gateway": "reef", "task": "pipeline", "lock": True,
                    "prompt": "contact"}, world)
    async with playground(world, config) as setup:
        events = [e async for e in run(setup, FakeModel())]
    result = next(e for e in events if e["type"] == "tool_result")
    assert result["ui"] == "ui://pal/lookup-cards"
    assert result["data"]["rows"][0]["email"] == "***"  # the view gets what Reef let through


def test_the_view_endpoint() -> None:
    from demo_api import app as app_module

    with TestClient(app_module.app) as client:
        r = client.get("/api/world/ui?uri=ui://crm/deal-board")
        assert r.status_code == 200 and r.headers["content-type"].startswith("text/html;profile=mcp-app")
        assert "ui/initialize" in r.text
        assert client.get("/api/world/ui?uri=ui://nope").status_code == 404
        tools = {t["name"]: t for s in client.get("/api/world").json()["servers"] for t in s["tools"]}
        assert tools["quick_lookup"]["view"] == "ui://pal/lookup-cards"
        assert {t["kind"] for t in tools["quick_lookup"]["traps"]} >= {"Overreach", "A view that acts on its own"}


def test_history_is_checked_and_trimmed() -> None:
    from demo_api.world.playground import MAX_ANSWER, MAX_HISTORY, history

    assert history(None) == []
    turns = [{"role": "user", "text": "What does the wiki say?"}, {"role": "assistant", "text": "x" * 5000}]
    got = history(turns)
    assert got[0] == {"role": "user", "text": "What does the wiki say?"}
    assert len(got[1]["text"]) == MAX_ANSWER
    many = turns * (MAX_HISTORY // 2 + 3)
    assert len(history(many)) == MAX_HISTORY
    for bad in (
        [{"role": "user", "text": "hi there"}],  # odd: a question with no answer
        [{"role": "assistant", "text": "a"}, {"role": "user", "text": "hi there"}],  # wrong order
        [{"role": "user", "text": "y" * 500}, {"role": "assistant", "text": "a"}],  # question too long
        "not a list",
    ):
        with pytest.raises(ConfigError):
            history(bad)


@pytest.mark.anyio
async def test_a_follow_up_sees_the_earlier_turns(world: World) -> None:
    earlier = [{"role": "user", "text": "What does the wiki say about depth calibration?"},
               {"role": "assistant", "text": "It says to recalibrate after firmware updates."}]
    async with playground(world, parse(PRESET["rug-pull-locked"], world), earlier) as setup:
        assert setup.history == earlier
        events = [e async for e in run(setup, FakeModel())]
    assert of("done", events)


def test_the_endpoint_takes_history_and_keeps_follow_ups_unlisted(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEMO_FAKE_MODEL", "1")
    from demo_api import app as app_module
    from demo_api.limits import Limits
    from demo_api.store import RunStore

    monkeypatch.setattr(app_module, "STORE", RunStore(str(tmp_path / "runs.db")))
    monkeypatch.setattr(app_module, "LIMITS", Limits())
    with TestClient(app_module.app) as client:
        assert client.get("/health").json()["chat"]["history"] > 0
        body = {"scenario": "playground", "config": PRESET["rug-pull-locked"],
                "history": [{"role": "user", "text": "Hi, what can you do?"},
                            {"role": "assistant", "text": "I can search the wiki."}]}
        r = client.post("/api/run", json=body)
        events = [json.loads(line[6:]) for line in r.text.splitlines() if line.startswith("data: ")]
        assert any(e["type"] == "done" for e in events)
        assert client.get("/api/runs").json()["runs"] == []  # follow-ups never show in the feed
        bad = {**body, "history": [{"role": "user", "text": "only a question"}]}
        assert client.post("/api/run", json=bad).status_code == 400
