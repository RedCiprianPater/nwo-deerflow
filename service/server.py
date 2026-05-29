"""
NWO Deer-Flow · execution service
==================================================================
The backend that ACTUALLY runs Deer-Flow jobs. The Cloudflare HA
worker and the Conway runner both POST the same task shape here:

    POST /api/tasks                 → submit, returns {task_id, status}
    GET  /api/tasks/{task_id}       → status + result when done
    GET  /api/tasks/{task_id}/stream→ SSE stream of live output lines
    POST /api/tasks/{task_id}/cancel→ cancel a running job
    GET  /api/tasks?status=&limit=  → list tasks
    GET  /healthz                   → liveness

This file is split into two clearly-marked layers:

  1. HTTP CONTRACT LAYER  — complete, do not need to touch. Matches the
     worker/runner shape byte-for-byte.

  2. EXECUTION LAYER      — run_deerflow_job(). This is the ONLY place the
     real ByteDance Deer-Flow harness call goes. It ships today with a
     working LM-call implementation (so the whole chain runs end-to-end
     and returns real output), plus a clearly-marked TODO showing exactly
     where to drop the Deer-Flow harness invocation once you confirm its
     Python API.

Storage: in-memory dict by default (fine for a single Render instance).
If you scale to >1 instance, point STORE at Supabase/Redis instead — the
task shape is already Supabase-compatible (see store comments).

Run locally:   uvicorn server:app --host 0.0.0.0 --port 8001
Run on Render: handled by Dockerfile CMD (uses $PORT)
"""

import os
import json
import asyncio
import time
import uuid
import logging
from typing import Optional, Dict, Any, List
from contextlib import suppress

import httpx
from fastapi import FastAPI, Request, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel, Field

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("nwo-deerflow")

# ==========================================================================
# CONFIG
# ==========================================================================

# Optional shared secret. If set, every request must send
# `Authorization: Bearer <DEERFLOW_API_KEY>`. The worker forwards this
# header automatically when its own DEERFLOW_API_KEY secret is set.
DEERFLOW_API_KEY = os.environ.get("DEERFLOW_API_KEY", "").strip()

# Server-side fallback LM keys. BYOK keys arrive per-request in the task
# body (field `provider` + the key passed through), but if a task arrives
# with no key, the service falls back to whatever is configured here.
PROVIDER_ENV = {
    "openai":     ("OPENAI_API_KEY",     "https://api.openai.com/v1",        "gpt-4o"),
    "anthropic":  ("ANTHROPIC_API_KEY",  "https://api.anthropic.com/v1",     "claude-sonnet-4-5"),
    "moonshot":   ("MOONSHOT_API_KEY",   "https://api.moonshot.ai/v1",       "kimi-k2-0905-preview"),
    "deepseek":   ("DEEPSEEK_API_KEY",   "https://api.deepseek.com/v1",      "deepseek-chat"),
    "groq":       ("GROQ_API_KEY",       "https://api.groq.com/openai/v1",   "llama-3.3-70b-versatile"),
    "together":   ("TOGETHER_API_KEY",   "https://api.together.xyz/v1",      "meta-llama/Llama-3.3-70B-Instruct-Turbo"),
    "openrouter": ("OPENROUTER_API_KEY", "https://openrouter.ai/api/v1",     "openai/gpt-4o"),
}

# Order the fallback chain walks when no provider is specified on the task.
FALLBACK_ORDER = [
    p for p in ["openai", "anthropic", "moonshot", "deepseek", "groq", "together", "openrouter"]
    if os.environ.get(PROVIDER_ENV[p][0])
]

VALID_MODES = {"flash", "standard", "pro", "ultra"}
VALID_FORMATS = {"report", "slides", "webpage", "image", "code"}

# Token budget per mode — rough proxy for "depth of work".
MODE_TOKENS = {"flash": 800, "standard": 2000, "pro": 4000, "ultra": 8000}


# ==========================================================================
# STORE  (in-memory; swap for Supabase/Redis if you run >1 instance)
# ==========================================================================

