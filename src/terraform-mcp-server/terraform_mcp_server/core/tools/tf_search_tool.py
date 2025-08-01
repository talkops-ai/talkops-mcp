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
Vector Search Tool Implementation.

This module implements the vector_search tool that provides semantic search
capabilities using vector embeddings stored in Neo4j with LangChain integration.
"""
from typing import List, Dict, Any, Optional
from datetime import datetime
from langchain_neo4j import Neo4jGraph, Neo4jVector
from langchain_openai import OpenAIEmbeddings
from pydantic import BaseModel, Field, field_validator
from terraform_mcp_server.core.tools.base_tool import BaseMCPTool
from terraform_mcp_server.config import Config
from terraform_mcp_server.utils.logging import get_logger
from terraform_mcp_server.utils.errors import ConfigurationError
from mcp.server.fastmcp import Context
from terraform_mcp_server.utils.logging import log_with_request_id, LogLevel

logger = get_logger(__name__)


# =============================================================================
# Pydantic Models for Input/Output Validation
# =============================================================================

class VectorSearchInput(BaseModel):
    """
    Input model for vector search requests.
    
    Validates and structures input parameters for semantic similarity search.
    """
    query: str = Field(
        ..., 
        description="The search query to find similar document chunks",
        min_length=1,
        max_length=1000
    )
    top_k: int = Field(
        default=5, 
        ge=1, 
        le=50, 
        description="Number of top results to return"
    )
    similarity_threshold: float = Field(
        default=0.7, 
        ge=0.0, 
        le=1.0, 
        description="Minimum similarity score threshold (0.0 to 1.0)"
    )
    node_types: Optional[List[str]] = Field(
        default=None,
        description="List of node types to search: 'resource', 'data_source', 'best_practice'. If None, searches all types."
    )
    
    @field_validator('node_types')
    @classmethod
    def validate_node_types(cls, v):
        """Validate node types if provided."""
        if v is not None:
            valid_types = ['resource', 'data_source', 'best_practice']
            for node_type in v:
                if node_type not in valid_types:
                    raise ValueError(f"Node type must be one of: {valid_types}")
        return v
    
    @field_validator('query')
    @classmethod
    def validate_query(cls, v):
        """Validate and clean the search query."""
        if not v or not v.strip():
            raise ValueError("Query cannot be empty or whitespace only")
        return v.strip()
    
    @field_validator('similarity_threshold')
    @classmethod
    def validate_threshold(cls, v):
        """Validate similarity threshold is reasonable."""
        if v < 0.0 or v > 1.0:
            raise ValueError("Similarity threshold must be between 0.0 and 1.0")
        return v


class SearchResult(BaseModel):
    """
    Model for individual search results.
    
    Represents a single document chunk with its metadata and similarity score.
    """
    content: str = Field(..., description="Document chunk content")
    similarity_score: float = Field(..., ge=0.0, le=1.0, description="Similarity score (0.0 to 1.0)")
    node_type: str = Field(..., description="Type of node: 'resource', 'data_source', 'best_practice'")
    id: Optional[str] = Field(None, description="Document chunk ID")
    chunk_index: Optional[int] = Field(None, ge=0, description="Chunk index within source document")
    source_path: Optional[str] = Field(None, description="Source file path")
    file_name: Optional[str] = Field(None, description="Source file name")
    loader: Optional[str] = Field(None, description="Document loader used")
    ingested_at: Optional[str] = Field(None, description="Ingestion timestamp")
    
    @field_validator('similarity_score')
    @classmethod
    def validate_score(cls, v):
        """Validate similarity score is within valid range."""
        if v < 0.0 or v > 1.0:
            raise ValueError("Similarity score must be between 0.0 and 1.0")
        return v


class SearchParameters(BaseModel):
    """
    Model for search parameters used in the request.
    
    Tracks the parameters that were applied during the search.
    """
    top_k: int = Field(..., ge=1, le=50, description="Number of results requested")
    similarity_threshold: float = Field(..., ge=0.0, le=1.0, description="Similarity threshold applied")


class ServiceInfo(BaseModel):
    """
    Model for service configuration information.
    
    Provides details about the embedding service and configuration used.
    """
    provider: str = Field(..., description="Embedding provider (e.g., 'openai')")
    model: str = Field(..., description="Embedding model used")
    dimensions: int = Field(..., gt=0, description="Embedding dimensions")
    index_name: str = Field(..., description="Vector index name")
    integration: str = Field(..., description="Integration framework (e.g., 'langchain_neo4j')")


class VectorSearchOutput(BaseModel):
    """
    Output model for vector search responses.
    
    Provides a structured response with search results and metadata.
    """
    query: str = Field(..., description="Original search query")
    results_count: int = Field(..., ge=0, description="Number of results returned")
    results: List[SearchResult] = Field(..., description="Search results")
    search_parameters: SearchParameters = Field(..., description="Search parameters used")
    service_info: ServiceInfo = Field(..., description="Service configuration info")
    
    @field_validator('results_count')
    @classmethod
    def validate_results_count(cls, v, info):
        """Validate results count matches actual results."""
        if 'results' in info.data and v != len(info.data['results']):
            raise ValueError("Results count must match the number of actual results")
        return v


# =============================================================================
# Vector Search Tool Implementation
# =============================================================================

class TFSearchTool(BaseMCPTool):
    """
    Vector Search Tool for semantic similarity search over document chunks.
    
    This tool performs vector similarity search to retrieve relevant document 
    chunks based on user queries using embeddings stored in Neo4j with LangChain integration.
    
    Features:
    - Pydantic input/output validation
    - Configurable similarity thresholds
    - Rich metadata extraction
    - Comprehensive error handling
    - Context-aware logging with request IDs
    """
    
    def __init__(self, dependencies: Optional[Dict[str, Any]] = None):
        super().__init__(dependencies)
        self.config = Config()
        self.context = None  # Will be set during request execution
        self._components_initialized = False
        self._validate_config()
        # Don't initialize components here - do it lazily on first use
    
    def _safe_log(self, level: LogLevel, message: str, **kwargs: Any) -> None:
        """
        Safely log a message with context, falling back to regular logging if context is not available.
        
        Args:
            level: The log level
            message: The message to log
            **kwargs: Additional fields to include in the log message
        """
        try:
            # Only try context-aware logging if we have a valid context
            if (hasattr(self, 'context') and 
                self.context is not None and 
                hasattr(self.context, 'request_id')):
                log_with_request_id(self.context, level, message, **kwargs)
            else:
                # Fallback to regular logging
                if level == LogLevel.DEBUG:
                    logger.debug(message, **kwargs)
                elif level == LogLevel.INFO:
                    logger.info(message, **kwargs)
                elif level == LogLevel.WARNING:
                    logger.warning(message, **kwargs)
                elif level == LogLevel.ERROR:
                    logger.error(message, **kwargs)
                elif level == LogLevel.CRITICAL:
                    logger.critical(message, **kwargs)
        except Exception as e:
            # Ultimate fallback to prevent logging errors from breaking the tool
            logger.error(f"Logging failed: {e}. Original message: {message}")
    
    def _validate_config(self):
        """Validate required configuration for vector search."""
        required_configs = [
            'NEO4J_URI', 'NEO4J_USERNAME', 'NEO4J_PASSWORD',
            'EMBEDDING_MODEL', 'EMBEDDING_DIMENSIONS'
        ]
        
        missing_configs = []
        for config_name in required_configs:
            if not hasattr(self.config, config_name) or not getattr(self.config, config_name):
                missing_configs.append(config_name)
        
        if missing_configs:
            self._safe_log(
                LogLevel.ERROR, 
                f"Missing required configuration for vector search: {missing_configs}"
            )
            raise ConfigurationError(
                f"Missing required configuration for vector search: {missing_configs}"
            )
    
    def _ensure_components_initialized(self):
        """Ensure components are initialized (lazy initialization)."""
        if not self._components_initialized:
            self._initialize_components()
            self._components_initialized = True
    
    def _initialize_components(self):
        """Initialize Neo4jGraph and Neo4jVector components."""
        try:
            self._safe_log(
                LogLevel.INFO, 
                "Initializing vector search components..."
            )
            
            # Initialize Neo4jGraph connection
            self.neo4j_graph = Neo4jGraph(
                url=self.config.NEO4J_URI,
                username=self.config.NEO4J_USERNAME,
                password=self.config.NEO4J_PASSWORD,
            )
            self._safe_log(
                LogLevel.INFO, 
                "Neo4jGraph connection established successfully"
            )
            
            # Initialize embedding model
            self.embedding_model = OpenAIEmbeddings(
                model=self.config.EMBEDDING_MODEL
            )
            self._safe_log(
                LogLevel.INFO, 
                f"Embedding model initialized: {self.config.EMBEDDING_MODEL}"
            )
            
            # Define retrieval queries for different node types
            self.retrieval_queries = {
                "resource": """
                MATCH (node:DocChunk_Resource)
                RETURN 
                    node.content AS text,
                    score,
                    {
                        id: node.id,
                        node_type: 'resource'
                    } AS metadata
                ORDER BY score DESC
                """,
                "data_source": """
                MATCH (node:DocChunk_DataSource)
                RETURN 
                    node.content AS text,
                    score,
                    {
                        id: node.id,
                        node_type: 'data_source'
                    } AS metadata
                ORDER BY score DESC
                """,
                "best_practice": """
                MATCH (node:DocChunk_BestPractice)
                RETURN 
                    node.content AS text,
                    score,
                    {
                        id: node.id,
                        node_type: 'best_practice'
                    } AS metadata
                ORDER BY score DESC
                """
            }
            
            # Initialize vector stores for each node type
            self.vector_stores = {}
            index_names = {
                "resource": "docchunk_resource_embedding_hnsw",
                "data_source": "docchunk_datasource_embedding_hnsw", 
                "best_practice": "docchunk_bestpractice_embedding_hnsw"
            }
            
            for node_type, index_name in index_names.items():
                try:
                    self.vector_stores[node_type] = Neo4jVector.from_existing_index(
                        embedding=self.embedding_model,
                        graph=self.neo4j_graph,
                        index_name=index_name,
                        embedding_node_property="embedding",
                        text_node_property="content",
                        retrieval_query=self.retrieval_queries[node_type]
                    )
                    self._safe_log(
                        LogLevel.INFO, 
                        f"Neo4jVector initialized for {node_type} with index {index_name}"
                    )
                except Exception as e:
                    self._safe_log(
                        LogLevel.WARNING, 
                        f"Failed to initialize vector store for {node_type}: {e}"
                    )
                    # Continue with other node types
            
            self._safe_log(
                LogLevel.INFO, 
                f"Vector stores initialized for {len(self.vector_stores)} node types"
            )
            
            self._safe_log(
                LogLevel.INFO, 
                "Vector search components initialization completed successfully"
            )
            
        except Exception as e:
            self._safe_log(
                LogLevel.ERROR, 
                f"Failed to initialize vector search components: {e}"
            )
            raise ConfigurationError(f"Vector search initialization failed: {e}")
    
    @property
    def tool_name_mcp(self) -> str:
        """Return the MCP tool name."""
        return "terraform_doc_search"
    
    @property
    def tool_description(self) -> str:
        """Return the tool description for MCP registration."""
        return "Perform semantic similarity search over terraform document chunks using vector embeddings with LangChain Neo4j integration"
    
    @property
    def input_schema(self) -> Dict[str, Any]:
        """Define input schema for validation using Pydantic model."""
        return VectorSearchInput.schema()
    
    @property
    def output_schema(self) -> Dict[str, Any]:
        """Define output schema for validation using Pydantic model."""
        return VectorSearchOutput.schema()
    
    async def execute(self, query: str, top_k: int = 5, similarity_threshold: float = 0.7, node_types: Optional[List[str]] = None, context: Optional[Context] = None) -> str:
        """
        Execute vector similarity search with Pydantic validation.
        
        Args:
            query: Search query string
            top_k: Number of results to return (default: 5)
            similarity_threshold: Minimum similarity score (default: 0.7)
            node_types: List of node types to search (default: None, searches all types)
        
        Returns:
            JSON-formatted string containing validated search results
        """
        try:
            # Set context for this request if provided
            if context is not None:
                self.context = context
            
            # Ensure components are initialized (lazy initialization)
            self._ensure_components_initialized()
            
            # Validate input using Pydantic model
            input_data = VectorSearchInput(
                query=query,
                top_k=top_k,
                similarity_threshold=similarity_threshold,
                node_types=node_types
            )
            
            self._safe_log(
                LogLevel.INFO, 
                f"Performing vector search: query='{input_data.query}', top_k={input_data.top_k}, threshold={input_data.similarity_threshold}"
            )
            
            # Perform similarity search
            results = self._perform_similarity_search(
                input_data.query, 
                input_data.top_k, 
                input_data.similarity_threshold,
                input_data.node_types
            )
            
            # Create validated output using Pydantic model
            output_data = VectorSearchOutput(
                query=input_data.query,
                results_count=len(results),
                results=results,
                search_parameters=SearchParameters(
                    top_k=input_data.top_k,
                    similarity_threshold=input_data.similarity_threshold
                ),
                service_info=ServiceInfo(
                    provider="openai",
                    model=self.config.EMBEDDING_MODEL,
                    dimensions=self.config.EMBEDDING_DIMENSIONS,
                    index_name=", ".join([f"docchunk_{nt}_embedding_hnsw" for nt in (input_data.node_types or ["resource", "data_source", "best_practice"])]),
                    integration="langchain_neo4j"
                )
            )
            
            self._safe_log(
                LogLevel.INFO, 
                f"Vector search completed successfully: {len(results)} results found"
            )
            
            return self.format_response(output_data.model_dump(), success=True)
            
        except Exception as e:
            self._safe_log(
                LogLevel.ERROR, 
                f"Vector search failed: {e}",
                query=query,
                top_k=top_k,
                similarity_threshold=similarity_threshold
            )
            return self.handle_error(e, context={"query": query, "top_k": top_k, "similarity_threshold": similarity_threshold})
    
    def _perform_similarity_search(self, query: str, top_k: int, similarity_threshold: float, node_types: Optional[List[str]] = None) -> List[SearchResult]:
        """
        Perform the actual similarity search using Neo4jVector across multiple node types.
        
        Args:
            query: Search query
            top_k: Number of results to return
            similarity_threshold: Minimum similarity score
            node_types: List of node types to search (None = all types)
        
        Returns:
            List of validated SearchResult objects
        """
        try:
            # Determine which node types to search
            if node_types is None:
                search_types = list(self.vector_stores.keys())
            else:
                search_types = [nt for nt in node_types if nt in self.vector_stores]
            
            if not search_types:
                self._safe_log(
                    LogLevel.WARNING, 
                    "No valid node types found for search"
                )
                return []
            
            self._safe_log(
                LogLevel.DEBUG, 
                f"Starting similarity search across node types: {search_types}, top_k={top_k}, threshold={similarity_threshold}"
            )
            
            all_results = []
            
            # Search each node type
            for node_type in search_types:
                try:
                    vector_store = self.vector_stores[node_type]
                    # Calculate per-type top_k (distribute evenly)
                    per_type_top_k = max(1, top_k // len(search_types))
                    
                    docs_and_scores = vector_store.similarity_search_with_score(
                        query, 
                        k=per_type_top_k
                    )
                    
                    for doc, score in docs_and_scores:
                        # Filter by similarity threshold
                        if score >= similarity_threshold:
                            # Create validated SearchResult using Pydantic model
                            # Only use metadata properties that are actually returned by our query
                            result = SearchResult(
                                content=doc.page_content,
                                similarity_score=score,
                                node_type=node_type,
                                id=doc.metadata.get("id"),
                                # These properties are not available in the current database schema
                                # chunk_index=None,
                                # source_path=None,
                                # file_name=None,
                                # loader=None,
                                # ingested_at=None
                            )
                            all_results.append(result)
                    
                    self._safe_log(
                        LogLevel.DEBUG, 
                        f"Found {len([r for r in all_results if r.node_type == node_type])} results for {node_type}"
                    )
                    
                except Exception as e:
                    self._safe_log(
                        LogLevel.WARNING, 
                        f"Search failed for node type {node_type}: {e}"
                    )
                    continue
            
            # Sort all results by similarity score (highest first) and limit to top_k
            all_results.sort(key=lambda x: x.similarity_score, reverse=True)
            final_results = all_results[:top_k]
            
            self._safe_log(
                LogLevel.INFO, 
                f"Found {len(final_results)} total results above threshold {similarity_threshold}",
                total_candidates=len(all_results),
                filtered_results=len(final_results),
                node_types_searched=search_types
            )
            return final_results
            
        except Exception as e:
            self._safe_log(
                LogLevel.ERROR, 
                f"Similarity search failed: {e}"
            )
            raise
    
    def get_tool_health(self) -> Dict[str, Any]:
        """
        Get tool health status and diagnostics.
        
        Returns:
            Dictionary containing health information
        """
        try:
            self._safe_log(
                LogLevel.DEBUG, 
                "Health check requested for vector search tool"
            )
            
            health_info = {
                "status": "healthy",
                "components": {
                    "neo4j_graph": "connected",
                    "embedding_model": "initialized",
                    "vector_store": "initialized",
                    "configuration": "validated",
                    "pydantic_models": "loaded"
                },
                "configuration": {
                    "embedding_model": self.config.EMBEDDING_MODEL,
                    "embedding_dimension": self.config.EMBEDDING_DIMENSIONS,
                    "index_name": "docchunk_embedding_hnsw",
                    "node_label": "DocChunk",
                    "integration": "langchain_neo4j"
                },
                "validation": {
                    "input_schema": "pydantic",
                    "output_schema": "pydantic",
                    "models": ["VectorSearchInput", "VectorSearchOutput", "SearchResult"]
                }
            }
            
            self._safe_log(
                LogLevel.INFO, 
                "Health check completed successfully"
            )
            
            return health_info
            
        except Exception as e:
            self._safe_log(
                LogLevel.ERROR, 
                f"Health check failed: {e}"
            )
            return {
                "status": "unhealthy",
                "error": str(e),
                "components": {},
                "configuration": {},
                "validation": {}
            }


def create_tf_search_tool(dependencies: Dict[str, Any]) -> TFSearchTool:
    """
    Factory function to create a TFSearchTool instance.
    
    Args:
        dependencies: Dictionary containing required dependencies
        
    Returns:
        TFSearchTool: Configured Terraform search tool instance
        
    Raises:
        ConfigurationError: If required dependencies are missing
    """
    try:
        return TFSearchTool(dependencies)
    except Exception as e:
        raise ConfigurationError(f"Failed to create TFSearchTool: {str(e)}") 