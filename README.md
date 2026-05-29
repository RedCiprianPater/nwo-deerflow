# NWO Deer-Flow

**Tool #20 for NWO Conway Agents** — a self-hostable service that wraps [ByteDance Deer-Flow](https://github.com/bytedance/deer-flow), the open-source super-agent harness, behind a stable HTTP API for deep research, code, slides, websites, and visual content. It drives the [NWO Agentic Space](https://huggingface.co/spaces/CPater/nwo-agentic) mission-control UI and is callable as Tool #20 by autonomous Conway agents on Base Mainnet.

License: **MIT**

---

## Table of contents

- [What this is](#what-this-is)
- [How it actually runs today](#how-it-actually-runs-today)
- [Architecture](#architecture)
- [Quick start](#quick-start)
- [Hosting tiers](#hosting-tiers)
- [The task shape](#the-task-shape) — one contract, every tier
- [Two execution engines](#two-execution-engines) — real harness + LM fallback
- [Bring your own LM](#bring-your-own-lm)
- [Modes](#modes)
- [Output formats](#output-formats)
- [Conway runner integration (Tool #20)](#conway-runner-integration-tool-20)
- [Cloudflare Worker / HA cluster](#cloudflare-worker--ha-cluster)
- [Configuration](#configuration)
- [API reference](#api-reference)
- [Deployment](#deployment)
- [Development](#development)
- [License](#license)

---

## What this is

The project ships two layers that can be used independently or together:

| Layer | Purpose | Location |
|-------|---------|----------|
| **nwo-deerflow service** (this repo) | A FastAPI service that runs Deer-Flow jobs, exposes a stable HTTP task API, and plugs into the NWO Conway runner as Tool #20. | `github.com/RedCiprianPater/nwo-deerflow` |
| **NWO Agentic Space** | Static front-end mission-control UI — wallet auth, BYOK for multiple LMs with fallback, per-agent terminals, output gallery, and external-agent registration. | `huggingface.co/spaces/CPater/nwo-agentic` |

Conway agents on the NWO Robotics platform call the service as Tool #20. External agents of any kind — autonomous loops, human-directed bots, third-party harnesses — submit work through the same task shape and stream output into the Space.

---

## How it actually runs today

This section is the source of truth; the rest of the README elaborates on it.

- **The live service runs at `https://nwo-deerflow.onrender.com`** (Render web service). Health: `GET /healthz`.
- The service has **two execution engines** and auto-selects at startup:
  - **`harness`** — the real ByteDance Deer-Flow (`from deerflow.client import DeerFlowClient`), used when the `deerflow` package is installed in the image.
  - **`lm`** — a direct OpenAI-compatible LM call, used as a fallback when the harness package isn't present. The service **never hard-fails** on a missing harness; it degrades to `lm` and reports which engine is live in `/healthz`.
- **Long jobs do not block.** Submitting returns a `task_id` immediately; callers poll `GET /api/tasks/{id}`. This is required because Cloudflare Workers (the Conway runner and the gateway) cannot hold a request open for the minutes-to-hours a `pro`/`ultra` job takes.
- **The Conway runner is at v6.1.1.** It submits `deer_flow` tasks, persists them, and reconciles completed results on a later cycle — so an agent's finished research flows back into its next decision.

If you read older docs that mention `pip install nwo-deerflow`, a `nwo.capital/webapp/api` endpoint, or a `nwo-ha.workers.dev` placeholder — those describe an aspirational layout. The deployed reality is the Render service above plus the Cloudflare workers you deploy yourself.

---

## Architecture

```
            NWO AGENTIC SPACE  (mission-control UI)
        huggingface.co/spaces/CPater/nwo-agentic
   agent terminals · output gallery · BYOK · wallet connect
        |            |            |            |
   1·JS bridge  2·postMessage  3·HTTP gw  4·CF Worker  5·Conway relayer
        |____________|____________|____________|____________|
                                |
                                v
              NWO Conway Agent  (Cloudflare Worker, v6.1.1)
              Tool 1 · Tool 2 · ... · Tool 20 (deer_flow)
                                |
                                v  HTTP (submit + poll)
              NWO Deer-Flow Service   (this repo, on Render)
              engine: harness | lm    https://nwo-deerflow.onrender.com
              /api/tasks · /api/tasks/{id} · /stream · /cancel · /healthz
```

The Conway runner and the optional HA-cluster worker are **proxies** that speak the task shape; the Render service is what actually executes a job. Because all tiers share one task shape, the backend is swappable by changing a single `DEERFLOW_API_BASE` env var.

---

## Quick start

### A — Hit the live service directly

```bash
# 1. Confirm it's up and see which engine is active
curl https://nwo-deerflow.onrender.com/healthz
# -> {"ok":true,"engine":"lm"|"harness","providers_configured":[...],"auth_required":false}

# 2. Submit a task
curl -X POST https://nwo-deerflow.onrender.com/api/tasks \
  -H "Content-Type: application/json" \
  -H "X-Agent-Id: my_agent_01" \
  -d '{"prompt":"Summarize this week in humanoid robotics","mode":"flash","output_format":"report"}'
# -> {"task_id":"tsk_...","status":"queued","mode":"flash"}

# 3. Poll for the result
curl https://nwo-deerflow.onrender.com/api/tasks/tsk_XXXX
# -> {"status":"completed","result":{"output":"...","artifacts":[...]}, ...}
```

> On Render's free/starter tier the first request after idle can cold-start for 30–60s. If a call hangs, wait and retry once.

### B — Run the service yourself

The service is a single FastAPI app (`server.py`). Clone, install, run:

```bash
git clone https://github.com/RedCiprianPater/nwo-deerflow.git
cd nwo-deerflow
pip install -r requirements.txt
export OPENAI_API_KEY="sk-..."        # or any supported provider
uvicorn server:app --host 0.0.0.0 --port 8001
```

This boots in `lm` mode and returns real generated output. To switch on the **real Deer-Flow harness**, install the `deerflow` package into the environment (it is not a slim PyPI library — it ships as the `bytedance/deer-flow` repo; see [Two execution engines](#two-execution-engines)), and the service flips to `engine: harness` automatically on next start.

### C — Stream live output (SSE)

```bash
curl -N https://nwo-deerflow.onrender.com/api/tasks/tsk_XXXX/stream
# data: {"level":"agent","text":"Planning the task...","ts":"..."}
# data: {"level":"agent","text":"...generated text deltas..."}
# data: {"event":"done","status":"completed"}
```

---

## Hosting tiers

All tiers accept the **same task shape** — only the base URL changes.

| Tier | Base URL | Notes |
|------|----------|-------|
| **Render (default)** | `https://nwo-deerflow.onrender.com` | The live service this repo deploys. Set provider keys in the Render dashboard. |
| **Local** | `http://localhost:8001` | `uvicorn server:app` with your own keys. Full data control. |
| **HA cluster** | `https://<your-worker>.workers.dev` | Optional Cloudflare Worker + Supabase failover in front of the Render service. You deploy it; the URL is your account's. |

There is **no** `nwo.capital/webapp/api` tier in the current deployment. If you need that, stand it up yourself and point `DEERFLOW_API_BASE` at it.

---

## The task shape

Every connection path and every tier uses this one object.

| Field | Type | Required | Values |
|-------|------|----------|--------|
| `prompt` | string | yes | 4–4000 chars |
| `mode` | string | no (default `standard`) | `flash` \| `standard` \| `pro` \| `ultra` |
| `output_format` | string | no (default `report`) | `report` \| `slides` \| `webpage` \| `image` \| `code` |
| `thread_id` | string | no | stable id linking tasks into a conversation |
| `stream_to` | string | no | `"nwo-agentic://terminal"` to surface in the Space |
| `autonomous` | boolean | no | `true` = output-only; `false` = two-way chat |
| `provider` | string | no | force a specific LM provider (see list) |
| `api_key` | string | no | BYOK passthrough; never echoed back in responses |
| `context` | object | no | `{ previous_findings: [], constraints: [] }` |

Identify the calling agent with the **`X-Agent-Id`** header (or `thread_id`). The service uses it to tag the task and route streaming output to the correct terminal tab. Omitting it lands the task with no agent association.

Submit response:

```json
{ "task_id": "tsk_...", "status": "queued", "mode": "flash" }
```

Status response when done (note the **nested `result`**):

```json
{
  "task_id": "tsk_...",
  "status": "completed",
  "result": { "output": "...", "artifacts": [ { "type": "report", "name": "...", "content": "..." } ] }
}
```

---

## Two execution engines

The service picks an engine at startup and reports it in `/healthz` (`engine`, `harness_available`, `harness_import_error`).

**Engine A — `harness` (real Deer-Flow).** When the `deerflow` package is importable, the service uses the embedded client:

```python
from deerflow.client import DeerFlowClient
client = DeerFlowClient()
for event in client.stream(message, thread_id=...):
    # event.type in {"values", "messages-tuple", "end"}
    ...
```

`client.stream()` is a synchronous generator, so the service runs it in a thread executor and bridges events back to its async loop — AI deltas stream to the terminal, and artifacts are captured from `values` state snapshots.

**Engine B — `lm` (fallback).** When the harness package is absent, the service makes a direct OpenAI-compatible (or Anthropic) call so the whole chain still produces real output. This is the default until you install the harness.

**Installing the real harness.** Deer-Flow is not a slim PyPI package — it is the `bytedance/deer-flow` repo (LangGraph-based, needs its own config and a sandbox backend). Two routes, both documented in `requirements.txt`:

```bash
# vendored (recommended): add backend/packages/harness, then
pip install ./harness
# or direct from git (heavier; pulls LangGraph + sandbox deps)
pip install "git+https://github.com/bytedance/deer-flow.git#subdirectory=backend/packages/harness"
```

You can also force a mode with `DEERFLOW_ENGINE=auto|harness|lm` — handy for cheap smoke tests.

---

## Bring your own LM

The Space stores keys in the browser's `sessionStorage` for the tab's lifetime only — never transmitted to NWO servers, never logged. Backend callers (HTTP/Worker) supply `provider` in the task body and set the matching `*_API_KEY` in the service environment, or pass a per-task `api_key` (which the service never echoes back).

The service's LM-fallback engine speaks the OpenAI-compatible Chat Completions API plus native Anthropic. Configured providers appear in `/healthz` under `providers_configured`. The Space UI advertises a broader BYOK list (OpenAI, Anthropic, Google, xAI, DeepSeek, Moonshot, Mistral, Cohere, Groq, Together, Fireworks, Perplexity, OpenRouter, Qwen, Hugging Face) with reorderable fallback priority; the service honors whichever providers have keys present.

---

## Modes

| Mode | Description | Duration | Use case |
|------|-------------|----------|----------|
| `flash` | Quick answers, no planning | 1–5 min | lookups, simple queries |
| `standard` | Balanced, single-pass | 5–15 min | general research |
| `pro` | Deep research with planning | 15–45 min | complex analysis |
| `ultra` | Multi-agent orchestration | 30–120 min | large projects, multi-step coding |

The service enforces a per-mode wall-clock ceiling so a stuck job eventually fails rather than hanging forever.

---

## Output formats

| `output_format` | Gallery section | Notes |
|-----------------|-----------------|-------|
| `report` | Reports | Markdown / PDF render |
| `slides` | Slides | Markdown slides separated by `---` |
| `webpage` | Websites | standalone HTML |
| `image` | Images | visual + description |
| `code` | Code | fenced, runnable code |

The service is format-aware: it instructs the model to emit the right structure per format.

---

## Conway runner integration (Tool #20)

The NWO Conway runner (Cloudflare Worker, **v6.1.1**) exposes `deer_flow` as Tool #20. A Conway agent emits:

```json
{
  "type": "deer_flow",
  "args": {
    "prompt": "Research quantum computing applications in robotics and generate a slide deck",
    "mode": "pro",
    "output_format": "slides"
  },
  "note": "deep research on quantum robotics"
}
```

What the runner does:

1. **(optional) registers** the agent with the Space's agent registry if `NWO_AGENTIC_REGISTER_URL` is set, so it appears under "My Agents".
2. **submits** the task to `DEERFLOW_API_BASE/api/tasks` with the agent's address as `X-Agent-Id` / `thread_id`.
3. **persists** the task under KV key `deerflow:{agent}` and returns the `task_id` immediately (no blocking).
4. **reconciles** on a later cycle: it polls `GET /api/tasks/{id}`, and when the job completes it surfaces the output preview + artifacts in the agent's cycle context — nudging the agent to mint the artifact as on-chain value via `mr_mint_item`.

Runner env vars (set in the Worker dashboard; the code already reads them):

```
DEERFLOW_API_BASE        = https://nwo-deerflow.onrender.com   # or your HA worker
NWO_AGENTIC_REGISTER_URL = https://<your-ha-worker>.workers.dev/agents/register
NWO_AGENTIC_SPACE_URL    = https://huggingface.co/spaces/CPater/nwo-agentic
DEERFLOW_API_KEY         = <optional shared secret, only if the service sets one>
```

---

## Cloudflare Worker / HA cluster

An optional Cloudflare Worker can sit in front of the Render service to add edge auth, rate-limiting, and a Supabase failover store (so the platform survives a Render outage). It speaks the same task shape and adds an `/agents/register` route.

```javascript
// worker/src/index.js
import { DeerFlowTool }     from './tools/deerflow';
import { SupabaseFailover } from './store/supabase';

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    if (url.pathname === '/api/tool/20/deer-flow') {
      return new DeerFlowTool(env).handle(request);
    }
    if (url.pathname === '/agents/register') {
      return new SupabaseFailover(env).registerAgent(await request.json());
    }
    return new Response('Not Found', { status: 404 });
  }
};
```

Deploy:

```bash
cd worker
npx wrangler kv namespace create DEERFLOW_CACHE   # paste the printed id into wrangler.toml
npx wrangler secret put SUPABASE_URL
npx wrangler secret put SUPABASE_SERVICE_KEY
npx wrangler secret put DEERFLOW_API_KEY          # optional
npx wrangler deploy
```

Set `DEERFLOW_API_BASE` (a Worker var) to `https://nwo-deerflow.onrender.com` so the Worker proxies to the Render backend. Note: the Worker is a proxy — it does **not** run Deer-Flow itself; the Render service does. Durable Objects (if used for live SSE coordination) require the Workers Paid plan.

---

## Configuration

Service environment variables:

| Variable | Description | Default |
|----------|-------------|---------|
| `DEERFLOW_API_KEY` | Shared bearer secret; if set, every request must send `Authorization: Bearer <key>` | none (open) |
| `DEERFLOW_ENGINE` | Force engine: `auto` \| `harness` \| `lm` | `auto` |
| `OPENAI_API_KEY` etc. | Server-side fallback LM keys (one or more) | none |
| `PORT` | Bound by the Dockerfile/Render | provided |

If `DEERFLOW_API_KEY` is set on the service, the Conway runner and the Worker must send the identical value. Confirm via `/healthz` → `auth_required`.

---

## API reference

```
GET  /healthz                      liveness + engine + providers + auth_required
POST /api/tasks                    submit; returns {task_id, status, mode}
GET  /api/tasks/{task_id}          status; result.{output,artifacts} when done
GET  /api/tasks?status=&limit=     list tasks
POST /api/tasks/{task_id}/cancel   cancel a running job
GET  /api/tasks/{task_id}/stream   SSE stream of live output (with keepalive)
```

HTTP status guidance for callers: `queued`/`running` → keep polling; `completed` → read `result`; `failed`/`cancelled` → read `error`; `422` → fix the task body; `401` → wrong/missing bearer token.

---

## Deployment

**Render (current production).** Push this repo, create a Render **Web Service** (the `render.yaml` Blueprint defines it), set at least one provider key (`OPENAI_API_KEY` or similar) in the dashboard, and Render serves it at `https://<service>.onrender.com`. The deploy-hook URL in Render settings is for triggering builds — it is a secret and is **not** your service URL.

**Self-hosted (BYOK).** Clone, `pip install -r requirements.txt`, set keys, `uvicorn server:app`. Full control over data and execution.

**HA cluster.** Deploy the Cloudflare Worker in front of the Render service as above.

---

## Development

```
nwo-deerflow/
├── server.py            # FastAPI service (two engines, task store, SSE)
├── requirements.txt     # fastapi/uvicorn/httpx/pydantic + DeerFlow install notes
├── Dockerfile           # binds uvicorn to $PORT
├── render.yaml          # Render Blueprint (type: web)
├── worker/              # optional Cloudflare Worker (HA cluster)
│   ├── src/index.js
│   ├── src/tools/deerflow.ts
│   └── wrangler.toml
└── db/schema.sql        # Supabase failover schema
```

---

## License

MIT — see `LICENSE`.

## Acknowledgments

[ByteDance Deer-Flow](https://github.com/bytedance/deer-flow) (the underlying harness), NWO Robotics (Conway agent ecosystem on Base Mainnet), LangChain / LangGraph.

## Support

- Issues: `github.com/RedCiprianPater/nwo-deerflow/issues`
- Space: `huggingface.co/spaces/CPater/nwo-agentic`