class TaskStore:
    """
    Minimal task ledger. Shape matches the Supabase `tasks` table so you
    can lift-and-shift to PostgREST later with no field renames.
    """
    def __init__(self):
        self._tasks: Dict[str, Dict[str, Any]] = {}
        # task_id -> asyncio.Queue of SSE line dicts
        self._streams: Dict[str, "asyncio.Queue"] = {}
        # task_id -> asyncio.Task (the running job, for cancellation)
        self._jobs: Dict[str, asyncio.Task] = {}

    def create(self, task: Dict[str, Any]):
        self._tasks[task["task_id"]] = task
        self._streams[task["task_id"]] = asyncio.Queue()

    def get(self, task_id: str) -> Optional[Dict[str, Any]]:
        return self._tasks.get(task_id)

    def update(self, task_id: str, **fields):
        if task_id in self._tasks:
            self._tasks[task_id].update(fields)
            self._tasks[task_id]["updated_at"] = _now_iso()

    def list(self, status: Optional[str], limit: int) -> List[Dict[str, Any]]:
        rows = list(self._tasks.values())
        if status:
            rows = [r for r in rows if r["status"] == status]
        rows.sort(key=lambda r: r.get("created_at", ""), reverse=True)
        return rows[:limit]

    def queue(self, task_id: str) -> Optional["asyncio.Queue"]:
        return self._streams.get(task_id)

    def register_job(self, task_id: str, job: asyncio.Task):
        self._jobs[task_id] = job

    def cancel_job(self, task_id: str) -> bool:
        job = self._jobs.get(task_id)
        if job and not job.done():
            job.cancel()
            return True
        return False


STORE = TaskStore()


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _new_task_id() -> str:
    return "tsk_" + uuid.uuid4().hex[:16]


async def _emit(task_id: str, level: str, text: str):
    """Push a line into the task's SSE stream and log it."""
    q = STORE.queue(task_id)
    line = {"level": level, "text": text, "ts": _now_iso()}
    if q:
        await q.put(line)
    log.info("[%s] %s: %s", task_id, level, text[:120])


# ==========================================================================
# EXECUTION LAYER  ←──────────  THIS IS THE ONLY PART YOU CUSTOMIZE
# ==========================================================================
#
# run_deerflow_job() is what turns a prompt into output. It currently does
# a real LM call (so the whole chain works today and returns genuine
# generated text). The clearly-marked TODO block is where the ByteDance
# Deer-Flow harness invocation goes once you confirm its Python API.
#
# Contract this function must honor:
#   - emit progress lines via _emit(task_id, level, text)
#   - on success: STORE.update(task_id, status="completed",
#                              result={...}, ...)
#   - on failure: STORE.update(task_id, status="failed", error="...")
#   - respect asyncio.CancelledError (raised by /cancel) — let it propagate
# --------------------------------------------------------------------------

async def _resolve_lm(task: Dict[str, Any]):
    """Pick provider + key. Per-task `provider`+`api_key`, else fallback chain."""
    # BYOK: task may carry its own key (Space passes it through per-request)
    explicit_provider = (task.get("provider") or "").strip().lower()
    explicit_key = (task.get("api_key") or "").strip()

    if explicit_provider and explicit_provider in PROVIDER_ENV:
        env_name, base, model = PROVIDER_ENV[explicit_provider]
        key = explicit_key or os.environ.get(env_name, "")
        if key:
            return explicit_provider, key, base, model

    for p in FALLBACK_ORDER:
        env_name, base, model = PROVIDER_ENV[p]
        key = os.environ.get(env_name, "")
        if key:
            return p, key, base, model

    return None, None, None, None


