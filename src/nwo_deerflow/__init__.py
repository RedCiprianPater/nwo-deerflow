"""NWO Deer-Flow Integration - Tool #20 for NWO Conway Agents.

This package provides integration with ByteDance's Deer-Flow super agent harness,
enabling NWO Conway agents to perform advanced research, code generation, and
sub-agent orchestration.

Example:
    >>> from nwo_deerflow import DeerFlowClient
    >>> client = DeerFlowClient()
    >>> result = client.submit_task(
    ...     prompt="Research quantum computing",
    ...     mode="pro"
    ... )
    >>> print(result.task_id)
"""

__version__ = "0.1.0"
__author__ = "NWO Robotics"
__email__ = "ciprian.pater@publicae.org"

from nwo_deerflow.client import (
    ConwayToolAdapter,
    DeerFlowClient,
    TaskRequest,
    TaskResponse,
    TaskResult,
)

__all__ = [
    "DeerFlowClient",
    "ConwayToolAdapter",
    "TaskRequest",
    "TaskResponse",
    "TaskResult",
]
