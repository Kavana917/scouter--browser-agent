"""Scouter research API: run creation, source execution, snapshots, and SSE."""

from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from uuid import uuid4

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

load_dotenv()

from .browser_automation import BrowserAutomation, BrowserAutomationError, validate_open_page_url
from .groq_service import groq_is_configured, stream_answer
from .sources import ADAPTERS, BROWSER_TOOLS, TOOLS

RUNS: dict[str, dict] = {}
SUBSCRIBERS: dict[str, set[asyncio.Queue]] = {}
TASKS: set[asyncio.Task] = set()
BROWSER = BrowserAutomation()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _limit(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        return max(minimum, min(maximum, int(os.getenv(name, default))))
    except (TypeError, ValueError):
        return default


def _snapshot(run: dict) -> dict:
    return {
        "run_id": run["run_id"], "query": run["query"], "status": run["status"],
        "created_at": run["created_at"], "updated_at": run["updated_at"],
        "sources": list(run["sources"].values()), "answer": run["answer"], "last_event_id": run["event_seq"],
        "error": run.get("error"),
    }


async def _emit(run_id: str, event_type: str, payload: dict) -> None:
    run = RUNS.get(run_id)
    if not run:
        return
    run["event_seq"] += 1
    event = {"id": run["event_seq"], "type": event_type, "data": payload}
    run["events"].append(event)
    # Keep the replay buffer bounded for long-running local sessions.
    run["events"] = run["events"][-300:]
    for queue in tuple(SUBSCRIBERS.get(run_id, ())):
        try:
            queue.put_nowait(event)
        except asyncio.QueueFull:
            pass


def _set_run_status(run: dict, status: str) -> None:
    run["status"] = status
    run["updated_at"] = _now()


async def _execute_source(run_id: str, source: dict, finalize_run: bool = False) -> None:
    run = RUNS.get(run_id)
    if not run:
        return
    execution_id = source["source_execution_id"]
    source["status"] = "running"
    source["started_at"] = _now()
    run["updated_at"] = _now()
    await _emit(run_id, "source.status", {"source_execution_id": execution_id, "status": "running"})
    timeout = _limit("REQUEST_TIMEOUT_SECONDS", 12, 3, 30)
    result_limit = _limit("MAX_RESULTS_PER_SOURCE", 5, 1, 10)
    try:
        if source["tool_id"] in BROWSER_TOOLS:
            results = await BROWSER.search(source["tool_id"], source.get("url") or source["query"], result_limit)
        else:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(timeout), follow_redirects=True,
                headers={"User-Agent": "ScouterResearch/0.1 (local research workspace)"},
            ) as client:
                adapter = ADAPTERS[source["tool_id"]]
                results = await adapter(client, source["query"], result_limit)
        source["results"] = results[:result_limit]
        source["status"] = "completed" if results else "empty"
        await _emit(run_id, "source.results", {"source_execution_id": execution_id, "results": source["results"]})
        await _emit(run_id, "source.status", {"source_execution_id": execution_id, "status": source["status"]})
    except httpx.TimeoutException:
        source["status"] = "timed_out"
        source["error"] = {"code": "SOURCE_TIMEOUT", "message": "This source took too long to respond."}
        await _emit(run_id, "source.status", {"source_execution_id": execution_id, "status": source["status"], "error": source["error"]})
    except BrowserAutomationError as exc:
        source["status"] = exc.status
        source["error"] = {"code": exc.code, "message": exc.safe_message}
        await _emit(run_id, "source.status", {"source_execution_id": execution_id, "status": source["status"], "error": source["error"]})
    except httpx.HTTPStatusError as exc:
        source["status"] = "unavailable" if exc.response.status_code in {403, 429, 503} else "failed"
        source["error"] = {"code": "SOURCE_UNAVAILABLE", "message": "This source is temporarily unavailable."}
        await _emit(run_id, "source.status", {"source_execution_id": execution_id, "status": source["status"], "error": source["error"]})
    except (httpx.HTTPError, ValueError):
        source["status"] = "unavailable"
        source["error"] = {"code": "SOURCE_UNAVAILABLE", "message": "Could not retrieve results from this source."}
        await _emit(run_id, "source.status", {"source_execution_id": execution_id, "status": source["status"], "error": source["error"]})
    except Exception:
        source["status"] = "failed"
        source["error"] = {"code": "SOURCE_FAILED", "message": "Something went wrong while reading this source."}
        await _emit(run_id, "source.status", {"source_execution_id": execution_id, "status": source["status"], "error": source["error"]})
    source["finished_at"] = _now()
    run["updated_at"] = source["finished_at"]
    if finalize_run and run.get("synthesis_finished"):
        pending = any(item["status"] in {"queued", "running"} for item in run["sources"].values())
        if not pending:
            statuses = [item["status"] for item in run["sources"].values()]
            usable = any(status in {"completed", "empty"} for status in statuses)
            status = "completed" if usable and all(value in {"completed", "empty"} for value in statuses) else "partial" if usable else "failed"
            _set_run_status(run, status)
            await _emit(run_id, "run.status", {"status": status})
            await _emit(run_id, "run.completed", {"status": status})


