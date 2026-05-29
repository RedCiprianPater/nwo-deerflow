"""
NWO Deer-Flow · execution service  (v1.1.0 — real harness wired)
==================================================================
The backend that ACTUALLY runs Deer-Flow jobs. The Cloudflare HA worker
and the Conway runner both POST the same task shape here:

    POST /api/tasks                 -> submit, returns {task_id, status}
    GET  /api/tasks/{task_id}       -> status + result when done
    GET  /api/tasks/{task_id}/stream-> SSE stream of live output lines
    POST /api/tasks/{task_id}/cancel-> cancel a running job
    GET  /api/tasks?status=&limit=  -> list tasks
    GET  /healthz                   -> liveness

Two layers:
  1. HTTP CONTRACT LAYER  - complete; matches worker/runner byte-for-byte.
  2. EXECUTION LAYER      - now wired to the REAL ByteDance DeerFlow harness
     via the embedded DeerFlowClient (from deerflow.client import
     DeerFlowClient). If the deerflow package is not importable in the
     running image, it degrades gracefully to a direct OpenAI-compatible LM
     call so the service never hard-fails. /healthz reports the live engine.

DeerFlow API used (confirmed against bytedance/deer-flow main):
  client = DeerFlowClient()
  for event in client.stream(message, thread_id=...):
      event.type in {"values","messages-tuple","end"}
      # messages-tuple: event.data["type"]=="ai" -> event.data["content"] is a delta
      # values:         event.data carries full state incl. "artifacts"
client.stream() is a SYNCHRONOUS generator, so we run it in a thread executor
and bridge events back to the async loop via a thread-safe queue.

Run locally:   uvicorn server:app --host 0.0.0.0 --port 8001
"""

import os
import json
import asyncio
import time
import uuid
import logging
import functools
from typing import Optional, Dict, Any, List
from contextlib import suppress

import httpx
from fastapi import FastAPI, Request, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("nwo-deerflow")

# ==========================================================================
# CONFIG
# ==========================================================================
DEERFLOW_API_KEY = os.environ.get("DEERFLOW_API_KEY", "").strip()
ENGINE_PREF = os.environ.get("DEERFLOW_ENGINE", "auto").strip().lower()  # auto|harness|lm

PROVIDER_ENV = {
    "openai":     ("OPENAI_API_KEY",     "https://api.openai.com/v1",        "gpt-4o"),
    "anthropic":  ("ANTHROPIC_API_KEY",  "https://api.anthropic.com/v1",     "claude-sonnet-4-5"),
    "moonshot":   ("MOONSHOT_API_KEY",   "https://api.moonshot.ai/v1",       "kimi-k2-0905-preview"),
    "deepseek":   ("DEEPSEEK_API_KEY",   "https://api.deepseek.com/v1",      "deepseek-chat"),
    "groq":       ("GROQ_API_KEY",       "https://api.groq.com/openai/v1",   "llama-3.3-70b-versatile"),
    "together":   ("TOGETHER_API_KEY",   "https://api.together.xyz/v1",      "meta-llama/Llama-3.3-70B-Instruct-Turbo"),
    "openrouter": ("OPENROUTER_API_KEY", "https://openrouter.ai/api/v1",     "openai/gpt-4o"),
}
FALLBACK_ORDER = [p for p in ["openai","anthropic","moonshot","deepseek","groq","together","openrouter"]
                  if os.environ.get(PROVIDER_ENV[p][0])]

VALID_MODES = {"flash","standard","pro","ultra"}
VALID_FORMATS = {"report","slides","webpage","image","code"}
MODE_TOKENS = {"flash":800,"standard":2000,"pro":4000,"ultra":8000}
MODE_TIMEOUT = {"flash":120,"standard":600,"pro":2700,"ultra":7200}

# Detect the real DeerFlow harness once, at import time.
_DEERFLOW_AVAILABLE = False
_DEERFLOW_IMPORT_ERR = None
DeerFlowClient = None
if ENGINE_PREF in ("auto","harness"):
    try:
        from deerflow.client import DeerFlowClient as _DFC  # type: ignore
        DeerFlowClient = _DFC
        _DEERFLOW_AVAILABLE = True
        log.info("DeerFlow harness detected - using embedded DeerFlowClient.")
    except Exception as e:
        _DEERFLOW_IMPORT_ERR = f"{type(e).__name__}: {e}"
        log.warning("DeerFlow harness NOT available (%s) - falling back to direct LM.", _DEERFLOW_IMPORT_ERR)

USING_HARNESS = _DEERFLOW_AVAILABLE and ENGINE_PREF != "lm"


