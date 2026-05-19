# NWO Deer-Flow Conway Integration Guide

This document describes how to integrate NWO Deer-Flow (Tool #20) with the NWO Conway Relayer system.

## Overview

NWO Deer-Flow is integrated as **Tool #20** in the NWO Conway Agent ecosystem, providing advanced research and coding capabilities via ByteDance's Deer-Flow super agent harness.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    NWO CONWAY AGENT                             │
│                                                                 │
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
                     ▼ HTTP/WebSocket
        ┌──────────────────────────────┐
        │    NWO Deer-Flow Service     │
        │  ┌────────────────────────┐  │
        │  │  Deer-Flow Worker     │  │
        │  │  (Cloudflare Worker)  │  │
        │  └────────────────────────┘  │
        │           OR                 │
        │  ┌────────────────────────┐  │
        │  │  Deer-Flow Server     │  │
        │  │  (Self-hosted Docker) │  │
        │  └────────────────────────┘  │
        └──────────────────────────────┘
                     │
        ┌────────────┼────────────┐
        ▼            ▼            ▼
   ┌─────────┐ ┌─────────┐ ┌─────────────┐
   │  LLM    │ │ Sandbox │ │   Memory    │
   │ Provider│ │Execution│ │   Store     │
   └─────────┘ └─────────┘ └─────────────┘
```

## Integration Points

### 1. Cloudflare Worker (Recommended for NWO Infrastructure)

Deploy the Deer-Flow Worker alongside the NWO Agent Runner:

```javascript
// In your NWO Agent Runner v6.0+
import { DeerFlowTool } from './tools/deerflow';

// Add to tool registry
const tools = {
  ...existingTools,
  20: new DeerFlowTool(env)
};
```

**Deployment Steps:**

1. **Create KV Namespace:**
   ```bash
   wrangler kv:namespace create DEERFLOW_CACHE
   ```

2. **Set Environment Variables:**
   ```bash
   wrangler secret put DEERFLOW_API_BASE
   # Enter: https://your-deerflow-instance.com
   
   wrangler secret put DEERFLOW_API_KEY
   # Enter: your-api-key
   ```

3. **Deploy Worker:**
   ```bash
   wrangler deploy worker.ts --name nwo-deerflow-tool20
   ```

### 2. Self-Hosted (For External Users)

Users can run their own Deer-Flow instance:

```bash
# Install
pip install nwo-deerflow

# Configure
export OPENAI_API_KEY="sk-..."
# OR
export MOONSHOT_API_KEY="sk-..."

# Run server
nwo-deerflow serve --host 0.0.0.0 --port 8001
```

## Tool Schema

Tool #20 accepts the following parameters:

```json
{
  "type": "object",
  "properties": {
    "prompt": {
      "type": "string",
      "description": "The research or coding task to perform",
      "maxLength": 10000
    },
    "mode": {
      "type": "string",
      "enum": ["flash", "standard", "pro", "ultra"],
      "default": "standard",
      "description": "Execution depth and duration"
    },
    "output_format": {
      "type": "string",
      "enum": ["text", "report", "slides", "code", "web"],
      "description": "Desired output format"
    },
    "max_duration_minutes": {
      "type": "integer",
      "minimum": 1,
      "maximum": 120,
      "default": 60
    }
  },
  "required": ["prompt"]
}
```

## Usage Examples

### Example 1: Quick Research (Flash Mode)

```json
{
  "type": "deer_flow",
  "args": {
    "prompt": "What are the latest developments in humanoid robotics?",
    "mode": "flash"
  },
  "note": "Quick research on robotics"
}
```

**Expected Duration:** 1-5 minutes

### Example 2: Deep Research with Report (Pro Mode)

```json
{
  "type": "deer_flow",
  "args": {
    "prompt": "Research quantum computing applications in robotics and create a comprehensive report with actionable insights",
    "mode": "pro",
    "output_format": "report",
    "max_duration_minutes": 45
  },
  "note": "Deep research on quantum robotics"
}
```

**Expected Duration:** 15-45 minutes

### Example 3: Code Generation (Standard Mode)

```json
{
  "type": "deer_flow",
  "args": {
    "prompt": "Create a Python script that analyzes crypto market trends using TimesFM and outputs a prediction",
    "mode": "standard",
    "output_format": "code"
  },
  "note": "Generate trading analysis script"
}
```

**Expected Duration:** 5-15 minutes

### Example 4: Complex Multi-Agent Task (Ultra Mode)

```json
{
  "type": "deer_flow",
  "args": {
    "prompt": "Create a complete website for a robotics consulting business including: homepage, about page, services, and contact form. Include modern design, responsive layout, and sample content.",
    "mode": "ultra",
    "output_format": "web",
    "max_duration_minutes": 90
  },
  "note": "Build complete website with sub-agents"
}
```

**Expected Duration:** 30-120 minutes

## Mode Descriptions

| Mode | Duration | Use Case | Sub-Agents |
|------|----------|----------|------------|
| `flash` | 1-5 min | Quick answers, simple queries | No |
| `standard` | 5-15 min | General research, code generation | No |
| `pro` | 15-45 min | Deep research, complex analysis | Optional |
| `ultra` | 30-120 min | Large projects, multi-step tasks | Yes |

## Rate Limits

- **Per cycle:** 1 Deer-Flow call per agent cycle
- **Concurrent:** 2 concurrent tasks per agent (ultra mode counts as 2)
- **Timeout:** Tasks exceeding max_duration_minutes are cancelled

## Error Handling

The tool returns structured error responses:

```json
{
  "success": false,
  "output": "",
  "artifacts": [],
  "duration_seconds": 300,
  "error": "Timeout waiting for task completion"
}
```

Common errors:
- `Timeout`: Task exceeded max_duration_minutes
- `API Error`: Deer-Flow service unavailable
- `Rate Limit`: Too many concurrent requests
- `Invalid Mode`: Unknown mode specified

## Cost Considerations

Deer-Flow tasks consume LLM tokens based on mode:

| Mode | Est. Tokens | Cost (GPT-4) |
|------|-------------|--------------|
| Flash | 5K-20K | $0.15-0.60 |
| Standard | 20K-100K | $0.60-3.00 |
| Pro | 100K-500K | $3.00-15.00 |
| Ultra | 500K-2M | $15.00-60.00 |

**Note:** Ultra mode with sub-agents can be significantly more expensive.

## Security

- All API keys stored in Cloudflare Worker secrets
- No plaintext keys in code or logs
- KV cache encrypted at rest
- CORS restricted to NWO domains in production

## Monitoring

Monitor Deer-Flow usage via:

```bash
# Worker logs
wrangler tail nwo-deerflow-tool20

# Check KV cache stats
wrangler kv:key list --namespace-id=your-namespace-id

# Health check
curl https://your-worker.your-subdomain.workers.dev/health
```

## Troubleshooting

### Issue: Tasks timing out
**Solution:** Increase `max_duration_minutes` or use a faster mode.

### Issue: API errors
**Solution:** Check DEERFLOW_API_BASE and DEERFLOW_API_KEY secrets.

### Issue: High costs
**Solution:** Use lower modes (flash/standard) or implement result caching.

### Issue: Worker errors
**Solution:** Check Worker logs with `wrangler tail`.

## Future Enhancements

- [ ] Streaming responses for real-time progress
- [ ] Persistent task queue for ultra-long tasks
- [ ] Multi-modal input (images, documents)
- [ ] Custom skill loading
- [ ] Integration with NWO MR marketplace

## Support

- GitHub Issues: [github.com/RedCiprianPater/nwo-deerflow/issues](https://github.com/RedCiprianPater/nwo-deerflow/issues)
- NWO Discord: [discord.gg/nwo-robotics](https://discord.gg/nwo-robotics)

---

**Version:** 0.1.0  
**Last Updated:** 2026-05-19  
**Compatible with:** NWO Agent Runner v6.0+