async def _call_lm(base: str, key: str, model: str, provider: str,
                   system: str, user: str, max_tokens: int) -> str:
    """OpenAI-compatible chat completion (covers all providers above except
    raw Anthropic, which is handled separately)."""
    async with httpx.AsyncClient(timeout=120) as client:
        if provider == "anthropic":
            r = await client.post(
                f"{base}/messages",
                headers={
                    "x-api-key": key,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "max_tokens": max_tokens,
                    "system": system,
                    "messages": [{"role": "user", "content": user}],
                },
            )
            r.raise_for_status()
            data = r.json()
            return "".join(
                b.get("text", "") for b in data.get("content", [])
                if b.get("type") == "text"
            )
        else:
            r = await client.post(
                f"{base}/chat/completions",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json={
                    "model": model,
                    "max_tokens": max_tokens,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                },
            )
            r.raise_for_status()
            data = r.json()
            return data["choices"][0]["message"]["content"]


async def run_deerflow_job(task_id: str):
    """The job body. Runs in the background; streams progress; writes result."""
    task = STORE.get(task_id)
    if not task:
        return

    prompt = task["prompt"]
    mode = task["mode"]
    output_format = task["output_format"]
    max_tokens = MODE_TOKENS.get(mode, 2000)

    try:
        STORE.update(task_id, status="running")
        await _emit(task_id, "info", f"Task started · mode={mode} · format={output_format}")

        provider, key, base, model = await _resolve_lm(task)
        if not key:
            raise RuntimeError(
                "No LM provider available. Set one of "
                f"{[PROVIDER_ENV[p][0] for p in PROVIDER_ENV]} on the service, "
                "or pass provider+api_key on the task."
            )
        await _emit(task_id, "info", f"Provider: {provider} ({model})")

        # ===================================================================
        # TODO · DROP THE REAL BYTEDANCE DEER-FLOW HARNESS CALL HERE
        # -------------------------------------------------------------------
        # Replace the single _call_lm() below with the actual harness. Based
        # on the Deer-Flow repo, this will look roughly like:
        #
        #     from deerflow import Harness          # confirm real import path
        #     harness = Harness(
        #         model=model, api_key=key, base_url=base,
        #         skills=["research", "report-generation", "slide-creation",
        #                 "web-page", "image-generation", "code-generation"],
        #         sandbox=os.environ.get("DEERFLOW_SANDBOX_MODE", "docker"),
        #     )
        #     async for event in harness.run(prompt=prompt, mode=mode,
        #                                     output_format=output_format):
        #         await _emit(task_id, "agent", event.text)   # stream progress
        #     output = harness.result.output
        #     artifacts = harness.result.artifacts
        #
        # Keep the _emit() calls so output keeps streaming to the Space
        # terminal. Keep the status/result writes below unchanged.
        # ===================================================================

        system = (
            "You are NWO Deer-Flow, a super-agent harness. Produce a "
            f"{output_format} for the user's request. Be thorough and "
            "well-structured. Work to a depth appropriate for the "
            f"'{mode}' mode."
        )
        await _emit(task_id, "agent", "Planning the task...")
        output = await _call_lm(base, key, model, provider, system, prompt, max_tokens)
        await _emit(task_id, "agent", "Generation complete.")

        artifacts = [{
            "type": output_format,
            "name": f"{task_id}.{_ext_for(output_format)}",
            "content": output,
        }]

        # --- end execution; record result -------------------------------
        STORE.update(
            task_id,
            status="completed",
            result={"output": output, "artifacts": artifacts},
        )
        await _emit(task_id, "ok", "Task completed.")

    except asyncio.CancelledError:
        STORE.update(task_id, status="cancelled")
        with suppress(Exception):
            await _emit(task_id, "warn", "Task cancelled.")
        raise
    except httpx.HTTPStatusError as e:
        msg = f"LM HTTP {e.response.status_code}: {e.response.text[:200]}"
        STORE.update(task_id, status="failed", error=msg)
        with suppress(Exception):
            await _emit(task_id, "err", msg)
    except Exception as e:
        msg = f"{type(e).__name__}: {e}"
        STORE.update(task_id, status="failed", error=msg)
        with suppress(Exception):
            await _emit(task_id, "err", msg)
    finally:
        # signal stream end
        q = STORE.queue(task_id)
        if q:
            await q.put(None)


def _ext_for(fmt: str) -> str:
    return {"report": "md", "slides": "md", "webpage": "html",
            "image": "txt", "code": "txt"}.get(fmt, "txt")