# ==========================================================================
# STORE
# ==========================================================================
class TaskStore:
    def __init__(self):
        self._tasks: Dict[str, Dict[str, Any]] = {}
        self._streams: Dict[str, "asyncio.Queue"] = {}
        self._jobs: Dict[str, asyncio.Task] = {}
    def create(self, task):
        self._tasks[task["task_id"]] = task
        self._streams[task["task_id"]] = asyncio.Queue()
    def get(self, task_id): return self._tasks.get(task_id)
    def update(self, task_id, **fields):
        if task_id in self._tasks:
            self._tasks[task_id].update(fields)
            self._tasks[task_id]["updated_at"] = _now_iso()
    def list(self, status, limit):
        rows = list(self._tasks.values())
        if status: rows = [r for r in rows if r["status"] == status]
        rows.sort(key=lambda r: r.get("created_at",""), reverse=True)
        return rows[:limit]
    def queue(self, task_id): return self._streams.get(task_id)
    def register_job(self, task_id, job): self._jobs[task_id] = job
    def cancel_job(self, task_id):
        job = self._jobs.get(task_id)
        if job and not job.done():
            job.cancel(); return True
        return False

STORE = TaskStore()

def _now_iso(): return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
def _new_task_id(): return "tsk_" + uuid.uuid4().hex[:16]

async def _emit(task_id, level, text):
    q = STORE.queue(task_id)
    line = {"level": level, "text": text, "ts": _now_iso()}
    if q: await q.put(line)
    log.info("[%s] %s: %s", task_id, level, str(text)[:120])

def _ext_for(fmt):
    return {"report":"md","slides":"md","webpage":"html","image":"txt","code":"txt"}.get(fmt,"txt")


# ==========================================================================
# ENGINE A - real ByteDance DeerFlow harness (sync generator -> async bridge)
# ==========================================================================
def _build_message(prompt, mode, output_format):
    depth = {
        "flash":"Answer quickly and concisely; no deep multi-step planning.",
        "standard":"Do balanced, single-pass work.",
        "pro":"Do deep work: plan, research thoroughly, verify sources.",
        "ultra":"Do maximal work: decompose into sub-agents, research exhaustively, then synthesize.",
    }.get(mode,"Do balanced work.")
    fmt = {
        "report":"Produce a well-structured Markdown report.",
        "slides":"Produce a slide deck (Markdown slides separated by ---).",
        "webpage":"Produce a complete standalone HTML page.",
        "image":"Produce / generate the requested visual and describe it.",
        "code":"Produce working, runnable code in fenced code blocks.",
    }.get(output_format,"Produce a well-structured Markdown report.")
    return f"{prompt}\n\n[Output format] {fmt}\n[Effort] {depth}"

def _run_harness_blocking(task_id, prompt, mode, output_format, thread_id, loop, bridge):
    def push(kind, payload):
        asyncio.run_coroutine_threadsafe(bridge.put((kind, payload)), loop)
    try:
        client = DeerFlowClient()
        message = _build_message(prompt, mode, output_format)
        text_parts, artifacts = [], []
        for event in client.stream(message, thread_id=thread_id):
            etype = getattr(event, "type", None)
            data = getattr(event, "data", None) or {}
            if etype == "messages-tuple":
                if isinstance(data, dict) and data.get("type") == "ai":
                    delta = data.get("content") or ""
                    if delta:
                        text_parts.append(delta)
                        push("line", {"level":"agent","text":delta})
                else:
                    tname = (data.get("name") if isinstance(data, dict) else None) or "tool"
                    push("line", {"level":"info","text":f"\u00b7 {tname}"})
            elif etype == "values":
                if isinstance(data, dict) and data.get("artifacts"):
                    artifacts = data["artifacts"]
            elif etype == "end":
                break
        push("final", {"output":"".join(text_parts).strip(), "artifacts":artifacts})
    except Exception as e:
        push("error", f"{type(e).__name__}: {e}")

async def _execute_harness(task_id, prompt, mode, output_format, thread_id):
    loop = asyncio.get_running_loop()
    bridge = asyncio.Queue()
    fut = loop.run_in_executor(None, functools.partial(
        _run_harness_blocking, task_id, prompt, mode, output_format, thread_id, loop, bridge))
    output, artifacts, error = "", [], None
    while True:
        if fut.done() and bridge.empty():
            break
        try:
            kind, payload = await asyncio.wait_for(bridge.get(), timeout=1.0)
        except asyncio.TimeoutError:
            continue
        if kind == "line":
            await _emit(task_id, payload["level"], payload["text"])
        elif kind == "final":
            output, artifacts = payload["output"], payload["artifacts"]
        elif kind == "error":
            error = payload
    with suppress(Exception):
        await fut
    if error:
        raise RuntimeError(error)
    if not artifacts:
        artifacts = [{"type":output_format,"name":f"{task_id}.{_ext_for(output_format)}","content":output}]
    return output, artifacts


