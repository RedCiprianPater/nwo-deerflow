/**
 * Deer-Flow Tool #20 — implementation for the NWO Conway Worker gateway.
 *
 * Talks to the NWO Deer-Flow execution service (server.py on Render / the HA
 * worker). Aligned to that service's REAL contract:
 *
 *   POST /api/tasks            → { task_id, status, mode }
 *   GET  /api/tasks/{task_id}  → { status, result:{output,artifacts}, error, ... }
 *
 * KEY DESIGN POINT — Cloudflare Workers cannot block a fetch() response for
 * the minutes-to-hours a pro/ultra job takes. So execute() SUBMITS and returns
 * the task_id immediately, doing only a short bounded poll (a few seconds, well
 * under the Worker limit) to opportunistically catch fast flash jobs. Anything
 * not finished in that window comes back as status:"pending" with a task_id the
 * caller polls later via getTaskStatus(). The Conway runner already works this
 * way (submit now, check next cycle).
 */

export interface DeerFlowParams {
  prompt: string;
  mode?: 'flash' | 'standard' | 'pro' | 'ultra';
  // Tool-facing formats; mapped to the service's accepted set below.
  output_format?: 'text' | 'report' | 'slides' | 'code' | 'web' | 'markdown';
  max_duration_minutes?: number;
  context?: Record<string, any>;
  // Agent identity — becomes the service thread_id and the Space terminal tab.
  agent_id?: string;
}

export interface DeerFlowResult {
  success: boolean;
  status: 'completed' | 'failed' | 'cancelled' | 'pending';
  task_id: string | null;
  output: string;
  artifacts: Array<{ type: string; name: string; url?: string; size?: number; content?: string }>;
  duration_seconds: number;
  cached?: boolean;
  viewer_url?: string;
  error?: string;
}

export interface TaskSubmission {
  task_id: string;
  status: string;
  mode?: string;
}

// Map the tool's output_format enum onto what server.py actually accepts:
//   report | slides | webpage | image | code
// (server.py coerces anything unknown to "report", so this keeps intent.)
const FORMAT_MAP: Record<string, string> = {
  text: 'report',
  markdown: 'report',
  report: 'report',
  slides: 'slides',
  web: 'webpage',
  webpage: 'webpage',
  code: 'code',
  image: 'image',
};

// How long execute() will opportunistically wait for a fast job before
// returning pending. Kept well under the Worker invocation budget.
const INLINE_WAIT_MS = 8_000;
const POLL_INTERVAL_MS = 1_500;

const SPACE_URL = 'https://huggingface.co/spaces/CPater/nwo-agentic';

export class DeerFlowTool {
  private apiBase: string;
  private apiKey?: string;
  private cache?: KVNamespace;

  constructor(env: {
    DEERFLOW_API_BASE: string;
    DEERFLOW_API_KEY?: string;
    DEERFLOW_CACHE?: KVNamespace;
  }) {
    this.apiBase = (env.DEERFLOW_API_BASE || '').replace(/\/+$/, '');
    this.apiKey = env.DEERFLOW_API_KEY;
    this.cache = env.DEERFLOW_CACHE;
  }

  private headers(agentId?: string): Record<string, string> {
    const h: Record<string, string> = { 'Content-Type': 'application/json' };
    if (this.apiKey) h['Authorization'] = `Bearer ${this.apiKey}`;
    if (agentId) h['X-Agent-Id'] = agentId;
    return h;
  }

  /**
   * Submit, then briefly poll. Returns completed result if the job finishes
   * inside INLINE_WAIT_MS (typical for flash), otherwise pending + task_id.
   */
  async execute(params: DeerFlowParams): Promise<DeerFlowResult> {
    const startTime = Date.now();

    if (!params.prompt || params.prompt.trim().length < 4) {
      return this.fail('prompt is required (min 4 chars)', null, startTime);
    }

    try {
      // Cache hit — return a prior completed result for identical input.
      const cacheKey = this.getCacheKey(params);
      if (this.cache) {
        const cached = await this.cache.get(cacheKey);
        if (cached) {
          const result = JSON.parse(cached) as DeerFlowResult;
          result.cached = true;
          return result;
        }
      }

      const submission = await this.submitTask(params);
      const taskId = submission.task_id;

      // Opportunistic bounded poll — catches fast flash jobs without ever
      // approaching the Worker wall-clock limit.
      const deadline = startTime + INLINE_WAIT_MS;
      while (Date.now() < deadline) {
        const status = await this.getTaskStatus(taskId);

        if (status.status === 'completed') {
          const result = this.toResult(true, 'completed', taskId, status, startTime);
          if (this.cache) {
            await this.cache.put(cacheKey, JSON.stringify(result), {
              expirationTtl: 3600,
              metadata: { created_at: Date.now() },
            });
          }
          return result;
        }
        if (status.status === 'failed' || status.status === 'cancelled') {
          return this.toResult(false, status.status, taskId, status, startTime);
        }
        await this.sleep(POLL_INTERVAL_MS);
      }

      // Still running — hand back the task_id for later polling. Not an error.
      return {
        success: true,
        status: 'pending',
        task_id: taskId,
        output: '',
        artifacts: [],
        duration_seconds: Math.floor((Date.now() - startTime) / 1000),
        viewer_url: SPACE_URL,
      };
    } catch (error: any) {
      return this.fail(error?.message || 'Unknown error', null, startTime);
    }
  }

