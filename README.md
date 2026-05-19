# NWO Deer-Flow Integration

**Tool #20 for NWO Conway Agents** - Advanced research and coding capabilities via ByteDance's Deer-Flow super agent harness.

[![PyPI version](https://badge.fury.io/py/nwo-deerflow.svg)](https://pypi.org/project/nwo-deerflow/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## Overview

NWO Deer-Flow integrates [ByteDance's Deer-Flow](https://github.com/bytedance/deer-flow) - a powerful open-source super agent harness - into the NWO Robotics ecosystem as **Tool #20** for Conway autonomous agents.

This integration enables NWO agents to:
- Conduct deep research tasks (minutes to hours)
- Generate code, reports, and presentations
- Create websites and visual content
- Spawn sub-agents for complex multi-step workflows
- Access sandboxed execution environments

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    NWO CONWAY AGENT                             │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────────────────┐   │
│  │ Tool 1  │ │ Tool 2  │ │  ...    │ │    Tool 20          │   │
│  │eml_regr │ │design_  │ │         │ │   deer_flow         │   │
│  │   ess   │ │  part   │ │         │ │  (THIS PACKAGE)     │   │
│  └────┬────┘ └────┬────┘ └─────────┘ └──────────┬──────────┘   │
│       └────────────┬─────────────────────────────┘              │
│                    │                                            │
│            NWO Agent Runner (Cloudflare Worker)                │
│                    │                                            │
└────────────────────┼────────────────────────────────────────────┘
                     │
                     ▼ HTTP API
        ┌──────────────────────────────┐
        │    NWO Deer-Flow Service     │
        │  (Self-hosted or NWO-hosted) │
        └──────────────┬───────────────┘
                       │
        ┌──────────────┼──────────────┐
        ▼              ▼              ▼
   ┌─────────┐   ┌─────────┐   ┌─────────────┐
   │  LLM    │   │ Sandbox │   │   Memory    │
   │ Provider│   │Execution│   │   Store     │
   └─────────┘   └─────────┘   └─────────────┘
```

## Installation

### For End Users (Connect Your Own LLM)

```bash
pip install nwo-deerflow
```

Set your environment variables:
```bash
export OPENAI_API_KEY="sk-..."
# OR
export ANTHROPIC_API_KEY="sk-ant-..."
# OR
export MOONSHOT_API_KEY="sk-..."
```

Run locally:
```bash
nwo-deerflow serve
```

### For NWO Conway Agent Integration

The NWO Deer-Flow service is automatically available to all Conway agents as Tool #20 when deployed to the NWO infrastructure.

## Quick Start

### 1. Local Development Mode

```python
from nwo_deerflow import DeerFlowClient

# Initialize client
client = DeerFlowClient(
    api_base="http://localhost:8001",
    api_key="your-api-key"  # Optional for local
)

# Submit a research task
response = client.submit_task(
    prompt="Research the latest developments in humanoid robotics and create a summary report",
    mode="pro",  # flash, standard, pro, ultra
    thread_id="my-thread-001"
)

print(f"Task ID: {response['task_id']}")
print(f"Status: {response['status']}")
```

### 2. Asynchronous Task Execution

```python
import asyncio
from nwo_deerflow import DeerFlowClient

async def run_research():
    client = DeerFlowClient()
    
    # Submit and wait for completion
    result = await client.submit_and_wait(
        prompt="Create a Python script that analyzes crypto market trends",
        mode="ultra",  # Uses sub-agents for complex coding
        timeout=3600  # Wait up to 1 hour
    )
    
    print(f"Result: {result['output']}")
    print(f"Artifacts: {result['artifacts']}")

asyncio.run(run_research())
```

### 3. Conway Agent Tool Usage

When used as Tool #20 in a Conway agent:

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

## Deployment Options

### Option A: Self-Hosted (Bring Your Own API Keys)

Deploy on your own infrastructure with your own LLM API keys:

```bash
# Clone the repository
git clone https://github.com/RedCiprianPater/nwo-deerflow.git
cd nwo-deerflow

# Configure
make setup

# Deploy with Docker
make docker-start
```

**Benefits:**
- Full control over data and execution
- Use your own LLM API keys
- Custom skill configurations
- Private sandbox environments

### Option B: NWO-Hosted (Included in Conway Agent)

Deploy as part of the NWO Conway agent infrastructure:

```bash
# Deployed automatically with NWO Agent Runner
# No additional configuration needed
# Usage billed through Conway agent's operational balance
```

**Benefits:**
- Zero setup required
- Integrated with NWO agent ecosystem
- Automatic scaling
- Shared memory across NWO tools

## Cloudflare Worker Integration

The NWO Deer-Flow integration includes a Cloudflare Worker that acts as a lightweight gateway between Conway agents and the Deer-Flow service:

```javascript
// worker.js - Deploy to Cloudflare Workers
import { DeerFlowTool } from './tools/deerflow';

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    
    if (url.pathname === '/api/tool/20/deer-flow') {
      const tool = new DeerFlowTool(env);
      return await tool.handle(request);
    }
    
    return new Response('Not Found', { status: 404 });
  }
};
```

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `DEERFLOW_API_BASE` | Deer-Flow API endpoint | `http://localhost:8001` |
| `DEERFLOW_API_KEY` | API key for authentication | None |
| `OPENAI_API_KEY` | OpenAI API key | None |
| `ANTHROPIC_API_KEY` | Anthropic API key | None |
| `MOONSHOT_API_KEY` | Moonshot/Kimi API key | None |
| `DEERFLOW_SANDBOX_MODE` | Sandbox execution mode | `docker` |
| `DEERFLOW_MAX_DURATION` | Max task duration (minutes) | 60 |

### config.yaml

```yaml
# Deer-Flow Configuration
models:
  - name: gpt-4o
    display_name: GPT-4o
    use: langchain_openai:ChatOpenAI
    model: gpt-4o
    api_key: $OPENAI_API_KEY

  - name: kimi-k2.5
    display_name: Kimi K2.5
    use: langchain_openai:ChatOpenAI
    model: kimi-k2.5
    api_key: $MOONSHOT_API_KEY
    base_url: https://api.moonshot.ai/v1

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

## API Reference

### Submit Task

```http
POST /api/tasks
Content-Type: application/json

{
  "prompt": "Research topic and generate output",
  "mode": "pro",
  "thread_id": "optional-thread-id",
  "context": {
    "previous_findings": [...],
    "constraints": [...]
  }
}
```

### Get Task Status

```http
GET /api/tasks/{task_id}
```

### List Tasks

```http
GET /api/tasks?status=running&limit=10
```

### Cancel Task

```http
POST /api/tasks/{task_id}/cancel
```

## Integration with NWO Conway Relayer

The Deer-Flow tool integrates seamlessly with the NWO Conway Relayer system:

```python
# Conway agent using Deer-Flow via relayer
from nwo_conway_relayer import ConwayAgent

agent = ConwayAgent(
    wallet_address="0x...",
    relayer_url="https://nwo-conway-relayer.onrender.com"
)

# Tool 20: Deer-Flow research
result = agent.execute_tool(
    tool_id=20,
    params={
        "prompt": "Analyze DeFi yield farming strategies",
        "mode": "ultra",
        "output_format": "report"
    }
)
```

## Modes Explained

| Mode | Description | Duration | Use Case |
|------|-------------|----------|----------|
| `flash` | Quick answers | 1-5 min | Simple queries |
| `standard` | Balanced research | 5-15 min | General research |
| `pro` | Deep research with planning | 15-45 min | Complex analysis |
| `ultra` | Multi-agent orchestration | 30-120 min | Large projects |

## Skills Available

Deer-Flow comes with built-in skills that NWO agents can leverage:

1. **Research** - Deep web research with source verification
2. **Report Generation** - Create structured reports
3. **Slide Creation** - Generate presentation decks
4. **Web Page** - Create and deploy websites
5. **Image Generation** - Generate visuals and diagrams
6. **Code Generation** - Write and test code

## Development

```bash
# Clone repository
git clone https://github.com/RedCiprianPater/nwo-deerflow.git
cd nwo-deerflow

# Install dependencies
make install

# Run tests
make test

# Start development server
make dev
```

## Contributing

We welcome contributions! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

MIT License - see [LICENSE](LICENSE) file.

## Acknowledgments

- [ByteDance Deer-Flow](https://github.com/bytedance/deer-flow) - The underlying super agent harness
- [NWO Robotics](https://github.com/RedCiprianPater/nwo-conway-relayer) - Conway agent ecosystem
- [LangChain](https://github.com/langchain-ai/langchain) - LLM framework
- [LangGraph](https://github.com/langchain-ai/langgraph) - Agent orchestration

## Support

- GitHub Issues: [github.com/RedCiprianPater/nwo-deerflow/issues](https://github.com/RedCiprianPater/nwo-deerflow/issues)
- NWO Discord: [discord.gg/nwo-robotics](https://discord.gg/nwo-robotics)

---

**Built with ❤️ by the NWO Robotics team**
