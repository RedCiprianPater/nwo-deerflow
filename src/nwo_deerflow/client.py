"""NWO Deer-Flow Client - Python SDK for Conway Agent Integration."""

from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncIterator, Optional
from urllib.parse import urljoin

import httpx
from pydantic import BaseModel, Field
from tenacity import retry, stop_after_attempt, wait_exponential


class TaskRequest(BaseModel):
    """Request model for submitting a Deer-Flow task."""
    
    prompt: str = Field(..., description="The task prompt/instruction")
    mode: str = Field(default="standard", description="Execution mode: flash, standard, pro, ultra")
    thread_id: Optional[str] = Field(default=None, description="Thread ID for conversation continuity")
    context: Optional[dict[str, Any]] = Field(default=None, description="Additional context")
    max_duration_minutes: int = Field(default=60, description="Maximum task duration")
    output_format: Optional[str] = Field(default=None, description="Desired output format")


class TaskResponse(BaseModel):
    """Response model for task submission."""
    
    task_id: str
    status: str
    thread_id: str
    created_at: str
    estimated_duration: Optional[int] = None


class TaskResult(BaseModel):
    """Result model for completed task."""
    
    task_id: str
    status: str  # completed, failed, cancelled
    output: str
    artifacts: list[dict[str, Any]] = Field(default_factory=list)
    duration_seconds: int
    token_usage: Optional[dict[str, int]] = None


class DeerFlowClient:
    """Client for interacting with Deer-Flow service.
    
    This client provides both synchronous and asynchronous interfaces
    for submitting tasks and retrieving results from Deer-Flow.
    
    Example:
        >>> client = DeerFlowClient(api_base="http://localhost:8001")
        >>> result = client.submit_task(
        ...     prompt="Research quantum computing",
        ...     mode="pro"
        ... )
        >>> print(result.task_id)
    """
    
    def __init__(
        self,
        api_base: str = "http://localhost:8001",
        api_key: Optional[str] = None,
        timeout: float = 30.0
    ):
        """Initialize the Deer-Flow client.
        
        Args:
            api_base: Base URL of the Deer-Flow API
            api_key: Optional API key for authentication
            timeout: Request timeout in seconds
        """
        self.api_base = api_base.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        
        self._client = httpx.Client(
            base_url=self.api_base,
            headers=headers,
            timeout=timeout
        )
        self._async_client: Optional[httpx.AsyncClient] = None
    
    def _get_async_client(self) -> httpx.AsyncClient:
        """Get or create async HTTP client."""
        if self._async_client is None:
            headers = {"Content-Type": "application/json"}
            if self.api_key:
                headers["Authorization"] = f"Bearer {api_key}"
            
            self._async_client = httpx.AsyncClient(
                base_url=self.api_base,
                headers=headers,
                timeout=self.timeout
            )
        return self._async_client
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10)
    )
    def submit_task(self, request: TaskRequest) -> TaskResponse:
        """Submit a new task to Deer-Flow.
        
        Args:
            request: Task request configuration
            
        Returns:
            TaskResponse with task ID and status
            
        Raises:
            httpx.HTTPError: If the API request fails
        """
        response = self._client.post(
            "/api/tasks",
            json=request.model_dump(exclude_none=True)
        )
        response.raise_for_status()
        return TaskResponse(**response.json())
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10)
    )
    def get_task(self, task_id: str) -> TaskResult:
        """Get task status and results.
        
        Args:
            task_id: The task ID to query
            
        Returns:
            TaskResult with current status and output
        """
        response = self._client.get(f"/api/tasks/{task_id}")
        response.raise_for_status()
        return TaskResult(**response.json())
    
    def submit_and_wait(
        self,
        prompt: str,
        mode: str = "standard",
        thread_id: Optional[str] = None,
        timeout: float = 3600.0,
        poll_interval: float = 5.0
    ) -> TaskResult:
        """Submit a task and wait for completion.
        
        Args:
            prompt: Task prompt
            mode: Execution mode
            thread_id: Optional thread ID
            timeout: Maximum wait time in seconds
            poll_interval: Seconds between status checks
            
        Returns:
            TaskResult when complete
            
        Raises:
            TimeoutError: If task doesn't complete within timeout
        """
        request = TaskRequest(
            prompt=prompt,
            mode=mode,
            thread_id=thread_id
        )
        
        response = self.submit_task(request)
        task_id = response.task_id
        
        start_time = asyncio.get_event_loop().time() if asyncio.get_event_loop().is_running() else 0
        import time
        start = time.time()
        
        while time.time() - start < timeout:
            result = self.get_task(task_id)
            
            if result.status in ("completed", "failed", "cancelled"):
                return result
            
            time.sleep(poll_interval)
        
        raise TimeoutError(f"Task {task_id} did not complete within {timeout}s")
    
    async def submit_task_async(self, request: TaskRequest) -> TaskResponse:
        """Async version of submit_task."""
        client = self._get_async_client()
        response = await client.post(
            "/api/tasks",
            json=request.model_dump(exclude_none=True)
        )
        response.raise_for_status()
        return TaskResponse(**response.json())
    
    async def get_task_async(self, task_id: str) -> TaskResult:
        """Async version of get_task."""
        client = self._get_async_client()
        response = await client.get(f"/api/tasks/{task_id}")
        response.raise_for_status()
        return TaskResult(**response.json())
    
    async def submit_and_wait_async(
        self,
        prompt: str,
        mode: str = "standard",
        thread_id: Optional[str] = None,
        timeout: float = 3600.0,
        poll_interval: float = 5.0
    ) -> TaskResult:
        """Async version of submit_and_wait."""
        request = TaskRequest(
            prompt=prompt,
            mode=mode,
            thread_id=thread_id
        )
        
        response = await self.submit_task_async(request)
        task_id = response.task_id
        
        import asyncio
        start = asyncio.get_event_loop().time()
        
        while asyncio.get_event_loop().time() - start < timeout:
            result = await self.get_task_async(task_id)
            
            if result.status in ("completed", "failed", "cancelled"):
                return result
            
            await asyncio.sleep(poll_interval)
        
        raise TimeoutError(f"Task {task_id} did not complete within {timeout}s")
    
    async def stream_task(
        self,
        task_id: str
    ) -> AsyncIterator[dict[str, Any]]:
        """Stream task progress updates.
        
        Args:
            task_id: Task to stream
            
        Yields:
            Progress update dictionaries
        """
        client = self._get_async_client()
        async with client.stream("GET", f"/api/tasks/{task_id}/stream") as response:
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    data = json.loads(line[6:])
                    yield data
    
    def health_check(self) -> dict[str, Any]:
        """Check Deer-Flow service health.
        
        Returns:
            Health status dictionary
        """
        response = self._client.get("/health")
        response.raise_for_status()
        return response.json()
    
    def list_models(self) -> list[dict[str, Any]]:
        """List available LLM models.
        
        Returns:
            List of model configurations
        """
        response = self._client.get("/api/models")
        response.raise_for_status()
        return response.json().get("models", [])
    
    def close(self) -> None:
        """Close the HTTP client."""
        self._client.close()
        if self._async_client:
            asyncio.get_event_loop().run_until_complete(self._async_client.aclose())
    
    def __enter__(self) -> DeerFlowClient:
        return self
    
    def __exit__(self, *args: Any) -> None:
        self.close()


