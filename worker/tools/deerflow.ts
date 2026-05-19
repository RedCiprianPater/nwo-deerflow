/**
 * Deer-Flow Tool Implementation for NWO Conway Agents
 * 
 * This class implements Tool #20 for the NWO Agent Runner,
 * providing integration with ByteDance's Deer-Flow super agent harness.
 */

export interface DeerFlowParams {
  prompt: string;
  mode?: 'flash' | 'standard' | 'pro' | 'ultra';
  output_format?: 'text' | 'report' | 'slides' | 'code' | 'web' | 'markdown';
  max_duration_minutes?: number;
  context?: Record<string, any>;
}

export interface DeerFlowResult {
  success: boolean;
  output: string;
  artifacts: Array<{
    type: string;
    name: string;
    url: string;
    size: number;
  }>;
  duration_seconds: number;
  token_usage?: {
    prompt_tokens: number;
    completion_tokens: number;
    total_tokens: number;
  };
  error?: string;
}

export interface TaskSubmission {
  task_id: string;
  status: string;
  thread_id: string;
  created_at: string;
  estimated_duration?: number;
}

export class DeerFlowTool {
  private apiBase: string;
  private apiKey?: string;
  private cache: KVNamespace;
  
  constructor(env: {
    DEERFLOW_API_BASE: string;
    DEERFLOW_API_KEY?: string;
    DEERFLOW_CACHE: KVNamespace;
  }) {
    this.apiBase = env.DEERFLOW_API_BASE;
    this.apiKey = env.DEERFLOW_API_KEY;
    this.cache = env.DEERFLOW_CACHE;
  }
  
  /**
   * Execute Deer-Flow tool from Conway agent
   */
  async execute(params: DeerFlowParams): Promise<DeerFlowResult> {
    const startTime = Date.now();
    
    try {
      // Check cache for identical requests
      const cacheKey = this.getCacheKey(params);
      const cached = await this.cache.get(cacheKey);
      if (cached) {
        const result = JSON.parse(cached);
        result.cached = true;
        return result;
      }
      
      // Submit task to Deer-Flow
      const submission = await this.submitTask(params);
      
      // Wait for completion
      const result = await this.waitForCompletion(
        submission.task_id,
        (params.max_duration_minutes || 60) * 60 * 1000
      );
      
      // Cache successful results
      if (result.success) {
        await this.cache.put(cacheKey, JSON.stringify(result), {
          expirationTtl: 3600 // 1 hour cache
        });
      }
      
      return result;
      
    } catch (error) {
      return {
        success: false,
        output: '',
        artifacts: [],
        duration_seconds: Math.floor((Date.now() - startTime) / 1000),
        error: error.message || 'Unknown error'
      };
    }
  }
  
  /**
   * Submit a task to Deer-Flow
   */
  async submitTask(params: DeerFlowParams): Promise<TaskSubmission> {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json'
    };
    
    if (this.apiKey) {
      headers['Authorization'] = `Bearer ${this.apiKey}`;
    }
    
    const response = await fetch(`${this.apiBase}/api/tasks`, {
      method: 'POST',
      headers,
      body: JSON.stringify({
        prompt: params.prompt,
        mode: params.mode || 'standard',
        output_format: params.output_format,
        max_duration_minutes: params.max_duration_minutes || 60,
        context: params.context
      })
    });
    
    if (!response.ok) {
      throw new Error(`Deer-Flow API error: ${response.status} ${response.statusText}`);
    }
    
    return response.json();
  }
  
  /**
   * Get task status
   */
  async getTaskStatus(taskId: string): Promise<any> {
    const headers: Record<string, string> = {};
    
    if (this.apiKey) {
      headers['Authorization'] = `Bearer ${this.apiKey}`;
    }
    
    const response = await fetch(`${this.apiBase}/api/tasks/${taskId}`, {
      headers
    });
    
    if (!response.ok) {
      throw new Error(`Failed to get task status: ${response.status}`);
    }
    
    return response.json();
  }
  
  /**
   * Wait for task completion with polling
   */
  private async waitForCompletion(
    taskId: string,
    timeoutMs: number,
    pollIntervalMs = 5000
  ): Promise<DeerFlowResult> {
    const startTime = Date.now();
    
    while (Date.now() - startTime < timeoutMs) {
      const status = await this.getTaskStatus(taskId);
      
      if (status.status === 'completed') {
        return {
          success: true,
          output: status.output || '',
          artifacts: status.artifacts || [],
          duration_seconds: status.duration_seconds || Math.floor((Date.now() - startTime) / 1000),
          token_usage: status.token_usage
        };
      }
      
      if (status.status === 'failed' || status.status === 'cancelled') {
        return {
          success: false,
          output: status.output || '',
          artifacts: status.artifacts || [],
          duration_seconds: status.duration_seconds || Math.floor((Date.now() - startTime) / 1000),
          error: status.output || `Task ${status.status}`
        };
      }
      
      // Wait before next poll
      await this.sleep(pollIntervalMs);
    }
    
    // Timeout
    return {
      success: false,
      output: '',
      artifacts: [],
      duration_seconds: Math.floor((Date.now() - startTime) / 1000),
      error: 'Timeout waiting for task completion'
    };
  }
  
  /**
   * Generate cache key from params
   */
  private getCacheKey(params: DeerFlowParams): string {
    // Simple hash for caching
    const key = JSON.stringify({
      p: params.prompt.slice(0, 100),
      m: params.mode,
      f: params.output_format
    });
    return `deerflow:${btoa(key).slice(0, 32)}`;
  }
  
  /**
   * Sleep utility
   */
  private sleep(ms: number): Promise<void> {
    return new Promise(resolve => setTimeout(resolve, ms));
  }
  
  /**
   * Get tool metadata for agent discovery
   */
  getMetadata() {
    return {
      tool_id: 20,
      tool_name: 'deer_flow',
      display_name: 'Deer-Flow Research',
      description: 'Advanced research and coding via Deer-Flow super agent harness',
      version: '0.1.0',
      modes: ['flash', 'standard', 'pro', 'ultra'],
      features: [
        'deep_research',
        'code_generation',
        'report_creation',
        'slide_generation',
        'web_development',
        'sub_agent_orchestration'
      ],
      rate_limits: {
        per_cycle: 1,
        concurrent: 2
      }
    };
  }
}
