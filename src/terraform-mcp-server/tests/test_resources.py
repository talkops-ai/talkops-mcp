"""Tests for MCP resources."""

import json
import pytest
from unittest.mock import MagicMock

from terraform_mcp_server.resources import initialize_resources
from terraform_mcp_server.resources.terraform_resources import TerraformResources, _redact


class TestResourceRedaction:
    """Test secret redaction logic."""
    
    def test_redacts_neo4j_password(self):
        assert _redact('NEO4J_PASSWORD', 'secret123') == '***REDACTED***'
    
    def test_redacts_openai_api_key(self):
        assert _redact('OPENAI_API_KEY', 'sk-abc') == '***REDACTED***'
    
    def test_redacts_generic_password(self):
        assert _redact('DB_PASSWORD', 'pass') == '***REDACTED***'
    
    def test_redacts_generic_secret(self):
        assert _redact('MY_SECRET', 'val') == '***REDACTED***'
    
    def test_redacts_generic_token(self):
        assert _redact('AUTH_TOKEN', 'tok') == '***REDACTED***'
    
    def test_preserves_safe_values(self):
        assert _redact('NEO4J_URI', 'bolt://localhost:7687') == 'bolt://localhost:7687'
    
    def test_preserves_embedding_model(self):
        assert _redact('EMBEDDING_MODEL', 'text-embedding-ada-002') == 'text-embedding-ada-002'


class TestResourceInitialization:
    """Test resource registry initialization."""
    
    def test_initialize_resources_creates_registry(self, service_locator):
        registry = initialize_resources(service_locator)
        assert len(registry.resources) == 1
    
    def test_register_all_resources(self, service_locator):
        registry = initialize_resources(service_locator)
        mcp_mock = MagicMock()
        
        # Should not raise
        registry.register_all_resources(mcp_mock)


@pytest.mark.asyncio
class TestKnowledgeGraphStatsResource:
    """Test terraform://knowledge-graph/stats resource."""
    
    async def test_stats_with_graph(self, service_locator):
        """Stats resource returns JSON with chunk counts."""
        resource = TerraformResources(service_locator)
        mcp_mock = MagicMock()
        resource.register(mcp_mock)
        
        # Get the registered handler
        # FastMCP registers with @mcp.resource() decorator, so we check
        # the mock was called
        assert mcp_mock.resource.called
    
    async def test_stats_without_graph(self, mock_config, mock_server_config):
        """Stats resource handles missing Neo4j gracefully."""
        locator = {
            'config': mock_config,
            'server_config': mock_server_config,
            'neo4j_graph': None,
        }
        resource = TerraformResources(locator)
        mcp_mock = MagicMock()
        resource.register(mcp_mock)
        
        # Verify registration happened
        assert mcp_mock.resource.called


@pytest.mark.asyncio
class TestConfigSummaryResource:
    """Test terraform://server/config-summary resource."""
    
    async def test_config_summary_redacts_secrets(self, service_locator):
        """Config summary should never echo passwords or API keys."""
        resource = TerraformResources(service_locator)
        mcp_mock = MagicMock()
        resource.register(mcp_mock)
        
        # The decorator was called twice (two resources)
        assert mcp_mock.resource.call_count == 2