class ConwayToolAdapter:
    """Adapter for integrating Deer-Flow as Tool #20 in NWO Conway agents.
    
    This adapter conforms to the NWO Agent Runner tool interface,
    allowing Conway agents to invoke Deer-Flow capabilities.
    """
    
    TOOL_ID = 20
    TOOL_NAME = "deer_flow"
    TOOL_DESCRIPTION = "Advanced research and coding via Deer-Flow super agent harness"
    
    def __init__(self, deerflow_client: DeerFlowClient):
        """Initialize with Deer-Flow client."""
        self.client = deerflow_client
    
    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        """Execute Deer-Flow tool from Conway agent.
        
        Args:
            params: Tool parameters from agent
                - prompt: Task description
                - mode: Execution mode (flash/standard/pro/ultra)
                - output_format: Desired output format
                - max_duration_minutes: Timeout
                
        Returns:
            Tool execution result for agent
        """
        prompt = params.get("prompt", "")
        mode = params.get("mode", "standard")
        output_format = params.get("output_format")
        max_duration = params.get("max_duration_minutes", 60)
        
        try:
            request = TaskRequest(
                prompt=prompt,
                mode=mode,
                max_duration_minutes=max_duration,
                output_format=output_format
            )
            
            result = self.client.submit_and_wait(
                prompt=prompt,
                mode=mode,
                timeout=max_duration * 60
            )
            
            return {
                "success": result.status == "completed",
                "output": result.output,
                "artifacts": result.artifacts,
                "duration_seconds": result.duration_seconds,
                "token_usage": result.token_usage,
                "error": None if result.status == "completed" else result.output
            }
            
        except Exception as e:
            return {
                "success": False,
                "output": "",
                "artifacts": [],
                "duration_seconds": 0,
                "error": str(e)
            }
    
    def get_schema(self) -> dict[str, Any]:
        """Get JSON schema for tool parameters."""
        return {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "The research or coding task to perform"
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
                    "default": 60,
                    "description": "Maximum time to spend on task"
                }
            },
            "required": ["prompt"]
        }
