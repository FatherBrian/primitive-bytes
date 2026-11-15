"""The demo API: POST /api/run streams one live agent run as server-sent events.

    uvicorn demo_api.app:app --port 8080

Request body: {"scenario": "rug-pull", "option": "reef-lock"}, or for the playground
{"scenario": "playground", "config": {...}, "history": [{"role": "user", "text": ...}, ...]},
where history is a chat's earlier turns (text only, the last few kept). The response is
text/event-stream, one JSON event per `data:` line (see demo_api.agent for the event types).

Environment:
    ANTHROPIC_API_KEY        the key the runs bill to (give it a spend limit in the Console)
    DEMO_ALLOWED_ORIGINS     comma-separated origins allowed to call it (the site's address)
    DEMO_ENABLED             0 turns live runs off
    DEMO_DAILY_BUDGET_USD    default 0.50
    DEMO_RUNS_PER_10_MIN     default 5 per visitor
    DEMO_RUNS_PER_DAY        default 25 per visitor
    DEMO_MAX_CONCURRENT      default 4
    DEMO_FAKE_MODEL          1 uses a scripted model instead of Claude (tests, local dev)
    DEMO_DB                  SQLite file for saved runs (default runs.db; on a host, a volume)
    DEMO_KEEP_RUNS           how many saved runs to keep (default 5000)

GET /api/runs/{id} returns a saved run, so a link can replay it. Saved runs hold the run's
events only, nothing about the visitor.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from collections import defaultdict, deque
from collections.abc import AsyncIterator, Callable
from typing import Any

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response, StreamingResponse
from starlette.routing import Route

from demo_api.agent import ClaudeModel, Model, run
from demo_api.feed import card
from demo_api.limits import Limits
from demo_api.scenarios import SCENARIOS
from demo_api.store import RunStore
from demo_api.world.playground import (
    MAX_HISTORY,
    MAX_QUESTION,
    PRESETS,
    PROMPTS,
    ConfigError,
    history,
    parse,
    playground,
)
from demo_api.world.servers import TASKS, World
from demo_api.world.views import MIME as VIEW_MIME


def _load_dotenv(path: str = os.path.join(os.path.dirname(__file__), "..", ".env")) -> None:
    """Local runs only: read KEY=VALUE lines from api/.env without overriding the environment.

    The file is git-ignored. Hosted deployments set secrets in the host instead.
    """
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))
    except OSError:
        pass


_load_dotenv()
LIMITS = Limits()
STORE = RunStore()


def _model() -> Model:
    if os.environ.get("DEMO_FAKE_MODEL") == "1":
        from demo_api.fake import FakeModel

        return FakeModel()
    return ClaudeModel()


def _visitor(request: Request) -> str:
    # Behind a proxy (Fly, Cloudflare), the first forwarded address is the visitor.
    forwarded = request.headers.get("fly-client-ip") or request.headers.get("cf-connecting-ip")
    if not forwarded:
        forwarded = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
    return forwarded or (request.client.host if request.client else "unknown")


async def health(_request: Request) -> JSONResponse:
    return JSONResponse(
        {
            "ok": True,
            "live": LIMITS.enabled,
            "chat": {"history": MAX_HISTORY},
            "budget_left_today_usd": round(max(0.0, LIMITS.daily_budget_usd - LIMITS.spent_today()), 4),
            "scenarios": {name: list(options) for name, (_, _, options) in SCENARIOS.items()},
        }
    )


async def run_demo(request: Request) -> JSONResponse | StreamingResponse:
    try:
        body: dict[str, Any] = await request.json()
    except ValueError:
        return JSONResponse({"error": "send JSON"}, status_code=400)
    scenario_name = str(body.get("scenario"))
    build: Callable[[str], Any]
    if scenario_name == "playground":
        world = await _get_world()
        try:
            config = parse(body.get("config"), world)
            earlier = history(body.get("history"))
        except ConfigError as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)
        option = json.dumps(config.as_dict(), separators=(",", ":"))
        # A follow-up carries the visitor's earlier words, so it never shows in the feed.
        listed = config.listed and not earlier

        def build(_option: str) -> Any:
            return playground(world, config, earlier)
    else:
        scenario = SCENARIOS.get(scenario_name)
        if scenario is None:
            return JSONResponse({"error": f"scenario must be playground or one of {sorted(SCENARIOS)}"}, status_code=400)
        build, _option_name, options = scenario
        option = str(body.get("option", options[0]))
        if option not in options:
            return JSONResponse({"error": f"option must be one of {list(options)}"}, status_code=400)
        listed = True
    why = LIMITS.check(_visitor(request))
    if why:
        return JSONResponse({"error": why}, status_code=429)

    async def events() -> AsyncIterator[str]:
        spent = 0.0
        run_id = RunStore.new_id()
        saved: list[dict[str, Any]] = []
        yield f"data: {json.dumps({'type': 'run', 'id': run_id})}\n\n"
        async with LIMITS.slots:
            try:
                async with build(option) as setup:
                    async for event in run(setup, _model()):
                        if event["type"] in ("usage", "done"):
                            spent = event["cost_usd"]
                        if event["type"] != "usage":
                            saved.append(event)
                        yield f"data: {json.dumps(event)}\n\n"
            except Exception as exc:
                failed = {"type": "error", "message": f"The run failed: {type(exc).__name__}"}
                saved.append(failed)
                yield f"data: {json.dumps(failed)}\n\n"
            finally:
                LIMITS.record(spent)
                if any(e["type"] == "done" for e in saved):
                    try:
                        STORE.save(run_id, scenario_name, option, saved, spent,
                                   listed=listed, card=card(scenario_name, saved))
                    except Exception:  # a lost save never breaks the live run
                        pass

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# -- the explorer: the sample company without a model (free, so only a loose rate limit) --------------

_world: World | None = None
_world_lock = asyncio.Lock()
_browse: dict[str, deque[float]] = defaultdict(deque)
BROWSE_PER_MIN = int(os.environ.get("DEMO_BROWSE_PER_MIN", "60"))


async def _get_world() -> World:
    global _world
    async with _world_lock:
        if _world is not None and _world.ledger_size() > 40_000:
            _world.close()  # an in-memory ledger shouldn't grow forever
            _world = None
        if _world is None:
            _world = await World().start()
        return _world


def _browse_limited(request: Request) -> JSONResponse | None:
    now = time.monotonic()
    hits = _browse[_visitor(request)]
    while hits and now - hits[0] > 60:
        hits.popleft()
    if len(hits) >= BROWSE_PER_MIN:
        return JSONResponse({"error": "That's a lot of clicks. Give it a minute."}, status_code=429)
    hits.append(now)
    if len(_browse) > 10_000:
        _browse.clear()
    return None


async def world_describe(_request: Request) -> JSONResponse:
    world = await _get_world()
    out = world.describe() | {
        "prompts": [{"id": p.id, "label": p.label, "text": p.text} for p in PROMPTS.values()],
        "presets": PRESETS,
        "max_question": MAX_QUESTION,
    }
    return JSONResponse(out, headers={"Cache-Control": "public, max-age=300"})


async def world_ui(request: Request) -> JSONResponse | Response:
    """An MCP Apps view's HTML, by its ui:// address. The page renders it in a sandbox."""
    world = await _get_world()  # serve what the servers serve now, swapped views included
    html = world.views.get(request.query_params.get("uri", ""))
    if html is None:
        return JSONResponse({"error": f"uri must be one of {list(world.views)}"}, status_code=404)
    return Response(html, media_type=VIEW_MIME, headers={"Cache-Control": "public, max-age=300"})


