"""Feed cards: a few lines about a finished run, for the list of recent runs.

Built from the run's own events, so it says only what the replay would show.
"""

from __future__ import annotations

from typing import Any

TITLES = {"rug-pull": "reef lock, live", "grant": "Grant playground"}


def card(scenario: str, events: list[dict[str, Any]]) -> dict[str, Any]:
    setup = next((e for e in events if e["type"] == "setup"), {})
    title = setup.get("prompt") if scenario == "playground" else TITLES.get(scenario, scenario)
    calls = [e for e in events if e["type"] == "tool_call"]
    results = [e for e in events if e["type"] == "tool_result"]
    ledger = [line for e in events if e["type"] == "ledger" for line in e.get("entries", [])]
    received = {e["server"]: [c["tool"] for c in e.get("calls", [])] for e in events if e["type"] == "server"}

    refused = sum(
        1 for r in results
        if r.get("is_error") and ("Denied at the door" in r["text"] or "forwarded nothing" in r["text"])
    )
    highlights: list[dict[str, str]] = []
    if any("send_email" in tools for tools in received.values()):
        highlights.append({"kind": "bad", "text": "mail went out"})
    if refused:
        highlights.append({"kind": "good", "text": f"{refused} call{'s' if refused > 1 else ''} refused"})
    if any(line.get("kind") == "tools.listed" and line.get("why") for line in ledger):
        highlights.append({"kind": "good", "text": "tools hidden"})
    if any(str(line.get("why", "")).startswith("masked") for line in ledger):
        highlights.append({"kind": "good", "text": "fields masked"})
    if any(e["type"] == "error" for e in events):
        highlights.append({"kind": "meh", "text": "stopped early"})

    answers = [e["text"] for e in events if e["type"] == "text"]
    answer = " ".join(answers[-1].split())[:160] if answers else ""
    return {
        "title": title or "A run",
        "setup": setup.get("summary", ""),
        "calls": len(calls),
        "highlights": highlights,
        "answer": answer,
    }
