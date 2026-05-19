"""Command-line interface for NWO Deer-Flow."""

from __future__ import annotations

import json
import os
import sys
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from nwo_deerflow.client import ConwayToolAdapter, DeerFlowClient, TaskRequest

app = typer.Typer(
    name="nwo-deerflow",
    help="NWO Deer-Flow Integration - Tool #20 for NWO Conway Agents",
    rich_markup_mode="rich"
)
console = Console()


def get_client() -> DeerFlowClient:
    """Create Deer-Flow client from environment."""
    api_base = os.getenv("DEERFLOW_API_BASE", "http://localhost:8001")
    api_key = os.getenv("DEERFLOW_API_KEY")
    return DeerFlowClient(api_base=api_base, api_key=api_key)


@app.command()
def serve(
    host: str = typer.Option("0.0.0.0", help="Host to bind to"),
    port: int = typer.Option(8001, help="Port to listen on"),
    reload: bool = typer.Option(False, help="Enable auto-reload"),
):
    """Start the Deer-Flow API server."""
    try:
        import uvicorn
        from nwo_deerflow.server import app as fastapi_app
        
        console.print(Panel.fit(
            f"[green]Starting NWO Deer-Flow Server[/green]\n"
            f"Host: {host}\nPort: {port}",
            title="🚀 Server"
        ))
        
        uvicorn.run(
            "nwo_deerflow.server:app",
            host=host,
            port=port,
            reload=reload
        )
    except ImportError:
        console.print("[red]Server dependencies not installed.[/red]")
        console.print("Run: pip install nwo-deerflow[server]")
        raise typer.Exit(1)


@app.command()
def submit(
    prompt: str = typer.Argument(..., help="Task prompt/instruction"),
    mode: str = typer.Option("standard", help="Execution mode: flash, standard, pro, ultra"),
    thread: Optional[str] = typer.Option(None, help="Thread ID for continuity"),
    wait: bool = typer.Option(False, help="Wait for completion"),
    timeout: int = typer.Option(3600, help="Timeout in seconds when waiting"),
):
    """Submit a task to Deer-Flow."""
    client = get_client()
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console
    ) as progress:
        task = progress.add_task("Submitting task...", total=None)
        
        request = TaskRequest(
            prompt=prompt,
            mode=mode,
            thread_id=thread
        )
        
        response = client.submit_task(request)
        progress.update(task, completed=True)
    
    console.print(Panel.fit(
        f"[green]Task Submitted[/green]\n"
        f"ID: {response.task_id}\n"
        f"Status: {response.status}\n"
        f"Thread: {response.thread_id}",
        title="✅ Submitted"
    ))
    
    if wait:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            task = progress.add_task("Waiting for completion...", total=None)
            
            try:
                result = client.submit_and_wait(
                    prompt=prompt,
                    mode=mode,
                    thread_id=thread,
                    timeout=timeout
                )
                progress.update(task, completed=True)
                
                console.print(Panel.fit(
                    f"[green]Task Completed[/green]\n"
                    f"Status: {result.status}\n"
                    f"Duration: {result.duration_seconds}s\n"
                    f"Output:\n{result.output[:500]}...",
                    title="✅ Complete"
                ))
                
            except TimeoutError:
                console.print("[red]Timeout waiting for task completion[/red]")
                raise typer.Exit(1)


@app.command()
def status(task_id: str = typer.Argument(..., help="Task ID to check")):
    """Check status of a task."""
    client = get_client()
    
    result = client.get_task(task_id)
    
    status_color = {
        "completed": "green",
        "failed": "red",
        "cancelled": "yellow",
        "running": "blue"
    }.get(result.status, "white")
    
    console.print(Panel.fit(
        f"Task ID: {result.task_id}\n"
        f"Status: [{status_color}]{result.status}[/{status_color}]\n"
        f"Duration: {result.duration_seconds}s\n"
        f"Artifacts: {len(result.artifacts)}\n"
        f"Output:\n{result.output[:1000]}",
        title=f"📋 Task Status"
    ))


@app.command()
def health():
    """Check Deer-Flow service health."""
    client = get_client()
    
    try:
        health = client.health_check()
        
        console.print(Panel.fit(
            f"[green]✓ Service Healthy[/green]\n"
            f"Status: {health.get('status', 'unknown')}\n"
            f"Version: {health.get('version', 'unknown')}",
            title="🏥 Health Check"
        ))
    except Exception as e:
        console.print(f"[red]✗ Health check failed: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def models():
    """List available LLM models."""
    client = get_client()
    
    models = client.list_models()
    
    table = Table(title="Available Models")
    table.add_column("Name", style="cyan")
    table.add_column("Display Name", style="magenta")
    table.add_column("Provider", style="green")
    
    for model in models:
        table.add_row(
            model.get("name", "N/A"),
            model.get("display_name", "N/A"),
            model.get("provider", "N/A")
        )
    
    console.print(table)


@app.command()
def conway_tool(
    prompt: str = typer.Argument(..., help="Task prompt"),
    mode: str = typer.Option("standard", help="Execution mode"),
    output_format: Optional[str] = typer.Option(None, help="Output format"),
):
    """Execute as Conway Tool #20 (for testing)."""
    client = get_client()
    adapter = ConwayToolAdapter(client)
    
    params = {
        "prompt": prompt,
        "mode": mode,
        "output_format": output_format
    }
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console
    ) as progress:
        task = progress.add_task("Executing Conway tool...", total=None)
        result = adapter.execute(params)
        progress.update(task, completed=True)
    
    if result["success"]:
        console.print(Panel.fit(
            f"[green]Tool Execution Successful[/green]\n"
            f"Duration: {result['duration_seconds']}s\n"
            f"Output:\n{result['output'][:1000]}...",
            title="✅ Conway Tool #20"
        ))
    else:
        console.print(Panel.fit(
            f"[red]Tool Execution Failed[/red]\n"
            f"Error: {result['error']}",
            title="❌ Failed"
        ))


@app.command()
def config():
    """Show current configuration."""
    config_table = Table(title="Configuration")
    config_table.add_column("Variable", style="cyan")
    config_table.add_column("Value", style="magenta")
    
    config_table.add_row("DEERFLOW_API_BASE", os.getenv("DEERFLOW_API_BASE", "http://localhost:8001"))
    config_table.add_row("DEERFLOW_API_KEY", "***" if os.getenv("DEERFLOW_API_KEY") else "Not set")
    config_table.add_row("OPENAI_API_KEY", "***" if os.getenv("OPENAI_API_KEY") else "Not set")
    config_table.add_row("ANTHROPIC_API_KEY", "***" if os.getenv("ANTHROPIC_API_KEY") else "Not set")
    config_table.add_row("MOONSHOT_API_KEY", "***" if os.getenv("MOONSHOT_API_KEY") else "Not set")
    
    console.print(config_table)


def main():
    """Entry point for CLI."""
    app()


if __name__ == "__main__":
    main()