  /** Submit a task to the Deer-Flow service. */
  async submitTask(params: DeerFlowParams): Promise<TaskSubmission> {
    const fmt = FORMAT_MAP[params.output_format || 'report'] || 'report';
    const response = await fetch(`${this.apiBase}/api/tasks`, {
      method: 'POST',
      headers: this.headers(params.agent_id),
      body: JSON.stringify({
        prompt: params.prompt,
        mode: params.mode || 'standard',
        output_format: fmt,
        thread_id: params.agent_id,
        stream_to: 'nwo-agentic://terminal',
        autonomous: true,
        context: params.context,
      }),
    });

    if (!response.ok) {
      const body = await response.text().catch(() => '');
      throw new Error(`Deer-Flow submit ${response.status}: ${body.slice(0, 200)}`);
    }
    return response.json();
  }

  /** Get task status from the service. */
  async getTaskStatus(taskId: string): Promise<any> {
    const response = await fetch(`${this.apiBase}/api/tasks/${encodeURIComponent(taskId)}`, {
      headers: this.headers(),
    });
    if (!response.ok) {
      const body = await response.text().catch(() => '');
      throw new Error(`Deer-Flow status ${response.status}: ${body.slice(0, 200)}`);
    }
    return response.json();
  }

  /** Cancel a running task. */
  async cancelTask(taskId: string): Promise<any> {
    const response = await fetch(`${this.apiBase}/api/tasks/${encodeURIComponent(taskId)}/cancel`, {
      method: 'POST',
      headers: this.headers(),
    });
    if (!response.ok) {
      const body = await response.text().catch(() => '');
      throw new Error(`Deer-Flow cancel ${response.status}: ${body.slice(0, 200)}`);
    }
    return response.json();
  }

  // --- helpers -------------------------------------------------------------

  // server.py nests output + artifacts under `result`. Normalize both the
  // nested shape and any flat shape (HA-worker failover rows) into DeerFlowResult.
  private toResult(
    success: boolean,
    status: 'completed' | 'failed' | 'cancelled',
    taskId: string,
    raw: any,
    startTime: number,
  ): DeerFlowResult {
    const result = raw?.result || {};
    return {
      success,
      status,
      task_id: taskId,
      output: result.output ?? raw?.output ?? '',
      artifacts: result.artifacts ?? raw?.artifacts ?? [],
      duration_seconds: Math.floor((Date.now() - startTime) / 1000),
      viewer_url: SPACE_URL,
      error: success ? undefined : (raw?.error || `task ${status}`),
    };
  }

  private fail(error: string, taskId: string | null, startTime: number): DeerFlowResult {
    return {
      success: false,
      status: 'failed',
      task_id: taskId,
      output: '',
      artifacts: [],
      duration_seconds: Math.floor((Date.now() - startTime) / 1000),
      error,
    };
  }

  private getCacheKey(params: DeerFlowParams): string {
    const key = JSON.stringify({
      p: params.prompt.slice(0, 100),
      m: params.mode,
      f: params.output_format,
    });
    return `deerflow:${btoa(unescape(encodeURIComponent(key))).slice(0, 64)}`;
  }

  private sleep(ms: number): Promise<void> {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  getMetadata() {
    return {
      tool_id: 20,
      tool_name: 'deer_flow',
      display_name: 'Deer-Flow Research',
      description: 'Advanced research and coding via Deer-Flow super agent harness',
      version: '1.1.0',
      modes: ['flash', 'standard', 'pro', 'ultra'],
      features: [
        'deep_research',
        'code_generation',
        'report_creation',
        'slide_generation',
        'web_development',
        'sub_agent_orchestration',
      ],
      rate_limits: { per_cycle: 1, concurrent: 2 },
    };
  }
}
