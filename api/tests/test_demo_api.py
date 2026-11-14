"""The demo API, end to end, with the scripted model (no key, no spend)."""

from __future__ import annotations

import json
from typing import Any

import anyio
import pytest

from demo_api.agent import run
from demo_api.fake import FakeModel
from demo_api.limits import Limits
from demo_api.scenarios import grant, rug_pull


async def collect(build: Any, option: str) -> list[dict[str, Any]]:
    async with build(option) as setup:
        return [e async for e in run(setup, FakeModel())]


def events_of(kind: str, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [e for e in events if e["type"] == kind]


def test_unprotected_rug_pull_sends_the_email() -> None:
    events = anyio.run(collect, rug_pull, "none")
    tools = events_of("tools", events)[0]["tools"]
    assert any("backup" in t["description"] for t in tools)  # the poisoned description
    server = events_of("server", events)[0]
    assert [c["tool"] for c in server["calls"]] == ["search", "send_email"]
    assert events[-1]["type"] == "done"


def test_reef_and_the_lock_hide_the_poisoned_tool() -> None:
    events = anyio.run(collect, rug_pull, "reef-lock")
    names = [t["name"] for t in events_of("tools", events)[0]["tools"]]
    assert names == ["notes_send_email"]  # search drifted, so Reef hides it
    ledger = [line for e in events_of("ledger", events) for line in e["entries"]]
    assert any("notes_search" in line["why"] for line in ledger)
    server = events_of("server", events)[0]
    assert server["calls"] == []  # nothing reached the server
    assert not any(e["type"] == "tool_call" and e["name"].endswith("send_email") for e in events)


def test_headcount_grant_hides_reviews_and_masks_salary() -> None:
    events = anyio.run(collect, grant, "headcount")
    names = sorted(t["name"] for t in events_of("tools", events)[0]["tools"])
    assert names == ["hr_headcount", "hr_payroll"]  # reviews are pii; the task didn't name it
    events = anyio.run(collect, grant, "headcount-pii")
    names = sorted(t["name"] for t in events_of("tools", events)[0]["tools"])
    assert names == ["hr_headcount", "hr_payroll", "hr_performance_reviews"]


def test_payroll_salary_is_masked_without_pii() -> None:
    async def call() -> str:
        async with grant("headcount") as setup:
            r = await setup.tools.call("hr_payroll", {})
            return json.dumps(r.structured_content)

    assert '"salary": "***"' in anyio.run(call)


def test_limits_per_visitor_and_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    now = [1_000_000.0]
    limits = Limits(per_window=2, per_day=3, daily_budget_usd=0.01, clock=lambda: now[0])
    assert limits.check("a") is None
    assert limits.check("a") is None
    assert "a lot of runs" in (limits.check("a") or "")
    now[0] += 601
    assert limits.check("a") is None
    assert "today's live runs" in (limits.check("a") or "")
    assert limits.check("b") is None  # someone else is unaffected
    limits.record(0.02)
    assert "budget" in (limits.check("c") or "")
    monkeypatch.setenv("DEMO_ENABLED", "0")
    assert "switched off" in (limits.check("d") or "")


def test_store_saves_gets_and_prunes(tmp_path: Any) -> None:
    from demo_api.store import RunStore

    store = RunStore(str(tmp_path / "runs.db"), keep=2)
    for n in range(3):
        store.save(f"r{n}", "grant", "headcount", [{"type": "done", "n": n}], 0.001)
    assert store.count() == 2
    assert store.get("r0") is None  # the oldest is gone
    saved = store.get("r2")
    assert saved is not None and saved["events"] == [{"type": "done", "n": 2}]
    assert set(saved) == {"id", "scenario", "option", "created_at", "cost_usd", "events"}


def test_a_live_run_is_saved_and_replayable(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEMO_FAKE_MODEL", "1")
    from starlette.testclient import TestClient

    from demo_api import app as app_module
    from demo_api.limits import Limits
    from demo_api.store import RunStore

    monkeypatch.setattr(app_module, "STORE", RunStore(str(tmp_path / "runs.db")))
    monkeypatch.setattr(app_module, "LIMITS", Limits())
    client = TestClient(app_module.app)
    r = client.post("/api/run", json={"scenario": "rug-pull", "option": "reef-lock"})
    streamed = [json.loads(line[6:]) for line in r.text.splitlines() if line.startswith("data: ")]
    assert streamed[0]["type"] == "run"
    run_id = streamed[0]["id"]
    saved = client.get(f"/api/runs/{run_id}").json()
    assert saved["scenario"] == "rug-pull" and saved["option"] == "reef-lock"
    assert saved["events"][-1]["type"] == "done"
    assert "testclient" not in json.dumps(saved)  # the caller's address is never stored
    assert client.get("/api/runs/nope").status_code == 404
