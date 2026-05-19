"""Terraform document search tool — MCP registration layer.

Wraps the existing TFSearchTool execution logic in a Traefik-style
BaseTool class with @mcp.tool() registration and pydantic.Field
parameter annotations.
"""

import json
import logging
from typing import Any, Dict, List, Optional

from pydantic import Field
from fastmcp import Context

from terraform_mcp_server.tools.base import BaseTool
from terraform_mcp_server.core.tools.tf_search_tool import (
    TFSearchTool,
    VectorSearchInput,
)

logger = logging.getLogger(__name__)


class TerraformSearchTools(BaseTool):
    """MCP tool registration for Terraform document search.
    
    Delegates execution to the existing TFSearchTool in core/tools/,
    preserving the public MCP tool name and JSON response contract.
    """
    
    def register(self, mcp_instance) -> None:
        """Register terraform_doc_search with the MCP instance."""
        # Capture self for closure
        config = self.config
        neo4j_graph = self.neo4j_graph
        
        @mcp_instance.tool()
        async def terraform_doc_search(
            query: str = Field(
                description="Search query to find similar Terraform documentation chunks",
            ),
            top_k: int = Field(
                default=5,
                ge=1,
                le=50,
                description="Number of top results to return",
            ),
            similarity_threshold: float = Field(
                default=0.7,
                ge=0.0,
                le=1.0,
                description="Minimum similarity score threshold (0.0 to 1.0)",
            ),
            node_types: Optional[List[str]] = Field(
                default=None,
                description=(
                    "Node types to search: 'resource', 'data_source', "
                    "'best_practice'. If None, searches all types."
                ),
            ),
            context: Context = None,
        ) -> str:
            """Perform semantic vector similarity search over Terraform document chunks.
            
            Uses vector embeddings stored in Neo4j with LangChain integration
            to find the most relevant documentation chunks for a given query.
            
            Results include content, similarity scores, node types, and metadata.
            Supports filtering by node type (resource, data_source, best_practice)
            and distributes results evenly across searched types.
            """
            dependencies = {'neo4j_graph': neo4j_graph} if neo4j_graph else {}
            search_tool = TFSearchTool(dependencies)
            
            return await search_tool.execute(
                query=query,
                top_k=top_k,
                similarity_threshold=similarity_threshold,
                node_types=node_types,
                context=context,
            )