# ==========================================================================
# HTTP CONTRACT LAYER  (complete — matches worker/runner exactly)
# ==========================================================================

app = FastAPI(title="NWO Deer-Flow Service", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class TaskIn(BaseModel):
    prompt: str
    mode: str = "standard"
    output_format: str = "report"
    thread_id: Optional[str] = None
    stream_to: Optional[str] = None
    autonomous: Optional[bool] = False
    provider: Optional[str] = None
    api_key: Optional[str] = None          # BYOK passthrough (optional)
    context: Optional[Dict[str, Any]] = None


def _check_auth(authorization: Optional[str]):
    if not DEERFLOW_API_KEY:
        return
    expected = f"Bearer {DEERFLOW_API_KEY}"
    if authorization != expected:
        raise HTTPException(status_code=401, detail="invalid or missing bearer token")


@app.get("/healthz")
async def healthz():
    return {
        "ok": True,
        "service": "nwo-deerflow-service",
        "providers_configured": FALLBACK_ORDER,
        "auth_required": bool(DEERFLOW_API_KEY),
    }


@app.post("/api/tasks")
async def submit_task(
    task_in: TaskIn,
    request: Request,
    authorization: Optional[str] = Header(None),
    x_agent_id: Optional[str] = Header(None),
):
    _check_auth(authorization)

    mode = task_in.mode if task_in.mode in VALID_MODES else "standard"
    fmt = task_in.output_format if task_in.output_format in VALID_FORMATS else "report"
    prompt = (task_in.prompt or "").strip()
    if not (4 <= len(prompt) <= 4000):
        raise HTTPException(status_code=422, detail="prompt must be 4-4000 chars")

    task_id = _new_task_id()
    task = {
        "task_id": task_id,
        "agent_id": x_agent_id or task_in.thread_id,
        "prompt": prompt,
        "mode": mode,
        "output_format": fmt,
        "provider": task_in.provider,
        "api_key": task_in.api_key,
        "status": "queued",
        "source": "origin",
        "result": None,
        "error": None,
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }
    STORE.create(task)

    job = asyncio.create_task(run_deerflow_job(task_id))
    STORE.register_job(task_id, job)

    # response strips the api_key — never echo a secret back
    return JSONResponse({"task_id": task_id, "status": "queued", "mode": mode})


@app.get("/api/tasks/{task_id}")
async def get_task(task_id: str, authorization: Optional[str] = Header(None)):
    _check_auth(authorization)
    task = STORE.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="task not found")
    # don't leak api_key
    safe = {k: v for k, v in task.items() if k != "api_key"}
    return safe


@app.get("/api/tasks")
async def list_tasks(status: Optional[str] = None, limit: int = 20,
                     authorization: Optional[str] = Header(None)):
    _check_auth(authorization)
    limit = max(1, min(limit, 100))
    rows = STORE.list(status, limit)
    safe = [{k: v for k, v in r.items() if k != "api_key"} for r in rows]
    return {"tasks": safe}


@app.post("/api/tasks/{task_id}/cancel")
async def cancel_task(task_id: str, authorization: Optional[str] = Header(None)):
    _check_auth(authorization)
    task = STORE.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="task not found")
    cancelled = STORE.cancel_job(task_id)
    STORE.update(task_id, status="cancelled")
    return {"task_id": task_id, "status": "cancelled", "was_running": cancelled}


@app.get("/api/tasks/{task_id}/stream")
async def stream_task(task_id: str, authorization: Optional[str] = Header(None)):
    _check_auth(authorization)
    if not STORE.get(task_id):
        raise HTTPException(status_code=404, detail="task not found")

    async def event_gen():
        q = STORE.queue(task_id)
        if q is None:
            return
        # replay nothing (in-memory) but stream live lines until sentinel
        while True:
            line = await q.get()
            if line is None:  # job finished
                final = STORE.get(task_id)
                payload = {"event": "done", "status": final["status"] if final else "unknown"}
                yield f"data: {json.dumps(payload)}\n\n"
                break
            yield f"data: {json.dumps(line)}\n\n"

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )
