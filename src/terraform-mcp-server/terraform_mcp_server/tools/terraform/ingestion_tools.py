"""Terraform document ingestion tool — MCP registration layer.

Wraps the existing TFIngestionTool execution logic in a Traefik-style
BaseTool class with @mcp.tool() registration and pydantic.Field
parameter annotations.
"""

import logging
from typing import Any, Dict, List, Optional

from pydantic import Field
from fastmcp import Context

from terraform_mcp_server.tools.base import BaseTool
from terraform_mcp_server.core.tools.tf_ingestion_tool import TFIngestionTool

logger = logging.getLogger(__name__)


class TerraformIngestionTools(BaseTool):
    """MCP tool registration for Terraform document ingestion.
    
    Delegates execution to the existing TFIngestionTool in core/tools/,
    preserving the public MCP tool name and JSON response contract.
    """
    
    def register(self, mcp_instance) -> None:
        """Register ingest_terraform_docs with the MCP instance."""
        neo4j_graph = self.neo4j_graph
        
        @mcp_instance.tool()
        async def ingest_terraform_docs(
            filter_types: List[str] = Field(
                description=(
                    "Document types to ingest: 'resource', 'data_source', "
                    "'datasource', 'best_practice', 'terraform' (both resource "
                    "and data_source), 'readme'"
                ),
            ),
            filter_services: Optional[List[str]] = Field(
                default=None,
                description="Filter by specific services (e.g., ['S3', 'EC2'])",
            ),
            scan_dirs: Optional[List[str]] = Field(
                default=None,
                description=(
                    "Directories to scan for documents "
                    "(default: ['docs/', 'terraform_mcp_server/docs/'])"
                ),
            ),
            context: Context = None,
        ) -> str:
            """Ingest Terraform documentation into the knowledge graph.
            
            Processes resources, data sources, and best practices using
            vector embeddings and structured chunking, storing results
            in Neo4j for semantic search and retrieval.
            
            Supports automatic ingestion from index files (resources,
            data sources) and directory scanning (best practices, READMEs).
            """
            dependencies = {'neo4j_graph': neo4j_graph} if neo4j_graph else {}
            ingestion_tool = TFIngestionTool(dependencies)
            
            return await ingestion_tool.execute(
                filter_types=filter_types,
                filter_services=filter_services,
                scan_dirs=scan_dirs,
                context=context,
            )
