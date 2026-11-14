"""Run one demo from the terminal and print what happens.

    python -m demo_api rug-pull none
    python -m demo_api rug-pull reef-lock
    python -m demo_api grant headcount
    python -m demo_api grant headcount-pii

Reads ANTHROPIC_API_KEY from the environment or api/.env. Each run costs a fraction of a
cent with Claude Haiku 5.5. DEMO_FAKE_MODEL=1 uses the scripted model instead.
"""

from __future__ import annotations

import sys

import anyio

from demo_api.agent import run
from demo_api.app import _model
from demo_api.scenarios import SCENARIOS


def show(e: dict) -> None:
    t = e["type"]
    if t == "setup":
        print(f"\n== {e.get('summary')}\n   task: {e['task']}")
    elif t == "tools":
        for tool in e["tools"]:
            print(f"   tool {tool['name']}: {tool['description'][:90]}")
    elif t == "thinking":
        print(f"   (thinking) {e['text'][:200]}")
    elif t == "text":
        print(f"   agent: {e['text']}")
    elif t == "tool_call":
        print(f"   -> {e['name']} {e['input']}")
    elif t == "tool_result":
        flag = " ERROR" if e["is_error"] else ""
        print(f"   <- {e['name']}{flag}: {e['text'][:160]}")
    elif t == "ledger":
        for line in e["entries"]:
            print(f"   ledger #{line['seq']} {line['what']}  {line['why']}")
    elif t == "server":
        print(f"   server {e['server']} saw: {[c['tool'] for c in e['calls']] or 'nothing'}")
    elif t == "done":
        print(f"== done, ${e['cost_usd']:.5f}")
    elif t == "error":
        print(f"!! {e['message']}")


async def main(scenario: str, option: str) -> None:
    build = SCENARIOS[scenario][0]
    async with build(option) as setup:
        async for event in run(setup, _model()):
            show(event)


if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] not in SCENARIOS:
        print(__doc__)
        sys.exit(2)
    anyio.run(main, sys.argv[1], sys.argv[2])
