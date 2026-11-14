"""The demo API: POST /api/run streams one live agent run as server-sent events.

    uvicorn demo_api.app:app --port 8080

Request body: {"scenario": "rug-pull", "option": "reef-lock"}. The response is
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
"""

from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator
from typing import Any

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, StreamingResponse
from starlette.routing import Route

from demo_api.agent import ClaudeModel, Model, run
from demo_api.limits import Limits
from demo_api.scenarios import SCENARIOS


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
            "budget_left_today_usd": round(max(0.0, LIMITS.daily_budget_usd - LIMITS.spent_today()), 4),
            "scenarios": {name: list(options) for name, (_, _, options) in SCENARIOS.items()},
        }
    )


async def run_demo(request: Request) -> JSONResponse | StreamingResponse:
    try:
        body: dict[str, Any] = await request.json()
    except ValueError:
        return JSONResponse({"error": "send JSON"}, status_code=400)
    scenario = SCENARIOS.get(str(body.get("scenario")))
    if scenario is None:
        return JSONResponse({"error": f"scenario must be one of {sorted(SCENARIOS)}"}, status_code=400)
    build, _option_name, options = scenario
    option = str(body.get("option", options[0]))
    if option not in options:
        return JSONResponse({"error": f"option must be one of {list(options)}"}, status_code=400)
    why = LIMITS.check(_visitor(request))
    if why:
        return JSONResponse({"error": why}, status_code=429)

    async def events() -> AsyncIterator[str]:
        spent = 0.0
        async with LIMITS.slots:
            try:
                async with build(option) as setup:
                    async for event in run(setup, _model()):
                        if event["type"] in ("usage", "done"):
                            spent = event["cost_usd"]
                        yield f"data: {json.dumps(event)}\n\n"
            except Exception as exc:
                yield f"data: {json.dumps({'type': 'error', 'message': f'The run failed: {type(exc).__name__}'})}\n\n"
            finally:
                LIMITS.record(spent)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


origins = [o.strip() for o in os.environ.get("DEMO_ALLOWED_ORIGINS", "http://localhost:4321").split(",") if o.strip()]

app = Starlette(
    routes=[Route("/health", health), Route("/api/run", run_demo, methods=["POST"])],
    middleware=[Middleware(CORSMiddleware, allow_origins=origins, allow_methods=["GET", "POST"], allow_headers=["content-type"])],
)
