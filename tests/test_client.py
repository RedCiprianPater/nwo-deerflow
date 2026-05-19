"""Tests for NWO Deer-Flow client."""

import pytest
from nwo_deerflow.client import DeerFlowClient, TaskRequest, ConwayToolAdapter


class TestDeerFlowClient:
    """Test suite for DeerFlowClient."""
    
    def test_client_initialization(self):
        """Test client can be initialized."""
        client = DeerFlowClient(api_base="http://localhost:8001")
        assert client.api_base == "http://localhost:8001"
        assert client.api_key is None
    
    def test_client_with_api_key(self):
        """Test client initialization with API key."""
        client = DeerFlowClient(
            api_base="http://localhost:8001",
            api_key="test-key"
        )
        assert client.api_key == "test-key"
    
    def test_task_request_creation(self):
        """Test TaskRequest model."""
        request = TaskRequest(
            prompt="Test prompt",
            mode="standard",
            max_duration_minutes=30
        )
        assert request.prompt == "Test prompt"
        assert request.mode == "standard"
        assert request.max_duration_minutes == 30


class TestConwayToolAdapter:
    """Test suite for ConwayToolAdapter."""
    
    def test_adapter_initialization(self):
        """Test adapter can be initialized."""
        client = DeerFlowClient()
        adapter = ConwayToolAdapter(client)
        assert adapter.client == client
        assert adapter.TOOL_ID == 20
    
    def test_get_schema(self):
        """Test schema generation."""
        client = DeerFlowClient()
        adapter = ConwayToolAdapter(client)
        schema = adapter.get_schema()
        
        assert schema["type"] == "object"
        assert "properties" in schema
        assert "prompt" in schema["properties"]
        assert "mode" in schema["properties"]


class TestIntegration:
    """Integration tests (requires running server)."""
    
    @pytest.mark.skip(reason="Requires running Deer-Flow server")
    def test_health_check(self):
        """Test health check endpoint."""
        client = DeerFlowClient()
        health = client.health_check()
        assert "status" in health
    
    @pytest.mark.skip(reason="Requires running Deer-Flow server")
    def test_list_models(self):
        """Test list models endpoint."""
        client = DeerFlowClient()
        models = client.list_models()
        assert isinstance(models, list)