async def _synthesize(run_id: str) -> None:
    run = RUNS[run_id]
    evidence = [item for source in run["sources"].values() for item in source["results"]]
    if not evidence:
        run["answer"] = {"status": "unavailable", "text": "No source results were available to synthesize.", "references": []}
        await _emit(run_id, "answer.updated", {"answer": run["answer"]})
        return
    if not groq_is_configured():
        run["answer"] = {
            "status": "unavailable",
            "text": "Your source results are ready. Add GROQ_API_KEY to backend/.env to enable the AI research summary.",
            "references": [],
        }
        await _emit(run_id, "answer.updated", {"answer": run["answer"]})
        return

    _set_run_status(run, "synthesizing")
    await _emit(run_id, "run.status", {"status": "synthesizing"})
    run["answer"] = {"status": "streaming", "text": "", "references": [item["evidence_id"] for item in evidence]}
    try:
        async for delta in stream_answer(run["query"], evidence):
            run["answer"]["text"] += delta
            run["updated_at"] = _now()
            await _emit(run_id, "answer.delta", {"delta": delta})
        run["answer"]["status"] = "completed"
        await _emit(run_id, "answer.updated", {"answer": run["answer"]})
    except Exception:
        run["answer"] = {
            "status": "unavailable",
            "text": "Sources were retrieved, but Groq could not complete the synthesis. Check the backend key, model access, or provider limits.",
            "references": [],
        }
        await _emit(run_id, "answer.updated", {"answer": run["answer"]})


async def _run_research(run_id: str) -> None:
    run = RUNS[run_id]
    _set_run_status(run, "planning")
    await _emit(run_id, "run.status", {"status": "planning"})

    query = run["query"]
    # Keep the core split workspace present for every query: web, Wikipedia,
    # and a YouTube panel. Extra providers are added when the question calls
    # for them (papers/images) and fit within the source budget.
    selected = ["web", "wikipedia", "youtube"]
    query_lower = query.lower()
    if any(term in query_lower for term in ("paper", "study", "studies", "academic", "research")):
        selected.append("papers")
    if any(term in query_lower for term in ("image", "images", "photo", "photos", "visual", "show me")):
        selected.append("images")
    # A regular query should show all core research panes immediately. Keep the
    # optional sources query-aware and within the configured concurrency cap.
    selected = selected[:_limit("MAX_SOURCES_PER_RUN", 6, 1, 6)]
    for tool_id in selected:
        await _add_source_record(run, tool_id)
    _set_run_status(run, "searching")
    await _emit(run_id, "run.status", {"status": "searching"})
    await asyncio.gather(*(_execute_source(run_id, source) for source in run["sources"].values()))
    while any(source["status"] in {"queued", "running"} for source in run["sources"].values()):
        await asyncio.sleep(0.1)
    await _synthesize(run_id)
    run["synthesis_finished"] = True
    while any(source["status"] in {"queued", "running"} for source in run["sources"].values()):
        await asyncio.sleep(0.1)
    statuses = [source["status"] for source in run["sources"].values()]
    completed = any(status in {"completed", "empty"} for status in statuses)
    terminal_status = "completed" if completed and all(status in {"completed", "empty"} for status in statuses) else "partial" if completed else "failed"
    _set_run_status(run, terminal_status)
    await _emit(run_id, "run.status", {"status": terminal_status})
    await _emit(run_id, "run.completed", {"status": terminal_status})


async def _add_source_record(run: dict, tool_id: str, url: str | None = None) -> dict:
    tool = next((item for item in TOOLS if item["tool_id"] == tool_id), None)
    if not tool or not tool["enabled"] or (tool_id not in ADAPTERS and tool_id not in BROWSER_TOOLS):
        raise HTTPException(status_code=400, detail={"code": "TOOL_DISABLED", "message": "That source is not available yet."})
    if tool_id == "open_page":
        try:
            url = validate_open_page_url(url or "")
        except BrowserAutomationError as exc:
            raise HTTPException(status_code=400, detail={"code": exc.code, "message": exc.safe_message}) from exc
    elif url:
        raise HTTPException(status_code=400, detail={"code": "INVALID_TARGET", "message": "A page URL is only accepted for the Open a page source."})
    source = {
        "source_execution_id": str(uuid4()), "tool_id": tool_id, "label": tool["label"],
        "query": run["query"], "status": "queued", "results": [], "error": None,
        "created_at": _now(), "url": url,
    }
    run["sources"][source["source_execution_id"]] = source
    await _emit(run["run_id"], "source.added", {"source": source})
    return source


@asynccontextmanager
async def lifespan(_: FastAPI):
    await BROWSER.start()
    yield
    for task in tuple(TASKS):
        task.cancel()
    await BROWSER.stop()