async def world_view(request: Request) -> JSONResponse:
    if (limited := _browse_limited(request)) is not None:
        return limited
    task = request.query_params.get("task", "")
    if task not in TASKS:
        return JSONResponse({"error": f"task must be one of {list(TASKS)}"}, status_code=400)
    return JSONResponse(await (await _get_world()).view(task))


async def world_call(request: Request) -> JSONResponse:
    if (limited := _browse_limited(request)) is not None:
        return limited
    try:
        body: dict[str, Any] = await request.json()
    except ValueError:
        return JSONResponse({"error": "send JSON"}, status_code=400)
    world = await _get_world()
    server, tool, task = body.get("server"), body.get("tool"), body.get("task")
    args = body.get("arguments") or {}
    if server not in world.servers or tool not in world.servers[str(server)].tools:
        return JSONResponse({"error": "no such server or tool"}, status_code=400)
    if task is not None and task not in TASKS:
        return JSONResponse({"error": f"task must be null or one of {list(TASKS)}"}, status_code=400)
    if not isinstance(args, dict) or len(args) > 10 or len(json.dumps(args)) > 4000:
        return JSONResponse({"error": "arguments must be a small JSON object"}, status_code=400)
    return JSONResponse(await world.call(str(server), str(tool), args, task))


async def recent_runs(request: Request) -> JSONResponse:
    """The newest listed runs (preset questions only; visitors' own questions never show)."""
    try:
        limit = int(request.query_params.get("limit", "20"))
    except ValueError:
        limit = 20
    return JSONResponse({"runs": STORE.recent(limit)}, headers={"Cache-Control": "public, max-age=30"})


async def get_run(request: Request) -> JSONResponse:
    saved = STORE.get(request.path_params["run_id"])
    if saved is None:
        return JSONResponse({"error": "no run with that id (old runs are cleared out)"}, status_code=404)
    return JSONResponse(saved, headers={"Cache-Control": "public, max-age=86400"})


origins = [o.strip() for o in os.environ.get("DEMO_ALLOWED_ORIGINS", "http://localhost:4321").split(",") if o.strip()]

app = Starlette(
    routes=[
        Route("/health", health),
        Route("/api/run", run_demo, methods=["POST"]),
        Route("/api/runs", recent_runs),
        Route("/api/runs/{run_id:str}", get_run),
        Route("/api/world", world_describe),
        Route("/api/world/view", world_view),
        Route("/api/world/ui", world_ui),
        Route("/api/world/call", world_call, methods=["POST"]),
    ],
    middleware=[Middleware(CORSMiddleware, allow_origins=origins, allow_methods=["GET", "POST"], allow_headers=["content-type"])],
)
