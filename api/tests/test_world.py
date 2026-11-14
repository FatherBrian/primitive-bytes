"""Kelpworks, the explorer's world: the traps fire, and Reef and Trellis catch what they can."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest
from starlette.testclient import TestClient

from demo_api.world.data import COMPANY, generate
from demo_api.world.servers import TASKS, World


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


def test_the_data_is_the_same_every_time() -> None:
    again = generate()
    assert again.tables() == COMPANY.tables()
    assert len(COMPANY.orders) == 2400 and len(COMPANY.accounts) == 120
    assert any("AI assistant" in t["body"] for t in COMPANY.tickets)


@pytest.mark.anyio
async def test_the_lock_catches_the_rug_pull_and_the_late_tool(world: World) -> None:
    status = {(s["name"], t["name"]): t["lock"]["status"]
              for s in world.describe()["servers"] for t in s["tools"]}
    assert status[("docs", "search")] == "drifted"
    assert status[("pal", "export_contacts")] == "missing"
    assert status[("crm", "list_deals")] == "pinned"
    seen = await world.view("everything")
    assert {h["tool"] for h in seen["hidden"]} == {"docs_search", "pal_export_contacts"}
    refused = await world.call("docs", "search", {"query": "depth"}, "everything")
    assert refused["is_error"] and refused["received"] == []
    direct = await world.call("docs", "search", {"query": "depth"}, None)
    assert not direct["is_error"] and direct["received"]  # the server itself still answers


@pytest.mark.anyio
async def test_grants_hide_mask_and_refuse(world: World) -> None:
    shown = {t["name"] for t in (await world.view("headcount"))["shown"]}
    assert "hr_payroll" in shown and "hr_performance_reviews" not in shown
    masked = await world.call("hr", "payroll", {"team": "Sales"}, "headcount")
    assert masked["result"]["rows"][0]["salary"] == "***"
    full = await world.call("hr", "payroll", {"team": "Sales"}, "hr-pii")
    assert isinstance(full["result"]["rows"][0]["salary"], int)
    send = await world.call("comms", "send_email", {"to": "a@b.example", "body": "x"}, "pipeline")
    assert send["is_error"] and "write" in send["text"] and send["received"] == []
    ticket = await world.call("support", "get_ticket", {"ticket_id": "T-1042"}, "triage")
    assert ticket["result"]["customer_email"] == "***"
    assert any(line["kind"] == "decision" for line in ticket["ledger"])


@pytest.mark.anyio
async def test_bad_arguments_come_back_as_tool_errors(world: World) -> None:
    r = await world.call("support", "get_ticket", {"ticket_id": "nope"}, None)
    assert r["is_error"] and "no ticket" in r["text"]
    r = await world.call("warehouse", "sales_summary", {"group_by": "planet"}, None)
    assert r["is_error"]


def test_the_endpoints(monkeypatch: pytest.MonkeyPatch) -> None:
    from demo_api import app as app_module

    monkeypatch.setattr(app_module, "BROWSE_PER_MIN", 1000)
    with TestClient(app_module.app) as client:
        world: dict[str, Any] = client.get("/api/world").json()
        assert len(world["servers"]) == 7 and len(world["tasks"]) == len(TASKS)
        view = client.get("/api/world/view?task=pipeline").json()
        assert any(t["name"] == "crm_list_deals" for t in view["shown"])
        assert client.get("/api/world/view?task=root").status_code == 400
        r = client.post("/api/world/call", json={"server": "crm", "tool": "list_deals",
                                                 "arguments": {"stage": "won"}, "task": "pipeline"})
        assert r.status_code == 200 and r.json()["result"]["rows"][0]["stage"] == "won"
        bad = client.post("/api/world/call", json={"server": "crm", "tool": "rm", "task": None})
        assert bad.status_code == 400
        big = client.post("/api/world/call", json={"server": "crm", "tool": "list_deals",
                                                   "arguments": {"x": "y" * 5000}})
        assert big.status_code == 400
