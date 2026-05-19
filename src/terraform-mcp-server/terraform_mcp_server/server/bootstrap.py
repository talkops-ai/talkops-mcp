"""Server initialization and bootstrap for Terraform MCP Server."""

import logging

from terraform_mcp_server.config import Config
from terraform_mcp_server.server_config import MCPConfig, ServerConfig
from terraform_mcp_server.server.core import create_mcp_server
from terraform_mcp_server.tools import initialize_tools
from terraform_mcp_server.resources import initialize_resources

logger = logging.getLogger(__name__)


class ServerBootstrap:
    """Bootstrap the Terraform MCP server with all components."""
    
    @staticmethod
    def initialize() -> tuple:
        """Initialize server and all components.
        
        Wiring sequence:
        1. Load domain config (Neo4j, embeddings, etc.)
        2. Load MCP server config (transport, host, port, etc.)
        3. Create FastMCP instance with middleware
        4. Create Neo4j graph connection
        5. Build service locator
        6. Initialize and register tools
        7. Initialize and register resources
        
        Returns:
            Tuple of (mcp_instance, server_config)
        """
        # 1. Load domain configuration
        config = Config()
        logger.info("Domain configuration loaded")
        
        # 2. Load MCP server configuration
        server_config = MCPConfig.from_env()
        logger.info(
            "MCP server config: transport=%s, host=%s, port=%d",
            server_config.transport,
            server_config.host,
            server_config.port,
        )
        
        # 3. Create FastMCP instance
        mcp = create_mcp_server(server_config)
        logger.info("FastMCP instance created with middleware")
        
        # 4. Create Neo4j connection (lazy — tools handle their own init)
        # We pass the config so tools can create connections as needed;
        # this avoids hard failure at startup when Neo4j isn't available.
        neo4j_graph = None
        try:
            from langchain_neo4j import Neo4jGraph
            neo4j_graph = Neo4jGraph(
                url=config.NEO4J_URI,
                username=config.NEO4J_USERNAME,
                password=config.NEO4J_PASSWORD,
            )
            logger.info("Neo4j connection established")
        except Exception as e:
            logger.warning(
                "Neo4j connection deferred (tools will retry): %s", e
            )
        
        # 5. Build service locator (dependency injection)
        service_locator = {
            'config': config,
            'server_config': server_config,
            'neo4j_graph': neo4j_graph,
        }
        
        # 6. Initialize and register tools
        tool_registry = initialize_tools(service_locator)
        tool_registry.register_all_tools(mcp)
        logger.info(
            "Registered %d tool categories", tool_registry.get_tools_count()
        )
        
        # 7. Initialize and register resources
        resource_registry = initialize_resources(service_locator)
        resource_registry.register_all_resources(mcp)
        logger.info("Resources registered")
        
        return mcp, server_config
