"""Tests for ServerBootstrap initialization."""

import pytest
from unittest.mock import patch, MagicMock
from fastmcp import FastMCP


class TestServerBootstrap:
    """Test ServerBootstrap.initialize() with mocked dependencies."""
    
    @patch('terraform_mcp_server.server.bootstrap.initialize_resources')
    @patch('terraform_mcp_server.server.bootstrap.initialize_tools')
    @patch('terraform_mcp_server.server.bootstrap.Neo4jGraph', create=True)
    @patch('terraform_mcp_server.server.bootstrap.Config')
    @patch('terraform_mcp_server.server.bootstrap.MCPConfig')
    def test_initialize_returns_mcp_and_config(
        self, mock_mcp_config, mock_config_class,
        mock_neo4j_graph_class, mock_init_tools, mock_init_resources,
        mock_config, mock_server_config
    ):
        """Bootstrap returns (mcp, server_config) tuple."""
        # Setup mocks
        mock_config_class.return_value = mock_config
        mock_mcp_config.from_env.return_value = mock_server_config
        
        mock_neo4j = MagicMock()
        mock_neo4j_graph_class.return_value = mock_neo4j
        
        mock_tool_registry = MagicMock()
        mock_init_tools.return_value = mock_tool_registry
        
        mock_resource_registry = MagicMock()
        mock_init_resources.return_value = mock_resource_registry
        
        from terraform_mcp_server.server.bootstrap import ServerBootstrap
        mcp, config = ServerBootstrap.initialize()
        
        # Verify returns
        assert isinstance(mcp, FastMCP)
        assert config is mock_server_config
        
        # Verify registration was called
        mock_tool_registry.register_all_tools.assert_called_once()
        mock_resource_registry.register_all_resources.assert_called_once()
    
    @patch('terraform_mcp_server.server.bootstrap.initialize_resources')
    @patch('terraform_mcp_server.server.bootstrap.initialize_tools')
    @patch('terraform_mcp_server.server.bootstrap.Config')
    @patch('terraform_mcp_server.server.bootstrap.MCPConfig')
    def test_initialize_handles_neo4j_failure(
        self, mock_mcp_config, mock_config_class,
        mock_init_tools, mock_init_resources,
        mock_config, mock_server_config
    ):
        """Bootstrap continues even when Neo4j connection fails."""
        mock_config_class.return_value = mock_config
        mock_mcp_config.from_env.return_value = mock_server_config
        
        mock_tool_registry = MagicMock()
        mock_init_tools.return_value = mock_tool_registry
        
        mock_resource_registry = MagicMock()
        mock_init_resources.return_value = mock_resource_registry
        
        # Patch the Neo4jGraph import to raise
        with patch.dict('sys.modules', {'langchain_neo4j': MagicMock()}):
            with patch(
                'terraform_mcp_server.server.bootstrap.Neo4jGraph',
                side_effect=Exception("Connection refused"),
                create=True,
            ):
                from terraform_mcp_server.server.bootstrap import ServerBootstrap
                mcp, config = ServerBootstrap.initialize()
                
                # Should still succeed with None neo4j_graph
                assert isinstance(mcp, FastMCP)