# ==========================================================================
# ENGINE B - direct LM fallback
# ==========================================================================
async def _resolve_lm(task):
    ep = (task.get("provider") or "").strip().lower()
    ek = (task.get("api_key") or "").strip()
    if ep and ep in PROVIDER_ENV:
        env_name, base, model = PROVIDER_ENV[ep]
        key = ek or os.environ.get(env_name, "")
        if key: return ep, key, base, model
    for p in FALLBACK_ORDER:
        env_name, base, model = PROVIDER_ENV[p]
        key = os.environ.get(env_name, "")
        if key: return p, key, base, model
    return None, None, None, None

async def _call_lm(base, key, model, provider, system, user, max_tokens):
    async with httpx.AsyncClient(timeout=120) as client:
        if provider == "anthropic":
            r = await client.post(f"{base}/messages",
                headers={"x-api-key":key,"anthropic-version":"2023-06-01","Content-Type":"application/json"},
                json={"model":model,"max_tokens":max_tokens,"system":system,
                      "messages":[{"role":"user","content":user}]})
            r.raise_for_status()
            data = r.json()
            return "".join(b.get("text","") for b in data.get("content",[]) if b.get("type")=="text")
        r = await client.post(f"{base}/chat/completions",
            headers={"Authorization":f"Bearer {key}","Content-Type":"application/json"},
            json={"model":model,"max_tokens":max_tokens,
                  "messages":[{"role":"system","content":system},{"role":"user","content":user}]})
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]

async def _execute_lm(task_id, task, prompt, mode, output_format):
    provider, key, base, model = await _resolve_lm(task)
    if not key:
        raise RuntimeError("No LM provider available. Set one of "
            f"{[PROVIDER_ENV[p][0] for p in PROVIDER_ENV]} on the service, or pass provider+api_key on the task.")
    await _emit(task_id, "info", f"LM fallback \u00b7 provider={provider} ({model})")
    system = ("You are NWO Deer-Flow, a super-agent harness. Produce a "
              f"{output_format} for the user's request, to a depth appropriate for '{mode}' mode. "
              "Be thorough and well-structured.")
    await _emit(task_id, "agent", "Planning the task...")
    output = await _call_lm(base, key, model, provider, system, prompt, MODE_TOKENS.get(mode,2000))
    await _emit(task_id, "agent", "Generation complete.")
    artifacts = [{"type":output_format,"name":f"{task_id}.{_ext_for(output_format)}","content":output}]
    return output, artifacts


# ==========================================================================
# JOB RUNNER
# ==========================================================================
async def run_deerflow_job(task_id):
    task = STORE.get(task_id)
    if not task: return
    prompt = task["prompt"]; mode = task["mode"]; output_format = task["output_format"]
    thread_id = task.get("agent_id") or task_id
    timeout = MODE_TIMEOUT.get(mode, 600)
    try:
        STORE.update(task_id, status="running")
        engine = "harness" if USING_HARNESS else "lm"
        await _emit(task_id, "info", f"Task started \u00b7 mode={mode} \u00b7 format={output_format} \u00b7 engine={engine}")
        coro = (_execute_harness(task_id, prompt, mode, output_format, thread_id)
                if USING_HARNESS else _execute_lm(task_id, task, prompt, mode, output_format))
        output, artifacts = await asyncio.wait_for(coro, timeout=timeout)
        STORE.update(task_id, status="completed", result={"output":output,"artifacts":artifacts})
        await _emit(task_id, "ok", "Task completed.")
    except asyncio.TimeoutError:
        msg = f"task exceeded {timeout}s timeout for mode '{mode}'"
        STORE.update(task_id, status="failed", error=msg)
        with suppress(Exception): await _emit(task_id, "err", msg)
    except asyncio.CancelledError:
        STORE.update(task_id, status="cancelled")
        with suppress(Exception): await _emit(task_id, "warn", "Task cancelled.")
        raise
    except httpx.HTTPStatusError as e:
        msg = f"LM HTTP {e.response.status_code}: {e.response.text[:200]}"
        STORE.update(task_id, status="failed", error=msg)
        with suppress(Exception): await _emit(task_id, "err", msg)
    except Exception as e:
        msg = f"{type(e).__name__}: {e}"
        STORE.update(task_id, status="failed", error=msg)
        with suppress(Exception): await _emit(task_id, "err", msg)
    finally:
        q = STORE.queue(task_id)
        if q: await q.put(None)


