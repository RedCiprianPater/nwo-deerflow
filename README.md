# NWO Deer-Flow

**Tool #20 for NWO Conway Agents — ByteDance Deer-Flow harness for deep research, code, slides, websites, and visual content. Drives the [NWO Agentic Space](https://huggingface.co/spaces/RedCiprianPater/nwo-agentic) mission-control UI.**

[![PyPI version](https://img.shields.io/badge/pypi-nwo--deerflow-blue)](https://pypi.org/project/nwo-deerflow/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![NWO Agentic Space](https://img.shields.io/badge/HF-NWO_Agentic-orange)](https://huggingface.co/spaces/RedCiprianPater/nwo-agentic)

---

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Quick Start](#quick-start)
- [Hosting Tiers](#hosting-tiers)
- [Connection Paths · five ways to plug an agent in](#connection-paths)
- [Bring Your Own LM · 15 providers with fallback ordering](#bring-your-own-lm)
- [Modes](#modes)
- [Skills](#skills)
- [Cloudflare Worker · HA Cluster · Supabase failover](#cloudflare-worker--ha-cluster)
- [Configuration](#configuration)
- [API Reference](#api-reference)
- [Conway Relayer Integration](#conway-relayer-integration)
- [Development](#development)
- [Contributing](#contributing)
- [License](#license)
- [Acknowledgments](#acknowledgments)
- [Support](#support)

---

## Overview

NWO Deer-Flow is the integration layer that brings [ByteDance Deer-Flow](https://github.com/bytedance/deer-flow) — a powerful open-source super-agent harness — into the NWO Robotics ecosystem as **Tool #20** for Conway autonomous agents.

The project ships two layers that can be used independently or together:

| Layer | Purpose | Location |
|---|---|---|
| **`nwo-deerflow` service** (this repo) | Self-hostable Python service that wraps Deer-Flow, exposes a stable HTTP API, and plugs into the NWO Conway runner | `github.com/RedCiprianPater/nwo-deerflow` |
| **NWO Agentic Space** | Static front-end mission-control UI — wallet auth, BYOK for 15 LMs with fallback, agent terminals, output gallery, 5-way external-agent registration | `huggingface.co/spaces/RedCiprianPater/nwo-agentic` |

Conway agents on the [NWO Robotics platform](https://nwo.capital/asi) call this service as Tool #20. External agents of any kind (autonomous loops, human-directed bots, Conway agents, third-party harnesses) can register themselves with the Space and stream output through the same task shape.

### Capabilities

The integration enables NWO Conway agents and any externally-registered agent to:

- Conduct deep research (minutes to hours, multi-step planning, source verification)
- Generate code, structured reports, slide decks, websites, and visual content
- Spawn sub-agents for complex multi-step workflows
- Run code in sandboxed execution environments (local, Docker, Kubernetes)
- Stream output back to the NWO Agentic Space terminal in real time
- Operate autonomously (no chat, output-only) or two-way (LM-mediated chat)

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                      NWO AGENTIC SPACE  (mission-control UI)                │
│                  huggingface.co/spaces/RedCiprianPater/nwo-agentic          │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐  │
│   │  Agent Terminals  ·  Output Gallery  ·  BYOK (15 LMs · fallback)    │  │
│   │  Wallet Connect (Base Mainnet)  ·  3 Hosting Tiers  ·  Φ branding   │  │
│   └────┬───────────┬────────────┬─────────────┬────────────┬────────────┘  │
└────────┼───────────┼────────────┼─────────────┼────────────┼───────────────┘
         │           │            │             │            │
    ┌────▼────┐ ┌────▼────┐  ┌────▼─────┐  ┌────▼────┐  ┌────▼─────┐
    │ 1 · JS  │ │ 2 ·post │  │ 3 · HTTP │  │ 4 · CF  │  │ 5· Conway│
    │ Bridge  │ │ Message │  │ Gateway  │  │ Worker  │  │ Relayer  │
    └────┬────┘ └────┬────┘  └────┬─────┘  └────┬────┘  └────┬─────┘
         │           │            │              │            │
         └───────────┴────────────┼──────────────┴────────────┘
                                  ▼
              ┌────────────────────────────────────────────┐
              │     NWO Conway Agent  (Cloudflare Worker)  │
              │  ┌──────┐ ┌──────┐ ┌──────┐ ┌────────────┐ │
              │  │Tool 1│ │Tool 2│ │ ...  │ │  Tool 20   │ │
              │  │ ...  │ │ ...  │ │      │ │ deer_flow  │ │
              │  └──────┘ └──────┘ └──────┘ └─────┬──────┘ │
              └────────────────────────────────────┼───────┘
                                                   │
                                                   ▼ HTTP
                              ┌──────────────────────────────────┐
                              │     NWO Deer-Flow Service        │
                              │       (this repository)          │
                              │  ┌──────┐  ┌──────┐  ┌────────┐  │
                              │  │ LLM  │  │Sand- │  │ Memory │  │
                              │  │Provid│  │ box  │  │ Store  │  │
                              │  └──────┘  └──────┘  └────────┘  │
                              └──────────────────────────────────┘
```

---

## Quick Start

### A · Run the service locally (Bring Your Own LM)

```bash
pip install nwo-deerflow
```

Set at least one provider environment variable:

```bash
export OPENAI_API_KEY="sk-..."
# or
export ANTHROPIC_API_KEY="sk-ant-..."
# or any of the 15 supported providers — see Configuration below
```

Start the service:

```bash
nwo-deerflow serve
```

The HTTP API will be available at `http://localhost:8001` and is immediately addressable from the NWO Agentic Space (select the `Local` hosting tier in the Space's sub-strip).

### B · Connect a Python client

```python
from nwo_deerflow import DeerFlowClient

client = DeerFlowClient(
    api_base="http://localhost:8001",
    api_key="your-api-key",  # optional for local
)

response = client.submit_task(
    prompt="Research the latest developments in humanoid robotics and create a summary report",
    mode="pro",              # flash | standard | pro | ultra
    thread_id="my-thread-001",
)

print(f"Task ID: {response['task_id']}")
print(f"Status:  {response['status']}")
```

### C · Asynchronous task with auto-wait

```python
import asyncio
from nwo_deerflow import DeerFlowClient

async def run_research():
    client = DeerFlowClient()
    result = await client.submit_and_wait(
        prompt="Create a Python script that analyzes crypto market trends",
        mode="ultra",        # uses sub-agents for complex coding
        timeout=3600,        # wait up to 1 hour
    )
    print(f"Result:    {result['output']}")
    print(f"Artifacts: {result['artifacts']}")

asyncio.run(run_research())
```

### D · Conway Agent tool call

When used as Tool #20 inside a Conway agent definition:

```json
{
  "type": "deer_flow",
  "args": {
    "prompt": "Research quantum computing applications in robotics and generate a slide deck",
    "mode": "pro",
    "output_format": "slides",
    "max_duration_minutes": 30
  },
  "note": "Deep research on quantum robotics"
}
```

---

## Hosting Tiers

The NWO Agentic Space lets users switch between three deployment targets at runtime. The same HTTP task shape works against all three — only the base URL changes.

| Tier | URL | Notes |
|---|---|---|
| **Local** | `http://localhost:8001` | Self-hosted via `nwo-deerflow serve` — use your own keys, full data control |
| **NWO.Capital** | `https://nwo.capital/webapp/api` | NWO-hosted production endpoint, billed through Conway agent operational balance |
| **HA Cluster** | `https://nwo-ha.workers.dev` *(placeholder URL)* | Cloudflare Worker + Supabase failover, 99.99% uptime SLA, automatic regional routing |

---

## Connection Paths

The NWO Agentic Space accepts **any kind of external agent** — Conway agents (soul-bound, on-chain identity), autonomous agents (output-only loops), and human-directed agents (two-way chat with an LM key). Five paths are supported. Each registered agent appears as its own X-closable tab in the Space's terminal panel and streams output into its own log.

### 1 · JS Bridge

Same-origin embeds (Chrome extensions, page scripts, iframes with shared origin).

```javascript
const handle = window.NWO_AGENTIC.register({
  id:         'recon_01',
  name:       'Recon_01',
  owner:      '0x...',          // wallet for "My Agents" tab filter
  source:     'js-bridge',
  autonomous: false,            // true = output-only, no chat
  mode:       'pro',            // flash | standard | pro | ultra
});

handle.push('info',  'Booting recon pipeline...');
handle.push('agent', 'Scan complete · 12 nodes online');
handle.push('ok',    'Telemetry uploaded');
```

### 2 · postMessage

Cross-origin iframes (Space loaded from a different domain).

```javascript
window.postMessage({
  type:    'nwo-agentic',
  action:  'register',
  agent: {
    id:         'drone_07',
    name:       'Drone_07',
    owner:      '0x...',
    source:     'postmessage',
    autonomous: true,
    mode:       'ultra',
  }
}, '*');

// then stream output:
window.postMessage({
  type:    'nwo-agentic',
  action:  'push',
  agentId: 'drone_07',
  level:   'agent',
  text:    'Cycle 42 · obstacle map refreshed',
}, '*');
```

### 3 · HTTP Gateway

Backend agents in any language. Same shape across all three hosting tiers — swap the base URL.

```bash
curl -X POST https://nwo.capital/webapp/api/tasks \
  -H "Content-Type: application/json" \
  -H "X-Agent-Id: external_42" \
  -d '{
    "prompt":        "Summarize this week of base-mainnet activity",
    "mode":          "pro",
    "output_format": "report",
    "thread_id":     "external_42",
    "stream_to":     "nwo-agentic://terminal"
  }'
```

Response:

```json
{
  "task_id": "tsk_8f4a...",
  "status":  "queued",
  "mode":    "pro"
}
```

### 4 · Cloudflare Worker (HA Cluster route)

The HA Cluster tier proxies through a Cloudflare Worker backed by a Supabase failover store — the platform stays up even when `nwo.capital` is down. The Worker exposes the same task gateway plus a WebSocket route for live agent self-registration.

```javascript
// worker.js — deploy to Cloudflare Workers
import { DeerFlowTool }     from './tools/deerflow';
import { SupabaseFailover } from './store/supabase';

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);

    // Route 1: tool gateway (mirrors /api/tool/20/deer-flow)
    if (url.pathname === '/api/tool/20/deer-flow') {
      const tool = new DeerFlowTool(env);
      return await tool.handle(request);
    }

    // Route 2: agent self-register over WebSocket
    if (url.pathname === '/agents/register') {
      const store = new SupabaseFailover(env);
      return store.registerAgent(await request.json());
    }

    return new Response('Not Found', { status: 404 });
  }
};
```

### 5 · Conway Relayer (Python)

Production Conway agents with on-chain wallet-signed identity on Base Mainnet. The relayer mediates payments and signs every `execute_tool` call.

```python
from nwo_conway_relayer import ConwayAgent

agent = ConwayAgent(
    wallet_address = "0x...",
    relayer_url    = "https://nwo-conway-relayer.onrender.com",
)

result = agent.execute_tool(
    tool_id = 20,
    params  = {
        "prompt":        "Analyze DeFi yield strategies",
        "mode":          "ultra",                     # flash | standard | pro | ultra
        "output_format": "report",                    # report | slides | webpage | image | code
        "stream_to":     "nwo-agentic://terminal",    # surface live output in the Space
        "autonomous":    False,                       # True = no chat, just output
    },
)

print("task_id =", result["task_id"])
print("status  =", result["status"])
```

> **Autonomous vs human-directed** — every connection path supports both modes. Set `autonomous: true` for output-only loops; set `autonomous: false` and provide an LM key in the Space's BYOK section for two-way chat. Conway-relayer agents may additionally be billed against on-chain operational balance.

---

## Bring Your Own LM

The NWO Agentic Space ships with BYOK support for **15 major LM providers** and an explicit fallback chain — set keys, reorder priority with the ↑ / ↓ arrows on each card, and the harness will try providers top-to-bottom until one succeeds.

| # | Provider | Key prefix | Models |
|---|---|---|---|
| 1 | OpenAI | `sk-...` | GPT-4o, o1, o3 |
| 2 | Anthropic | `sk-ant-...` | Claude family |
| 3 | Google | `AIza...` | Gemini 2.5 |
| 4 | xAI | `xai-...` | Grok |
| 5 | DeepSeek | `sk-...` | V3, R1 |
| 6 | Moonshot | `sk-...` | Kimi K2.5 |
| 7 | Mistral | — | Large, Codestral |
| 8 | Cohere | `co...` | Command R+ |
| 9 | Groq | `gsk_...` | Llama / Mixtral (fast inference) |
| 10 | Together AI | — | Open-source model hosting |
| 11 | Fireworks AI | `fw_...` | Fast OSS inference |
| 12 | Perplexity | `pplx-...` | Sonar Pro |
| 13 | OpenRouter | `sk-or-...` | Multi-model aggregator |
| 14 | Qwen | — | Alibaba DashScope |
| 15 | Hugging Face | `hf_...` | Inference API |

**Storage** — keys live only in the browser's `sessionStorage` for the duration of the tab. They are never transmitted to NWO servers, never logged, and evaporate when the tab closes. The active provider is shown masked in the terminal (e.g. `anthropic:****1f9a`).

**Two-way mode** — once any key is set, registered non-autonomous agents flip to two-way mode and the chat input becomes active.

**Service-side configuration** — the service itself (`config.yaml`) can be configured for any LangChain-compatible model. See [Configuration](#configuration) below for the full schema.

---

## Modes

| Mode | Description | Duration | Use case |
|---|---|---|---|
| `flash` | Quick answers, no planning | 1–5 min | Simple queries, lookups |
| `standard` | Balanced research, single-pass | 5–15 min | General research |
| `pro` | Deep research with planning | 15–45 min | Complex analysis |
| `ultra` | Multi-agent orchestration, sub-agents | 30–120 min | Large projects, multi-step coding |

---

## Skills

Deer-Flow ships with six built-in skills that any NWO agent can leverage. The Space's harness section lets users toggle which skills are active for a given task.

- **Research** — deep web research with source verification
- **Report Generation** — structured Markdown / PDF reports
- **Slide Creation** — generate presentation decks
- **Web Page** — create and deploy static websites
- **Image Generation** — generate visuals and diagrams
- **Code Generation** — write and test code in sandbox

---

## Cloudflare Worker / HA Cluster

The NWO Deer-Flow integration includes a Cloudflare Worker that serves two roles:

1. **Lightweight task gateway** — proxies Conway agent calls to the Deer-Flow service, attaching auth and rate-limiting at the edge.
2. **HA cluster routing** — when the Space's `HA Cluster` tier is selected, the Worker routes through a Supabase failover store so the platform stays up even when `nwo.capital` is down. Target: 99.99% uptime.

```javascript
// worker.js — deploy to Cloudflare Workers
import { DeerFlowTool }     from './tools/deerflow';
import { SupabaseFailover } from './store/supabase';

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);

    if (url.pathname === '/api/tool/20/deer-flow') {
      const tool = new DeerFlowTool(env);
      return await tool.handle(request);
    }

    if (url.pathname === '/agents/register') {
      const store = new SupabaseFailover(env);
      return store.registerAgent(await request.json());
    }

    return new Response('Not Found', { status: 404 });
  }
};
```

Deploy:

```bash
cd worker
wrangler deploy
```

Required secrets:

```bash
wrangler secret put SUPABASE_URL
wrangler secret put SUPABASE_SERVICE_KEY
wrangler secret put DEERFLOW_API_BASE
wrangler secret put DEERFLOW_API_KEY
```

---

## Configuration

### Environment Variables

| Variable | Description | Default |
|---|---|---|
| `DEERFLOW_API_BASE` | Deer-Flow API endpoint | `http://localhost:8001` |
| `DEERFLOW_API_KEY` | API key for authentication | `None` |
| `DEERFLOW_SANDBOX_MODE` | Sandbox execution mode (`local` / `docker` / `kubernetes`) | `docker` |
| `DEERFLOW_MAX_DURATION` | Max task duration (minutes) | `60` |
| `OPENAI_API_KEY` | OpenAI key | `None` |
| `ANTHROPIC_API_KEY` | Anthropic key | `None` |
| `GOOGLE_API_KEY` | Google Gemini key | `None` |
| `XAI_API_KEY` | xAI Grok key | `None` |
| `DEEPSEEK_API_KEY` | DeepSeek key | `None` |
| `MOONSHOT_API_KEY` | Moonshot / Kimi key | `None` |
| `MISTRAL_API_KEY` | Mistral key | `None` |
| `COHERE_API_KEY` | Cohere key | `None` |
| `GROQ_API_KEY` | Groq key | `None` |
| `TOGETHER_API_KEY` | Together AI key | `None` |
| `FIREWORKS_API_KEY` | Fireworks AI key | `None` |
| `PERPLEXITY_API_KEY` | Perplexity key | `None` |
| `OPENROUTER_API_KEY` | OpenRouter key | `None` |
| `QWEN_API_KEY` | Alibaba Qwen / DashScope key | `None` |
| `HUGGINGFACE_API_KEY` | Hugging Face Inference API key | `None` |
| `SUPABASE_URL` | Supabase failover store URL (HA mode) | `None` |
| `SUPABASE_SERVICE_KEY` | Supabase service role key (HA mode) | `None` |

### `config.yaml`

```yaml
# Deer-Flow Configuration
models:
  - name: gpt-4o
    display_name: GPT-4o
    use: langchain_openai:ChatOpenAI
    model: gpt-4o
    api_key: $OPENAI_API_KEY

  - name: claude-sonnet
    display_name: Claude Sonnet
    use: langchain_anthropic:ChatAnthropic
    model: claude-sonnet-4-5
    api_key: $ANTHROPIC_API_KEY

  - name: kimi-k2.5
    display_name: Kimi K2.5
    use: langchain_openai:ChatOpenAI
    model: kimi-k2.5
    api_key: $MOONSHOT_API_KEY
    base_url: https://api.moonshot.ai/v1

  - name: deepseek-v3
    display_name: DeepSeek V3
    use: langchain_openai:ChatOpenAI
    model: deepseek-chat
    api_key: $DEEPSEEK_API_KEY
    base_url: https://api.deepseek.com/v1

  # ... add additional providers as needed

fallback:
  enabled: true
  order:
    - gpt-4o
    - claude-sonnet
    - kimi-k2.5
    - deepseek-v3

sandbox:
  use: deerflow.community.aio_sandbox:AioSandboxProvider
  # Options: local, docker, kubernetes

skills:
  - research
  - report-generation
  - slide-creation
  - web-page
  - image-generation
  - code-generation
```

---

## API Reference

### Submit task

```http
POST /api/tasks
Content-Type: application/json
X-Agent-Id: <optional agent identifier>

{
  "prompt":        "Research topic and generate output",
  "mode":          "pro",
  "output_format": "report",
  "thread_id":     "optional-thread-id",
  "stream_to":     "nwo-agentic://terminal",
  "autonomous":    false,
  "provider":      "anthropic",
  "context": {
    "previous_findings": [...],
    "constraints":       [...]
  }
}
```

Response:

```json
{
  "task_id": "tsk_8f4a...",
  "status":  "queued",
  "mode":    "pro"
}
```

### Get task status

```http
GET /api/tasks/{task_id}
```

### List tasks

```http
GET /api/tasks?status=running&limit=10
```

### Cancel task

```http
POST /api/tasks/{task_id}/cancel
```

### Stream task output (SSE)

```http
GET /api/tasks/{task_id}/stream
Accept: text/event-stream
```

### Register agent (HA Cluster route)

```http
POST /agents/register
Content-Type: application/json

{
  "id":         "external_42",
  "name":       "External_42",
  "owner":      "0x...",
  "source":     "http",
  "autonomous": false,
  "mode":       "pro"
}
```

---

## Conway Relayer Integration

The Deer-Flow tool integrates with the NWO Conway Relayer system for production agents with on-chain identity on Base Mainnet.

```python
from nwo_conway_relayer import ConwayAgent

agent = ConwayAgent(
    wallet_address = "0x...",
    relayer_url    = "https://nwo-conway-relayer.onrender.com",
)

# Tool 20: Deer-Flow research
result = agent.execute_tool(
    tool_id = 20,
    params  = {
        "prompt":        "Analyze DeFi yield farming strategies",
        "mode":          "ultra",
        "output_format": "report",
        "stream_to":     "nwo-agentic://terminal",
    },
)
```

The relayer:

- Signs every tool call with the agent's wallet
- Bills usage against the agent's on-chain operational balance
- Surfaces all output in the NWO Agentic Space terminal under the agent's tab
- Persists task results to the NWO graph for accountability

---

## Deployment

### Option A · Self-hosted (BYOK)

Deploy on your own infrastructure with your own LLM API keys.

```bash
git clone https://github.com/RedCiprianPater/nwo-deerflow.git
cd nwo-deerflow

# Configure
make setup
cp .env.example .env   # then fill in your provider keys

# Deploy with Docker
make docker-start
```

**Benefits**

- Full control over data and execution
- Use your own LLM API keys
- Custom skill configurations
- Private sandbox environments

### Option B · NWO-hosted (turnkey)

Deploy as part of the NWO Conway agent infrastructure.

- Deployed automatically with NWO Agent Runner
- No additional configuration needed
- Usage billed through Conway agent's operational balance

**Benefits**

- Zero setup required
- Integrated with NWO agent ecosystem
- Automatic scaling
- Shared memory across NWO tools

### Option C · HA Cluster (Cloudflare + Supabase)

Cloudflare Worker fronting a Supabase failover store. Targeted at 99.99% uptime.

```bash
# 1. Deploy the Cloudflare Worker
cd worker
wrangler deploy

# 2. Provision Supabase failover schema
psql $SUPABASE_DB_URL -f db/schema.sql

# 3. Set the Space's hosting tier to "HA Cluster"
```

---

## Development

```bash
# Clone repository
git clone https://github.com/RedCiprianPater/nwo-deerflow.git
cd nwo-deerflow

# Install dependencies
make install

# Run tests
make test

# Start development server (with hot-reload)
make dev

# Lint + format
make lint
make format
```

### Project structure

```
nwo-deerflow/
├── src/
│   └── nwo_deerflow/
│       ├── __init__.py
│       ├── client.py            # DeerFlowClient
│       ├── server.py            # FastAPI service
│       ├── providers/           # 15 LM provider adapters
│       ├── sandbox/             # local / docker / k8s sandbox impls
│       ├── skills/              # research / report / slides / etc.
│       └── memory/
├── worker/                      # Cloudflare Worker
│   ├── src/
│   │   ├── index.js
│   │   ├── tools/deerflow.js
│   │   └── store/supabase.js
│   └── wrangler.toml
├── db/
│   └── schema.sql               # Supabase failover schema
├── tests/
├── config.yaml.example
├── .env.example
└── README.md
```

---

## Contributing

Contributions are welcome! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines. Areas where help is especially appreciated:

- Additional LM provider adapters (the BYOK list is open-ended)
- Sandbox provider improvements (security hardening, K8s deployments)
- New skill modules
- Documentation, examples, and integration recipes

---

## License

MIT License — see [LICENSE](LICENSE).

---

## Acknowledgments

- **[ByteDance Deer-Flow](https://github.com/bytedance/deer-flow)** — the underlying super-agent harness
- **[NWO Robotics](https://nwo.capital)** — Conway agent ecosystem on Base Mainnet
- **[LangChain](https://github.com/langchain-ai/langchain)** — LLM framework
- **[LangGraph](https://github.com/langchain-ai/langgraph)** — agent orchestration

---

## Support

- **GitHub Issues** — [github.com/RedCiprianPater/nwo-deerflow/issues](https://github.com/RedCiprianPater/nwo-deerflow/issues)
- **NWO Robotics platform** — [nwo.capital/asi](https://nwo.capital/asi)
- **NWO Agentic Space** — [huggingface.co/spaces/RedCiprianPater/nwo-agentic](https://huggingface.co/spaces/RedCiprianPater/nwo-agentic)

Built with ❤️ by the NWO Robotics team.
