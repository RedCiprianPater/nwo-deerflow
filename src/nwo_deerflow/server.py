"""FastAPI server for NWO Deer-Flow integration."""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from nwo_deerflow.client import TaskRequest, TaskResult

app = FastAPI(
    title="NWO Deer-Flow API",
    description="Tool #20 for NWO Conway Agents - Deer-Flow Integration",
    version="0.1.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory task storage (replace with Redis/DB in production)
tasks: dict[str, dict[str, Any]] = {}


class SubmitTaskRequest(BaseModel):
    """Request model for task submission."""
    prompt: str = Field(..., description="Task prompt/instruction")
    mode: str = Field(default="standard", description="Execution mode")
    thread_id: Optional[str] = Field(default=None, description="Thread ID")
    context: Optional[dict[str, Any]] = Field(default=None, description="Context")
    max_duration_minutes: int = Field(default=60, description="Max duration")
    output_format: Optional[str] = Field(default=None, description="Output format")


class TaskStatusResponse(BaseModel):
    """Response model for task status."""
    task_id: str
    status: str
    thread_id: str
    created_at: str
    updated_at: Optional[str] = None
    output: Optional[str] = None
    artifacts: list[dict[str, Any]] = Field(default_factory=list)
    duration_seconds: int = 0


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "version": "0.1.0",
        "service": "nwo-deerflow",
        "timestamp": datetime.utcnow().isoformat()
    }


@app.post("/api/tasks")
async def submit_task(request: SubmitTaskRequest):
    """Submit a new task."""
    task_id = str(uuid.uuid4())
    thread_id = request.thread_id or str(uuid.uuid4())
    
    task = {
        "task_id": task_id,
        "status": "pending",
        "thread_id": thread_id,
        "prompt": request.prompt,
        "mode": request.mode,
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": None,
        "output": None,
        "artifacts": [],
        "duration_seconds": 0
    }
    
    tasks[task_id] = task
    
    # Start background processing
    asyncio.create_task(process_task(task_id, request))
    
    return {
        "task_id": task_id,
        "status": "pending",
        "thread_id": thread_id,
        "created_at": task["created_at"],
        "estimated_duration": estimate_duration(request.mode)
    }


@app.get("/api/tasks/{task_id}")
async def get_task(task_id: str):
    """Get task status and results."""
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    
    task = tasks[task_id]
    return {
        "task_id": task["task_id"],
        "status": task["status"],
        "thread_id": task["thread_id"],
        "created_at": task["created_at"],
        "updated_at": task["updated_at"],
        "output": task["output"] or "",
        "artifacts": task["artifacts"],
        "duration_seconds": task["duration_seconds"]
    }


@app.get("/api/tasks")
async def list_tasks(
    status: Optional[str] = None,
    limit: int = 10,
    offset: int = 0
):
    """List tasks with optional filtering."""
    task_list = list(tasks.values())
    
    if status:
        task_list = [t for t in task_list if t["status"] == status]
    
    task_list = task_list[offset:offset + limit]
    
    return {
        "tasks": task_list,
        "total": len(tasks),
        "limit": limit,
        "offset": offset
    }


@app.post("/api/tasks/{task_id}/cancel")
async def cancel_task(task_id: str):
    """Cancel a running task."""
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    
    task = tasks[task_id]
    
    if task["status"] in ("completed", "failed", "cancelled"):
        raise HTTPException(status_code=400, detail="Task already finished")
    
    task["status"] = "cancelled"
    task["updated_at"] = datetime.utcnow().isoformat()
    
    return {"task_id": task_id, "status": "cancelled"}


@app.get("/api/tasks/{task_id}/stream")
async def stream_task(task_id: str):
    """Stream task progress updates."""
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    
    async def event_generator():
        task = tasks[task_id]
        last_status = None
        
        while True:
            if task["status"] != last_status:
                last_status = task["status"]
                yield f"data: {json.dumps({'status': task['status'], 'output': task.get('output', '')})}\n\n"
            
            if task["status"] in ("completed", "failed", "cancelled"):
                break
            
            await asyncio.sleep(1)
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream"
    )


