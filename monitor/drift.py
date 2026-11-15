"""MCP drift watch: run reef.lock against public MCP servers and record what changed.

Every run lists each server's tools (and reads their MCP Apps views), pins them the way
`reef lock` does, and compares them with monitor/reef.lock from the last run. Anything that
changed, appeared or disappeared becomes an event in src/data/drift/history.json, then the
lock is updated so tomorrow's run compares against today. A server that can't be reached is
marked unreachable and keeps its old pins, so an outage never looks like drift.

    python monitor/drift.py            # check, record, update the lock
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from reef.clients import load_client_config
from reef.downstream import downstream_for
from reef.lock import Lock, read_views

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
CONFIG = HERE / "servers.json"
LOCK = HERE / "reef.lock"
DATA = ROOT / "src" / "data" / "drift"
STATUS = DATA / "status.json"
HISTORY = DATA / "history.json"
TIMEOUT = 120  # seconds per server, including an npx install
KEEP = 500  # events kept in history


def load(path: Path, default: Any) -> Any:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def save(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


async def snapshot(spec: Any) -> tuple[list[Any], dict[str, dict[str, Any]]]:
    client = downstream_for(spec, os.environ)
    tools = await client.list_tools(None)
    views = await read_views(client, None, tools, strict=False)
    return tools, views


async def main() -> int:
    now = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    loaded = load_client_config(CONFIG)
    lock = Lock.load(LOCK) if LOCK.exists() else Lock()
    status = load(STATUS, {"servers": {}})
    history: list[dict[str, Any]] = load(HISTORY, [])
    homepage = {name: e.get("homepage") for name, e in load(CONFIG, {})["mcpServers"].items()}
    events: list[dict[str, Any]] = []

    for name, spec in loaded.config.servers.items():
        prev = status["servers"].get(name, {})
        entry: dict[str, Any] = {
            "where": spec.where,
            "kind": "stdio" if spec.command else "http",
            "homepage": homepage.get(name),
            "first_seen": prev.get("first_seen"),
            "last_change": prev.get("last_change"),
        }
        try:
            tools, views = await asyncio.wait_for(snapshot(spec), TIMEOUT)
        except Exception as exc:  # unreachable: keep the old pins, record why
            reason = f"{type(exc).__name__}: {exc}".strip()
            print(f"{name}: unreachable ({reason[:200]})", file=sys.stderr)
            status["servers"][name] = {**prev, **entry, "status": "unreachable", "error": reason[:300],
                                       "checked": now}
            continue

        fresh = Lock.from_catalog({name: tools}, {name: views}).servers.get(name, {})
        if name in lock.servers:
            mine = Lock(servers={name: lock.servers[name]})
            for d in mine.compare({name: tools}, {name: views}):
                before = lock.servers[name].get(d.tool, {})
                after = fresh.get(d.tool, {})
                events.append({
                    "at": now, "server": name, "tool": d.tool, "kind": d.kind, "diff": d.diff,
                    "before": before.get("description"), "after": after.get("description"),
                })
        else:
            entry["first_seen"] = now
        changed = any(e["server"] == name for e in events)
        if changed:
            entry["last_change"] = now
        lock.servers[name] = fresh
        status["servers"][name] = {**entry, "status": "changed" if changed else "stable",
                                   "tools": len(fresh), "error": None, "checked": now}
        print(f"{name}: {len(fresh)} tools, {'CHANGED' if changed else 'no change'}")

    for name, why in loaded.skipped.items():
        status["servers"][name] = {"status": "skipped", "error": why, "checked": now}
    # Servers taken out of servers.json drop out of the lock and the status.
    for name in set(lock.servers) - set(loaded.config.servers):
        del lock.servers[name]
    for name in set(status["servers"]) - set(loaded.config.servers) - set(loaded.skipped):
        del status["servers"][name]

    status["checked"] = now
    status["tools"] = sum(len(t) for t in lock.servers.values())
    DATA.mkdir(parents=True, exist_ok=True)
    lock.save(LOCK)
    save(STATUS, status)
    save(HISTORY, (events + history)[:KEEP])
    print(f"{len(events)} change(s) recorded")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
