/**
 * NWO Deer-Flow Tool #20 - Cloudflare Worker Integration
 * 
 * This Worker acts as a gateway between NWO Conway agents and the Deer-Flow service.
 * It integrates with the NWO Agent Runner v6.0+ as Tool #20.
 */

import { DeerFlowTool } from './tools/deerflow';

export interface Env {
  // Deer-Flow service configuration
  DEERFLOW_API_BASE: string;
  DEERFLOW_API_KEY?: string;
  
  // NWO Conway integration
  CONWAY_RELAYER_URL: string;
  NWO_AGENT_RUNNER_VERSION: string;
  
  // KV for caching
  DEERFLOW_CACHE: KVNamespace;
  
  // Secrets
  WORKER_ENCRYPTION_KEY: string;
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const url = new URL(request.url);
    const path = url.pathname;
    
    // CORS headers
    const corsHeaders = {
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
      'Access-Control-Allow-Headers': 'Content-Type, Authorization',
    };
    
    if (request.method === 'OPTIONS') {
      return new Response(null, { headers: corsHeaders });
    }
    
    try {
      // Health check
      if (path === '/health') {
        return jsonResponse({
          status: 'healthy',
          service: 'nwo-deerflow-worker',
          version: '0.1.0',
          tool_id: 20,
          timestamp: new Date().toISOString()
        }, corsHeaders);
      }
      
      // Tool schema for Conway agent discovery
      if (path === '/api/tool/20/schema') {
        return jsonResponse(getToolSchema(), corsHeaders);
      }
      
      // Tool execution endpoint
      if (path === '/api/tool/20/execute' && request.method === 'POST') {
        const tool = new DeerFlowTool(env);
        const params = await request.json();
        const result = await tool.execute(params);
        return jsonResponse(result, corsHeaders);
      }
      
      // Task submission (direct API)
      if (path === '/api/tasks' && request.method === 'POST') {
        const tool = new DeerFlowTool(env);
        const params = await request.json();
        const result = await tool.submitTask(params);
        return jsonResponse(result, corsHeaders);
      }
      
      // Task status check
      if (path.startsWith('/api/tasks/') && request.method === 'GET') {
        const taskId = path.split('/')[3];
        const tool = new DeerFlowTool(env);
        const result = await tool.getTaskStatus(taskId);
        return jsonResponse(result, corsHeaders);
      }
      
      // List models
      if (path === '/api/models') {
        return jsonResponse({
          models: [
            { name: 'gpt-4o', display_name: 'GPT-4o', provider: 'openai' },
            { name: 'claude-sonnet-4', display_name: 'Claude Sonnet 4', provider: 'anthropic' },
            { name: 'kimi-k2.5', display_name: 'Kimi K2.5', provider: 'moonshot' }
          ]
        }, corsHeaders);
      }
      
      // Conway agent runner integration status
      if (path === '/api/conway/status') {
        return jsonResponse({
          tool_id: 20,
          tool_name: 'deer_flow',
          status: 'active',
          modes: ['flash', 'standard', 'pro', 'ultra'],
          features: [
            'deep_research',
            'code_generation',
            'report_creation',
            'slide_generation',
            'web_development',
            'sub_agent_orchestration'
          ]
        }, corsHeaders);
      }
      
      return new Response('Not Found', { status: 404, headers: corsHeaders });
      
    } catch (error) {
      console.error('Error:', error);
      return jsonResponse({
        success: false,
        error: error.message || 'Internal server error'
      }, corsHeaders, 500);
    }
  },
  
  // Optional: Scheduled task for cleanup
  async scheduled(event: ScheduledEvent, env: Env, ctx: ExecutionContext): Promise<void> {
    // Clean up old cached results
    const keys = await env.DEERFLOW_CACHE.list();
    const now = Date.now();
    const maxAge = 24 * 60 * 60 * 1000; // 24 hours
    
    for (const key of keys.keys) {
      if (key.metadata && key.metadata.created_at) {
        if (now - key.metadata.created_at > maxAge) {
          await env.DEERFLOW_CACHE.delete(key.name);
        }
      }
    }
  }
};

function jsonResponse(data: any, headers: Record<string, string>, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      'Content-Type': 'application/json',
      ...headers
    }
  });
}

function getToolSchema() {
  return {
    tool_id: 20,
    tool_name: 'deer_flow',
    tool_description: 'Advanced research and coding via Deer-Flow super agent harness. Conducts deep research, generates code, creates reports and presentations, and orchestrates sub-agents for complex tasks.',
    version: '0.1.0',
    parameters: {
      type: 'object',
      properties: {
        prompt: {
          type: 'string',
          description: 'The research or coding task to perform. Be specific about desired output.',
          maxLength: 10000
        },
        mode: {
          type: 'string',
          enum: ['flash', 'standard', 'pro', 'ultra'],
          default: 'standard',
          description: 'Execution depth: flash (1-5 min), standard (5-15 min), pro (15-45 min), ultra (30-120 min with sub-agents)'
        },
        output_format: {
          type: 'string',
          enum: ['text', 'report', 'slides', 'code', 'web', 'markdown'],
          description: 'Desired output format'
        },
        max_duration_minutes: {
          type: 'integer',
          minimum: 1,
          maximum: 120,
          default: 60,
          description: 'Maximum time to spend on task'
        },
        context: {
          type: 'object',
          description: 'Additional context from previous tasks or agent state'
        }
      },
      required: ['prompt']
    },
    returns: {
      type: 'object',
      properties: {
        success: { type: 'boolean' },
        output: { type: 'string', description: 'Task output/result' },
        artifacts: { 
          type: 'array',
          items: {
            type: 'object',
            properties: {
              type: { type: 'string' },
              name: { type: 'string' },
              url: { type: 'string' },
              size: { type: 'number' }
            }
          }
        },
        duration_seconds: { type: 'number' },
        token_usage: { type: 'object' },
        error: { type: 'string' }
      }
    },
    examples: [
      {
        description: 'Quick research query',
        params: {
          prompt: 'What are the latest developments in humanoid robotics?',
          mode: 'flash'
        }
      },
      {
        description: 'Deep research with report',
        params: {
          prompt: 'Research quantum computing applications in robotics and create a comprehensive report',
          mode: 'pro',
          output_format: 'report'
        }
      },
      {
        description: 'Code generation',
        params: {
          prompt: 'Create a Python script that analyzes crypto market trends using TimesFM',
          mode: 'standard',
          output_format: 'code'
        }
      }
    ],
    rate_limits: {
      per_cycle: 1,
      concurrent: 2,
      note: 'Ultra mode counts as 2 concurrent slots due to sub-agent orchestration'
    }
  };
}