app = FastAPI(title="Scouter Research API", version="0.1.0", lifespan=lifespan)
origins = [origin.strip() for origin in os.getenv("FRONTEND_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware, allow_origins=origins, allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"], allow_headers=["Content-Type", "Last-Event-ID"],
)


class CreateRunBody(BaseModel):
    query: str = Field(min_length=1, max_length=1200)
    client_source: str = Field(default="web_app", pattern="^(web_app|browser_extension)$")


class AddSourceBody(BaseModel):
    tool_id: str = Field(min_length=1, max_length=80)
    url: str | None = Field(default=None, max_length=2048)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "groq_configured": groq_is_configured(), "browser_automation": "ready" if BROWSER.available else "unavailable"}


@app.get("/api/v1/tools")
async def list_tools() -> dict:
    return {"tools": TOOLS, "max_sources_per_run": _limit("MAX_SOURCES_PER_RUN", 6, 1, 6)}


@app.post("/api/v1/research-runs", status_code=202)
async def create_run(body: CreateRunBody, request: Request) -> dict:
    query = body.query.strip()
    if not query:
        raise HTTPException(status_code=422, detail={"code": "INVALID_QUERY", "message": "Enter a research question."})
    run_id = str(uuid4())
    frontend_origin = request.headers.get("origin", "http://localhost:5173")
    if frontend_origin not in origins:
        frontend_origin = origins[0] if origins else "http://localhost:5173"
    run = {
        "run_id": run_id, "query": query, "status": "queued", "created_at": _now(), "updated_at": _now(),
        "sources": {}, "answer": {"status": "pending", "text": "Research is underway.", "references": []},
        "events": [], "event_seq": 0, "error": None, "synthesis_finished": False,
    }
    RUNS[run_id] = run
    _set_run_status(run, "queued")
    await _emit(run_id, "run.status", {"status": "queued"})
    task = asyncio.create_task(_run_research(run_id))
    TASKS.add(task)
    task.add_done_callback(TASKS.discard)
    return {
        "run_id": run_id, "query": query, "status": run["status"],
        "workspace_url": f"{frontend_origin}/?run_id={run_id}",
        "events_url": f"/api/v1/research-runs/{run_id}/events", "sources": [],
    }


@app.get("/api/v1/research-runs/{run_id}")
async def get_run(run_id: str) -> dict:
    run = RUNS.get(run_id)
    if not run:
        raise HTTPException(status_code=404, detail={"code": "RUN_NOT_FOUND", "message": "This research run could not be found. It may have expired after the backend restarted."})
    return _snapshot(run)


@app.get("/api/v1/research-runs/{run_id}/events")
async def run_events(run_id: str, request: Request, after: int = Query(default=0, ge=0)) -> StreamingResponse:
    run = RUNS.get(run_id)
    if not run:
        raise HTTPException(status_code=404, detail={"code": "RUN_NOT_FOUND", "message": "This research run could not be found."})
    try:
        after = max(after, int(request.headers.get("last-event-id", "0")))
    except ValueError:
        pass
    queue: asyncio.Queue = asyncio.Queue(maxsize=128)
    SUBSCRIBERS.setdefault(run_id, set()).add(queue)

    async def stream_events():
        cursor = after
        try:
            for event in run["events"]:
                if event["id"] > cursor:
                    cursor = event["id"]
                    yield f"id: {event['id']}\nevent: {event['type']}\ndata: {__import__('json').dumps(event['data'], ensure_ascii=False)}\n\n"
            if run["status"] in {"completed", "partial", "failed", "cancelled"}:
                return
            while not await request.is_disconnected():
                event = await queue.get()
                if event["id"] <= cursor:
                    continue
                cursor = event["id"]
                yield f"id: {event['id']}\nevent: {event['type']}\ndata: {__import__('json').dumps(event['data'], ensure_ascii=False)}\n\n"
        finally:
            SUBSCRIBERS.get(run_id, set()).discard(queue)

    return StreamingResponse(stream_events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post("/api/v1/research-runs/{run_id}/sources", status_code=202)
async def add_source(run_id: str, body: AddSourceBody) -> dict:
    run = RUNS.get(run_id)
    if not run:
        raise HTTPException(status_code=404, detail={"code": "RUN_NOT_FOUND", "message": "This research run could not be found."})
    if len(run["sources"]) >= _limit("MAX_SOURCES_PER_RUN", 6, 1, 6):
        raise HTTPException(status_code=409, detail={"code": "RUN_LIMIT_REACHED", "message": "This run has reached its source limit."})
    source = await _add_source_record(run, body.tool_id, body.url)
    _set_run_status(run, "searching")
    await _emit(run_id, "run.status", {"status": "searching"})
    task = asyncio.create_task(_execute_source(run_id, source, finalize_run=True))
    TASKS.add(task)
    task.add_done_callback(TASKS.discard)
    return {"source": source}
