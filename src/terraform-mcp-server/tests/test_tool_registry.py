"""Tests for ToolRegistry and tool initialization."""

import pytest
from unittest.mock import MagicMock

from terraform_mcp_server.tools import initialize_tools
from terraform_mcp_server.tools.registry import ToolRegistry
from terraform_mcp_server.tools.base import BaseTool


class TestToolRegistry:
    """Test ToolRegistry registration and lifecycle."""
    
    def test_registry_creation(self, service_locator):
        """Registry initializes with empty tools list."""
        registry = ToolRegistry(service_locator)
        assert registry.get_tools_count() == 0
        assert registry.get_tools() == []
    
    def test_register_tool(self, service_locator):
        """Single tool registration increments count."""
        registry = ToolRegistry(service_locator)
        
        # Create a concrete tool (minimal stub)
        class StubTool(BaseTool):
            def register(self, mcp_instance):
                pass
        
        tool = StubTool(service_locator)
        registry.register_tool(tool)
        assert registry.get_tools_count() == 1
    
    def test_initialize_tools_registers_three_categories(self, service_locator):
        """initialize_tools creates exactly 3 tool categories."""
        registry = initialize_tools(service_locator)
        
        assert isinstance(registry, ToolRegistry)
        assert registry.get_tools_count() == 3
    
    def test_register_all_tools_calls_register(self, service_locator):
        """register_all_tools calls register() on each tool."""
        registry = initialize_tools(service_locator)
        mcp_mock = MagicMock()
        
        # This should not raise — tools register their handlers
        registry.register_all_tools(mcp_mock)
    
    def test_get_tools_returns_copy(self, service_locator):
        """get_tools returns a copy, not the internal list."""
        registry = initialize_tools(service_locator)
        tools = registry.get_tools()
        tools.clear()  # Modify the copy
        assert registry.get_tools_count() == 3  # Internal list unchanged


class TestBaseTool:
    """Test BaseTool dependency injection."""
    
    def test_config_required(self):
        """BaseTool raises ValueError if config is missing."""
        class StubTool(BaseTool):
            def register(self, mcp_instance):
                pass
        
        with pytest.raises(ValueError, match="config"):
            StubTool({})
    
    def test_config_injected(self, service_locator):
        """BaseTool extracts config from service_locator."""
        class StubTool(BaseTool):
            def register(self, mcp_instance):
                pass
        
        tool = StubTool(service_locator)
        assert tool.config is service_locator['config']
        assert tool.server_config is service_locator['server_config']
        assert tool.neo4j_graph is service_locator['neo4j_graph']
