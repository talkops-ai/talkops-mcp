"""Tools module for Terraform MCP Server.

Tool Categories:
1. Search: Semantic vector similarity search over Terraform documentation
2. Ingestion: Document ingestion into Neo4j knowledge graph
3. Execution: Secure Terraform command execution
"""

from typing import Dict, Any, List

from terraform_mcp_server.tools.registry import ToolRegistry
from terraform_mcp_server.tools.base import BaseTool
from terraform_mcp_server.tools.terraform.search_tools import TerraformSearchTools
from terraform_mcp_server.tools.terraform.ingestion_tools import TerraformIngestionTools
from terraform_mcp_server.tools.terraform.execution_tools import TerraformExecutionTools

__all__ = [
    'initialize_tools',
    'ToolRegistry',
    'BaseTool',
    'TerraformSearchTools',
    'TerraformIngestionTools',
    'TerraformExecutionTools',
]


def initialize_tools(service_locator: Dict[str, Any]) -> ToolRegistry:
    """Initialize all tools and register them with the registry.
    
    Args:
        service_locator: Dependency injection container
    
    Returns:
        Configured ToolRegistry ready for register_all_tools()
    """
    registry = ToolRegistry(service_locator)
    
    # Initialize tool categories
    tools: List[BaseTool] = [
        TerraformSearchTools(service_locator),
        TerraformIngestionTools(service_locator),
        TerraformExecutionTools(service_locator),
    ]
    
    for tool in tools:
        registry.register_tool(tool)
    
    return registry