# ==========================================================================
# HTTP CONTRACT LAYER
# ==========================================================================
app = FastAPI(title="NWO Deer-Flow Service", version="1.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

class TaskIn(BaseModel):
    prompt: str
    mode: str = "standard"
    output_format: str = "report"
    thread_id: Optional[str] = None
    stream_to: Optional[str] = None
    autonomous: Optional[bool] = False
    provider: Optional[str] = None
    api_key: Optional[str] = None
    context: Optional[Dict[str, Any]] = None

def _check_auth(authorization):
    if not DEERFLOW_API_KEY: return
    if authorization != f"Bearer {DEERFLOW_API_KEY}":
        raise HTTPException(status_code=401, detail="invalid or missing bearer token")

@app.get("/healthz")
async def healthz():
    return {"ok":True,"service":"nwo-deerflow-service",
            "engine":"harness" if USING_HARNESS else "lm",
            "harness_available":_DEERFLOW_AVAILABLE,
            "harness_import_error":_DEERFLOW_IMPORT_ERR,
            "providers_configured":FALLBACK_ORDER,
            "auth_required":bool(DEERFLOW_API_KEY)}

@app.post("/api/tasks")
async def submit_task(task_in: TaskIn, request: Request,
                      authorization: Optional[str] = Header(None),
                      x_agent_id: Optional[str] = Header(None)):
    _check_auth(authorization)
    mode = task_in.mode if task_in.mode in VALID_MODES else "standard"
    fmt = task_in.output_format if task_in.output_format in VALID_FORMATS else "report"
    prompt = (task_in.prompt or "").strip()
    if not (4 <= len(prompt) <= 4000):
        raise HTTPException(status_code=422, detail="prompt must be 4-4000 chars")
    task_id = _new_task_id()
    task = {"task_id":task_id,"agent_id":x_agent_id or task_in.thread_id,"prompt":prompt,
            "mode":mode,"output_format":fmt,"provider":task_in.provider,"api_key":task_in.api_key,
            "status":"queued","source":"origin","result":None,"error":None,
            "created_at":_now_iso(),"updated_at":_now_iso()}
    STORE.create(task)
    job = asyncio.create_task(run_deerflow_job(task_id))
    STORE.register_job(task_id, job)
    return JSONResponse({"task_id":task_id,"status":"queued","mode":mode})

@app.get("/api/tasks/{task_id}")
async def get_task(task_id: str, authorization: Optional[str] = Header(None)):
    _check_auth(authorization)
    task = STORE.get(task_id)
    if not task: raise HTTPException(status_code=404, detail="task not found")
    return {k:v for k,v in task.items() if k != "api_key"}

@app.get("/api/tasks")
async def list_tasks(status: Optional[str] = None, limit: int = 20,
                     authorization: Optional[str] = Header(None)):
    _check_auth(authorization)
    limit = max(1, min(limit, 100))
    rows = STORE.list(status, limit)
    return {"tasks":[{k:v for k,v in r.items() if k != "api_key"} for r in rows]}

@app.post("/api/tasks/{task_id}/cancel")
async def cancel_task(task_id: str, authorization: Optional[str] = Header(None)):
    _check_auth(authorization)
    if not STORE.get(task_id): raise HTTPException(status_code=404, detail="task not found")
    cancelled = STORE.cancel_job(task_id)
    STORE.update(task_id, status="cancelled")
    return {"task_id":task_id,"status":"cancelled","was_running":cancelled}

@app.get("/api/tasks/{task_id}/stream")
async def stream_task(task_id: str, authorization: Optional[str] = Header(None)):
    _check_auth(authorization)
    if not STORE.get(task_id): raise HTTPException(status_code=404, detail="task not found")
    async def event_gen():
        q = STORE.queue(task_id)
        if q is None: return
        while True:
            try:
                line = await asyncio.wait_for(q.get(), timeout=15.0)
            except asyncio.TimeoutError:
                yield ": keepalive\n\n"; continue
            if line is None:
                final = STORE.get(task_id)
                payload = {"event":"done","status":final["status"] if final else "unknown"}
                yield f"data: {json.dumps(payload)}\n\n"; break
            yield f"data: {json.dumps(line)}\n\n"
    return StreamingResponse(event_gen(), media_type="text/event-stream",
        headers={"Cache-Control":"no-cache","Connection":"keep-alive"})