@app.get("/api/models")
async def list_models():
    """List available LLM models."""
    return {
        "models": [
            {
                "name": "gpt-4o",
                "display_name": "GPT-4o",
                "provider": "openai"
            },
            {
                "name": "claude-sonnet-4",
                "display_name": "Claude Sonnet 4",
                "provider": "anthropic"
            },
            {
                "name": "kimi-k2.5",
                "display_name": "Kimi K2.5",
                "provider": "moonshot"
            }
        ]
    }


@app.get("/api/tool/20/schema")
async def get_tool_schema():
    """Get JSON schema for Conway Tool #20."""
    return {
        "tool_id": 20,
        "tool_name": "deer_flow",
        "tool_description": "Advanced research and coding via Deer-Flow super agent harness",
        "parameters": {
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
    }


@app.post("/api/tool/20/execute")
async def execute_tool(request: Request):
    """Execute Tool #20 (Conway integration endpoint)."""
    params = await request.json()
    
    # Create task from tool parameters
    task_request = SubmitTaskRequest(
        prompt=params.get("prompt", ""),
        mode=params.get("mode", "standard"),
        output_format=params.get("output_format"),
        max_duration_minutes=params.get("max_duration_minutes", 60)
    )
    
    # Submit and wait
    result = await submit_task(task_request)
    task_id = result["task_id"]
    
    # Wait for completion (with timeout)
    max_wait = task_request.max_duration_minutes * 60
    waited = 0
    
    while waited < max_wait:
        task = tasks.get(task_id)
        if task and task["status"] in ("completed", "failed", "cancelled"):
            return {
                "success": task["status"] == "completed",
                "output": task.get("output", ""),
                "artifacts": task.get("artifacts", []),
                "duration_seconds": task.get("duration_seconds", 0),
                "error": None if task["status"] == "completed" else task.get("output", "Unknown error")
            }
        
        await asyncio.sleep(5)
        waited += 5
    
    return {
        "success": False,
        "output": "",
        "artifacts": [],
        "duration_seconds": waited,
        "error": "Timeout waiting for task completion"
    }


async def process_task(task_id: str, request: SubmitTaskRequest):
    """Process a task in the background."""
    import json
    import time
    
    task = tasks[task_id]
    start_time = time.time()
    
    try:
        task["status"] = "running"
        task["updated_at"] = datetime.utcnow().isoformat()
        
        # Simulate Deer-Flow processing
        # In production, this would call the actual Deer-Flow harness
        duration = estimate_duration(request.mode)
        await asyncio.sleep(min(duration, 10))  # Cap at 10s for demo
        
        # Generate mock output based on mode
        task["output"] = generate_mock_output(request)
        task["artifacts"] = generate_mock_artifacts(request)
        task["status"] = "completed"
        task["duration_seconds"] = int(time.time() - start_time)
        task["updated_at"] = datetime.utcnow().isoformat()
        
    except Exception as e:
        task["status"] = "failed"
        task["output"] = str(e)
        task["duration_seconds"] = int(time.time() - start_time)
        task["updated_at"] = datetime.utcnow().isoformat()


def estimate_duration(mode: str) -> int:
    """Estimate task duration based on mode."""
    durations = {
        "flash": 60,
        "standard": 300,
        "pro": 900,
        "ultra": 1800
    }
    return durations.get(mode, 300)


def generate_mock_output(request: SubmitTaskRequest) -> str:
    """Generate mock output for demo purposes."""
    return f"""# Research Results

**Task:** {request.prompt}
**Mode:** {request.mode}
**Completed:** {datetime.utcnow().isoformat()}

## Summary

This is a simulated output from the NWO Deer-Flow integration (Tool #20).
In production, this would contain actual research results, code, or generated content
from the Deer-Flow super agent harness.

## Key Findings

1. Finding one related to the query
2. Finding two with supporting evidence
3. Finding three with actionable insights

## Artifacts Generated

- {len(generate_mock_artifacts(request))} files/resources created
- Available in the artifacts array

---
*Generated by NWO Deer-Flow (Tool #20)*
"""


def generate_mock_artifacts(request: SubmitTaskRequest) -> list[dict[str, Any]]:
    """Generate mock artifacts for demo purposes."""
    return [
        {
            "type": "document",
            "name": "research_summary.md",
            "url": f"/api/tasks/{request.prompt[:8]}/artifacts/summary.md",
            "size": 2048
        }
    ]
