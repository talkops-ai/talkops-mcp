# Copyright (C) 2025 StructBinary
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Restructured FastMCP Server Implementation for Terraform Knowledge Graph.

This module implements a FastMCP server using the official MCP SDK with
a clean, simple approach focused on vector search capabilities.
"""

import logging
import signal
import sys
from typing import List, Dict
from mcp.server.fastmcp import FastMCP, Context
from langchain_neo4j import Neo4jGraph
from terraform_mcp_server.config import Config
from terraform_mcp_server.core.tools import TFSearchTool, TFIngestionTool, TFExecutionTool, register_tool_with_fastmcp

logger = logging.getLogger(__name__)


def create_server(host: str = "localhost", port: int = 8000):
    """Creates and returns a FastMCP server instance for Terraform Knowledge Graph operations."""
    return FastMCP(
        'terraform-knowledge-graph-server',
        instructions='This server provides MCP tools for vector similarity search, GraphRAG recommendations, and Terraform command execution using Neo4jVector and Natural Language Query Pipeline.',
        host=host,
        port=port
    )


def main(host: str = "localhost", port: int = 8000, transport: str = "stdio"):
    """Main function that sets up the server and registers the vector search tool."""
    logger.info(f"main() starting with host={host}, port={port}, transport={transport}")
    
    # Create server instance
    server = create_server(host, port)
    logger.info("FastMCP server instance created.")
    
    # Initialize services
    config = Config()
    
    # Create Neo4j connection
    neo4j_graph = Neo4jGraph(
        url=config.NEO4J_URI,
        username=config.NEO4J_USERNAME,
        password=config.NEO4J_PASSWORD
    )
    
    logger.info("Neo4j connection established.")
    
    # Register Terraform search tool
    register_tf_search_tool(server, neo4j_graph)
    
    # Register Terraform ingestion tool
    register_tf_ingestion_tool(server, neo4j_graph)
    
    # Register Terraform execution tool
    register_tf_execution_tool(server)
    
    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, lambda signum, frame: handle_shutdown(signum, frame))
    signal.signal(signal.SIGTERM, lambda signum, frame: handle_shutdown(signum, frame))
    
    logger.info("Server initialization complete. Starting server...")
    
    # Start the server
    server.run(transport=transport)
    logger.info("FastMCP server run() has returned (should not happen unless server exits)")


def register_tf_search_tool(server: FastMCP, neo4j_graph: Neo4jGraph):
    """Register the Terraform search tool with the server."""
    logger.info("Registering Terraform search tool...")
    
    # Create dependencies for the Terraform search tool
    dependencies = {
        'neo4j_graph': neo4j_graph
    }
    
    # Create tool instance (lazy initialization will happen on first use)
    tf_search_tool = TFSearchTool(dependencies)
    logger.info("TFSearchTool instance created (components will initialize on first use)")
    
    @server.tool(name=tf_search_tool.tool_name_mcp, description=tf_search_tool.tool_description)
    async def tf_search(query: str, top_k: int = 5, similarity_threshold: float = 0.7, node_types: List[str] = None, context: Context = None) -> str:
        """
        Perform semantic vector similarity search over terraform document chunks using LangChain Neo4j integration.

        This tool provides semantic search capabilities over terraform document chunks by using vector embeddings
        to find similar content in the knowledge graph. It leverages Neo4jVector
        with the existing docchunk_embedding_hnsw index for fast similarity search.

        ## Arguments
        - query (str): The search query text to find similar content for.
        - top_k (int): Number of results to return (1-50, default: 5).
        - similarity_threshold (float): Minimum similarity score threshold (0.0-1.0, default: 0.7).
        - node_types (List[str], optional): List of node types to search: 'resource', 'data_source', 'best_practice'. If None, searches all types.

        ## Usage Tips
        - Use natural language queries to find relevant Terraform documentation.
        - Adjust top_k based on how many results you need.
        - Use similarity_threshold to filter out low-quality matches.
        - Use node_types to search specific document types (resources, data sources, best practices).
        - Results are ranked by similarity score (higher is better).
        - When searching multiple node types, results are distributed evenly across types.

        ## Response Information
        - Returns a JSON string with search results, scores, and metadata.
        - Each result includes content, similarity score, and DocChunk metadata.
        - Includes service information about the embedding model and integration.

        ## Examples
        Search for AWS S3 bucket configuration across all types:
            result = await terraform_doc_search(
                query="AWS S3 bucket configuration",
                top_k=5,
                similarity_threshold=0.7
            )

        Search only in resources:
            result = await terraform_doc_search(
                query="AWS S3 bucket configuration",
                top_k=5,
                similarity_threshold=0.7,
                node_types=["resource"]
            )

        Search in resources and best practices:
            result = await terraform_doc_search(
                query="AWS S3 bucket configuration",
                top_k=10,
                similarity_threshold=0.7,
                node_types=["resource", "best_practice"]
            )

        ## Response Format
        {
            "query": "AWS S3 bucket configuration",
            "results_count": 5,
            "results": [
                {
                    "content": "S3 bucket configuration content...",
                    "similarity_score": 0.95,
                    "node_type": "resource",
                    "id": "chunk_123",
                    "source_path": "https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/s3_bucket",
                    "file_name": "s3_bucket.md",
                    "loader": "terraform_markdown",
                    "ingested_at": "2025-01-15T10:30:00"
                }
            ],
            "search_parameters": {
                "top_k": 5,
                "similarity_threshold": 0.7
            },
            "service_info": {
                "provider": "openai",
                "model": "text-embedding-3-large",
                "dimensions": 3072,
                "index_name": "docchunk_resource_embedding_hnsw, docchunk_datasource_embedding_hnsw, docchunk_bestpractice_embedding_hnsw",
                "integration": "langchain_neo4j"
            }
        }
        """
        return await tf_search_tool.execute(
            query=query, 
            top_k=top_k, 
            similarity_threshold=similarity_threshold,
            node_types=node_types,
            context=context
        )
    
    logger.info("Terraform search tool registered successfully.")


def register_tf_ingestion_tool(server: FastMCP, neo4j_graph: Neo4jGraph):
    """Register the Terraform ingestion tool with the server."""
    logger.info("Registering Terraform ingestion tool...")
    
    # Create dependencies for the Terraform ingestion tool
    dependencies = {
        'neo4j_graph': neo4j_graph
    }
    
    # Create tool instance (lazy initialization will happen on first use)
    tf_ingestion_tool = TFIngestionTool(dependencies)
    logger.info("TFIngestionTool instance created (components will initialize on first use)")
    
    @server.tool(name=tf_ingestion_tool.tool_name_mcp, description=tf_ingestion_tool.tool_description)
    async def tf_ingestion(filter_types: List[str], filter_services: List[str] = None,
                          scan_dirs: List[str] = None, context: Context = None) -> str:
        """
        Ingest and process Terraform documentation into searchable knowledge graph.

        This tool provides comprehensive document ingestion capabilities for Terraform
        resources, data sources, and best practices. It automatically discovers and processes
        documents using vector embeddings and structured chunking, storing them in Neo4j
        for semantic search and retrieval.

        ## Key Capabilities
        - **Resource Ingestion**: Process Terraform resources from index files
        - **Data Source Ingestion**: Process Terraform data sources from index files  
        - **Best Practice Ingestion**: Discover and process best practice documents from directory scans
        - **README Ingestion**: Process README documents from directory scans
        - **Vector Embeddings**: Generate embeddings for semantic search
        - **Structured Chunking**: Break documents into searchable chunks
        - **Neo4j Storage**: Store processed data in knowledge graph

        ## Arguments
        - filter_types (List[str]): Document types to ingest:
          - 'resource': Ingest Terraform resources from index
          - 'data_source': Ingest Terraform data sources from index  
          - 'datasource': Ingest Terraform data sources from index (alternative to data_source)
          - 'best_practice': Ingest best practice documents from scan
          - 'readme': Ingest README documents from scan
          - 'terraform': Ingest both resources and data sources (equivalent to ['resource', 'data_source'])
        - filter_services (List[str], optional): Filter by specific services (e.g., ['S3', 'EC2'])
        - scan_dirs (List[str], optional): Directories to scan for documents (default: ["docs/", "tf_knowledge_graph/docs/"])

        ## Common Use Cases
        - **Ingest Resources**: `filter_types=["resource"]` - Process Terraform resources from index
        - **Ingest Data Sources**: `filter_types=["data_source"]` - Process Terraform data sources from index
        - **Ingest Best Practices**: `filter_types=["best_practice"]` - Process best practice documents
        - **Ingest Everything**: `filter_types=["terraform", "best_practice"]` - Process all document types
        - **Service-Specific**: `filter_types=["resource"], filter_services=["S3"]` - Process only S3 resources

        ## Usage Tips
        - Use ['resource'] to ingest only Terraform resources
        - Use ['data_source'] to ingest only Terraform data sources
        - Use ['terraform'] to ingest both resources and data sources
        - Use ['best_practice'] to ingest best practice documents
        - Use ['resource', 'best_practice'] to ingest both resources and best practices
        - The tool automatically resolves 'terraform' to ['resource', 'data_source']
        - Resources and data sources are ingested from the default index file
        - Best practices are discovered by scanning the specified directories

        ## Response Information
        - Returns a JSON string with ingestion results and metadata
        - Each result includes status, error information, and strategies applied
        - Includes performance metrics for the ingestion process
        - Provides configuration information used during ingestion

        ## Examples
        Ingest only Terraform resources:
            result = await ingest_terraform_docs(filter_types=["resource"])

        Ingest only data sources:
            result = await ingest_terraform_docs(filter_types=["data_source"])

        Ingest both resources and data sources:
            result = await ingest_terraform_docs(filter_types=["terraform"])

        Ingest best practices:
            result = await ingest_terraform_docs(filter_types=["best_practice"])

        Ingest everything:
            result = await ingest_terraform_docs(filter_types=["terraform", "best_practice"])

        Ingest S3-specific resources:
            result = await ingest_terraform_docs(filter_types=["resource"], filter_services=["S3"])

        ## Response Format
        {
            "operation_type": "automatic",
            "results": [
                {
                    "path": "tf_knowledge_graph/docs/AWS_PROVIDER_TEST.md",
                    "doc_type": "index",
                    "status": "success",
                    "error": null,
                    "strategies": ["index_based"],
                    "chunks_created": null,
                    "embeddings_generated": null
                },
                {
                    "path": "scan",
                    "doc_type": "best_practice",
                    "status": "success",
                    "error": null,
                    "strategies": ["scan_based"],
                    "chunks_created": null,
                    "embeddings_generated": null
                }
            ],
            "metrics": {
                "total_documents": 0,
                "successful_ingestions": 2,
                "failed_ingestions": 0,
                "skipped_ingestions": 0,
                "total_chunks_created": 0,
                "total_embeddings_generated": 0,
                "processing_time_seconds": 45.2
            },
            "configuration": {
                "embedding_model": "text-embedding-3-large",
                "embedding_provider": "openai",
                "embedding_dimensions": 3072,
                "neo4j_uri": "bolt://localhost:7687"
            }
        }
        """
        return await tf_ingestion_tool.execute(
            filter_types=filter_types,
            filter_services=filter_services,
            scan_dirs=scan_dirs,
            context=context
        )
    
    logger.info("Terraform ingestion tool registered successfully.")


def register_tf_execution_tool(server: FastMCP):
    """Register the Terraform execution tool with the server."""
    logger.info("Registering Terraform execution tool...")
    
    # Create dependencies for the Terraform execution tool (no external dependencies needed)
    dependencies = {}
    
    # Create tool instance
    tf_execution_tool = TFExecutionTool(dependencies)
    logger.info("TFExecutionTool instance created")
    
    @server.tool(name=tf_execution_tool.tool_name_mcp, description=tf_execution_tool.tool_description)
    async def tf_execution(command: str, working_directory: str, variables: Dict[str, str] = None,
                          aws_region: str = None, strip_ansi: bool = True, timeout: int = None,
                          context: Context = None) -> str:
        """
        Execute Terraform commands securely with comprehensive validation and security checks.

        This tool provides secure execution of Terraform commands with comprehensive
        validation, security checks, and configurable parameters. It supports all
        standard Terraform commands with proper error handling and output processing.

        ## Key Capabilities
        - **Command Validation**: Validate Terraform commands (init, plan, validate, apply, destroy)
        - **Security Checks**: Comprehensive security pattern detection and validation
        - **Configurable Timeouts**: Set execution timeouts with configurable limits
        - **Output Processing**: Clean ANSI codes and handle command outputs
        - **AWS Integration**: Support for AWS region configuration
        - **Variable Handling**: Secure variable validation and processing
        - **Output Extraction**: Extract Terraform outputs for apply commands
        - **Error Handling**: Comprehensive error handling and logging

        ## Arguments
        - command (str): The Terraform command to execute (init, plan, validate, apply, destroy)
        - working_directory (str): Directory containing Terraform configuration files
        - variables (Dict[str, str], optional): Optional dictionary of Terraform variables to pass
        - aws_region (str, optional): Optional AWS region to use for the execution
        - strip_ansi (bool, optional): Whether to strip ANSI color codes from command output (default: True)
        - timeout (int, optional): Command execution timeout in seconds (1-1800, default: 300)

        ## Security Features
        - **Command Injection Prevention**: Validates all inputs against dangerous patterns
        - **Directory Traversal Protection**: Prevents access to unauthorized directories
        - **Variable Sanitization**: Cleans and validates Terraform variables
        - **Working Directory Validation**: Ensures safe directory operations
        - **Timeout Protection**: Prevents long-running commands from hanging

        ## Usage Tips
        - Always use relative paths for working_directory when possible
        - Set appropriate timeouts for long-running operations
        - Use variables parameter for passing Terraform variables securely
        - Enable strip_ansi for clean output in automated environments
        - Set aws_region for AWS-specific operations

        ## Response Information
        - Returns a JSON string with execution results and metadata
        - Includes command output, error information, and execution time
        - Provides Terraform outputs for successful apply commands
        - Includes security validation status and configuration details

        ## Examples
        Initialize Terraform:
            result = await terraform_execute(
                command="init",
                working_directory="./terraform"
            )

        Plan with variables:
            result = await terraform_execute(
                command="plan",
                working_directory="./terraform",
                variables={"environment": "production", "instance_type": "t3.micro"},
                aws_region="us-west-2"
            )

        Apply with timeout:
            result = await terraform_execute(
                command="apply",
                working_directory="./terraform",
                variables={"environment": "production"},
                timeout=600
            )

        Validate configuration:
            result = await terraform_execute(
                command="validate",
                working_directory="./terraform"
            )

        ## Response Format
        {
            "command": "terraform apply",
            "status": "success",
            "result": {
                "command": "terraform apply",
                "status": "success",
                "return_code": 0,
                "stdout": "Apply complete! Resources: 3 added, 0 changed, 0 destroyed.",
                "stderr": "",
                "working_directory": "./terraform",
                "error_message": null,
                "outputs": {
                    "instance_id": "i-1234567890abcdef0",
                    "public_ip": "203.0.113.1"
                },
                "execution_time": 45.2
            },
            "metadata": {
                "terraform_version": "1.5.0",
                "aws_region": "us-west-2",
                "variables_count": 2,
                "outputs_count": 2,
                "security_checks_passed": true
            },
            "configuration": {
                "terraform_binary_path": "terraform",
                "allowed_commands": ["init", "plan", "validate", "apply", "destroy"],
                "default_timeout": 300,
                "max_timeout": 1800,
                "security_enabled": true
            }
        }
        """
        return await tf_execution_tool.execute(
            command=command,
            working_directory=working_directory,
            variables=variables,
            aws_region=aws_region,
            strip_ansi=strip_ansi,
            timeout=timeout,
            context=context
        )
    
    logger.info("Terraform execution tool registered successfully.")


def handle_shutdown(signum, frame):
    """Handle shutdown signals gracefully."""
    logger.info(f'Received signal {signum}, initiating shutdown...')
    shutdown()


def shutdown():
    """Gracefully shut down the Terraform Knowledge Graph MCP Server."""
    try:
        logger.info('Shutting down Terraform Knowledge Graph MCP Server...')
        # Clean up resources here if needed
        logger.info('Shutdown complete.')
    except Exception as e:
        logger.error(f'Error during shutdown: {e}', exc_info=True)
    finally:
        sys.exit(0)


if __name__ == "__main__":
    main() 