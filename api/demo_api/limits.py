"""Keeping the live demos cheap and hard to abuse.

- Per visitor: a few runs per ten minutes, and a daily cap.
- Overall: a daily spending cap in dollars, and a cap on runs at the same time.
- DEMO_ENABLED=0 turns live runs off without a redeploy.

Everything is in memory: one small instance is plenty, and a restart only resets counters.
The Anthropic key's own spend limit (set in the Console) is the backstop.
"""

from __future__ import annotations

import asyncio
import os
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return default


@dataclass
class Limits:
    per_window: int = int(_env_float("DEMO_RUNS_PER_10_MIN", 5))
    per_day: int = int(_env_float("DEMO_RUNS_PER_DAY", 25))
    daily_budget_usd: float = _env_float("DEMO_DAILY_BUDGET_USD", 0.50)
    concurrent: int = int(_env_float("DEMO_MAX_CONCURRENT", 4))
    clock: object = time.time
    _runs: dict[str, deque[float]] = field(default_factory=lambda: defaultdict(deque))
    _spent: dict[str, float] = field(default_factory=dict)  # day -> dollars
    _slots: asyncio.Semaphore | None = None

    @property
    def enabled(self) -> bool:
        return os.environ.get("DEMO_ENABLED", "1") != "0"

    def _now(self) -> float:
        return self.clock()  # type: ignore[operator]

    def _day(self) -> str:
        return time.strftime("%Y-%m-%d", time.gmtime(self._now()))

    def spent_today(self) -> float:
        return self._spent.get(self._day(), 0.0)

    def check(self, visitor: str) -> str | None:
        """Why this visitor can't start a run now, or None if they can."""
        if not self.enabled:
            return "Live runs are switched off right now."
        if self.spent_today() >= self.daily_budget_usd:
            return "Today's demo budget is used up. Try again tomorrow."
        now = self._now()
        runs = self._runs[visitor]
        while runs and now - runs[0] > 86_400:
            runs.popleft()
        if len(runs) >= self.per_day:
            return "You've used today's live runs. Try again tomorrow."
        recent = sum(1 for t in runs if now - t < 600)
        if recent >= self.per_window:
            return "That's a lot of runs in a few minutes. Try again shortly."
        runs.append(now)
        return None

    def record(self, dollars: float) -> None:
        day = self._day()
        self._spent = {day: self._spent.get(day, 0.0) + dollars}

    @property
    def slots(self) -> asyncio.Semaphore:
        if self._slots is None:
            self._slots = asyncio.Semaphore(self.concurrent)
        return self._slots
