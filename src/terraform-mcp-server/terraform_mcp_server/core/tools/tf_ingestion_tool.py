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
Terraform Document Ingestion Tool Implementation.

This module implements the tf_ingestion tool that provides document ingestion
capabilities for Terraform resources, data sources, and best practices using
the IngestionOrchestrator with vector embeddings and structured chunking.
"""
from typing import List, Dict, Any, Optional, Union
from datetime import datetime
from pydantic import BaseModel, Field, field_validator
from terraform_mcp_server.core.tools.base_tool import BaseMCPTool
from terraform_mcp_server.config import Config
from terraform_mcp_server.utils.logging import get_logger
from terraform_mcp_server.utils.errors import ConfigurationError
from terraform_mcp_server.ingestion_orchestrator import IngestionOrchestrator
from mcp.server.fastmcp import Context
from terraform_mcp_server.utils.logging import log_with_request_id, LogLevel

logger = get_logger(__name__)


# =============================================================================
# Pydantic Models for Input/Output Validation
# =============================================================================

class IngestionInput(BaseModel):
    """
    Input model for Terraform document ingestion requests.
    
    Validates and structures input parameters for automatic document ingestion.
    """
    filter_types: List[str] = Field(
        ..., 
        description="List of document types to ingest: 'resource', 'data_source', 'datasource', 'best_practice', 'terraform' (for both resource and data_source), 'readme'",
        min_items=1
    )
    filter_services: Optional[List[str]] = Field(
        default=None,
        description="Optional list of service names to filter by (e.g., ['S3', 'EC2'])"
    )
    scan_dirs: Optional[List[str]] = Field(
        default=["docs/", "terraform_mcp_server/docs/"],
        description="Directories to scan for best practices and other documents"
    )
    
    @field_validator('filter_types')
    @classmethod
    def validate_filter_types(cls, v):
        """Validate filter types."""
        valid_types = ['resource', 'data_source', 'datasource', 'best_practice', 'terraform', 'readme']
        for doc_type in v:
            if doc_type not in valid_types:
                raise ValueError(f"Filter type must be one of: {valid_types}")
        return v
    
    @field_validator('filter_services')
    @classmethod
    def validate_filter_services(cls, v):
        """Validate filter services if provided."""
        if v is not None and len(v) == 0:
            raise ValueError("Filter services list cannot be empty if provided")
        return v


class IngestionResult(BaseModel):
    """
    Model for individual ingestion results.
    
    Represents the result of ingesting a single document.
    """
    path: str = Field(..., description="Document path that was ingested")
    doc_type: str = Field(..., description="Type of document ingested")
    status: str = Field(..., description="Ingestion status: 'success', 'failure', 'skipped'")
    error: Optional[str] = Field(None, description="Error message if ingestion failed")
    strategies: List[str] = Field(..., description="Ingestion strategies applied")
    chunks_created: Optional[int] = Field(None, description="Number of chunks created")
    embeddings_generated: Optional[int] = Field(None, description="Number of embeddings generated")


class IngestionMetrics(BaseModel):
    """
    Model for ingestion performance metrics.
    
    Tracks performance and statistics for the ingestion process.
    """
    total_documents: int = Field(..., ge=0, description="Total number of documents processed")
    successful_ingestions: int = Field(..., ge=0, description="Number of successful ingestions")
    failed_ingestions: int = Field(..., ge=0, description="Number of failed ingestions")
    skipped_ingestions: int = Field(..., ge=0, description="Number of skipped ingestions (already ingested)")
    total_chunks_created: int = Field(..., ge=0, description="Total number of chunks created")
    total_embeddings_generated: int = Field(..., ge=0, description="Total number of embeddings generated")
    processing_time_seconds: float = Field(..., ge=0.0, description="Total processing time in seconds")


class IngestionOutput(BaseModel):
    """
    Output model for ingestion responses.
    
    Provides a structured response with ingestion results and metadata.
    """
    operation_type: str = Field(..., description="Type of ingestion operation performed")
    results: List[IngestionResult] = Field(..., description="Individual ingestion results")
    metrics: IngestionMetrics = Field(..., description="Ingestion performance metrics")
    configuration: Dict[str, Any] = Field(..., description="Configuration used for ingestion")
    
    @field_validator('operation_type')
    @classmethod
    def validate_operation_type(cls, v):
        """Validate operation type."""
        valid_types = ['single_document', 'index_based', 'unified', 'automatic']
        if v not in valid_types:
            raise ValueError(f"Operation type must be one of: {valid_types}")
        return v


# =============================================================================
# Terraform Ingestion Tool Implementation
# =============================================================================

class TFIngestionTool(BaseMCPTool):
    """
    Terraform Document Ingestion Tool for processing and storing Terraform documentation.
    
    This tool provides comprehensive document ingestion capabilities for Terraform
    resources, data sources, and best practices using vector embeddings and structured
    chunking with Neo4j integration.
    
    Features:
    - Single document ingestion
    - Index-based bulk ingestion
    - Unified ingestion with directory scanning
    - Pydantic input/output validation
    - Comprehensive error handling
    - Performance metrics tracking
    - Context-aware logging with request IDs
    """
    
    def __init__(self, dependencies: Optional[Dict[str, Any]] = None):
        super().__init__(dependencies)
        self.config = Config()
        self.context = None  # Will be set during request execution
        self._orchestrator_initialized = False
        self._validate_config()
        # Don't initialize orchestrator here - do it lazily on first use
    
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
        """Validate required configuration for document ingestion."""
        required_configs = [
            'NEO4J_URI', 'NEO4J_USERNAME', 'NEO4J_PASSWORD',
            'EMBEDDING_MODEL', 'EMBEDDING_DIMENSIONS', 'EMBEDDING_PROVIDER'
        ]
        
        missing_configs = []
        for config_name in required_configs:
            if not hasattr(self.config, config_name) or not getattr(self.config, config_name):
                missing_configs.append(config_name)
        
        if missing_configs:
            self._safe_log(
                LogLevel.ERROR, 
                f"Missing required configuration for document ingestion: {missing_configs}"
            )
            raise ConfigurationError(
                f"Missing required configuration for document ingestion: {missing_configs}"
            )
    
    def _ensure_orchestrator_initialized(self):
        """Ensure orchestrator is initialized (lazy initialization)."""
        if not self._orchestrator_initialized:
            self._initialize_orchestrator()
            self._orchestrator_initialized = True
    
    def _initialize_orchestrator(self):
        """Initialize the IngestionOrchestrator."""
        try:
            self._safe_log(
                LogLevel.INFO, 
                "Initializing Terraform document ingestion orchestrator..."
            )
            
            # Initialize the orchestrator with default configuration
            self.orchestrator = IngestionOrchestrator()
            
            self._safe_log(
                LogLevel.INFO, 
                "Ingestion orchestrator initialized successfully"
            )
            
        except Exception as e:
            self._safe_log(
                LogLevel.ERROR, 
                f"Failed to initialize ingestion orchestrator: {e}"
            )
            raise ConfigurationError(f"Document ingestion initialization failed: {e}")
    
    @property
    def tool_name_mcp(self) -> str:
        """Return the MCP tool name."""
        return "ingest_terraform_docs"
    
    @property
    def tool_description(self) -> str:
        """Return the tool description for MCP registration."""
        return "Ingest Terraform documentation (resources, data sources, best practices) into the knowledge graph using vector embeddings and structured chunking. Supports automatic ingestion of resources from index files, data sources from index files, and best practices from scanned directories. Use filter_types to specify what to ingest: 'resource', 'data_source', 'best_practice', 'terraform' (for both resource and data_source), or 'readme'."
    
    @property
    def input_schema(self) -> Dict[str, Any]:
        """Define input schema for validation using Pydantic model."""
        return IngestionInput.schema()
    
    @property
    def output_schema(self) -> Dict[str, Any]:
        """Define output schema for validation using Pydantic model."""
        return IngestionOutput.schema()
    
    async def execute(self, filter_types: List[str], filter_services: Optional[List[str]] = None,
                     scan_dirs: Optional[List[str]] = None, context: Optional[Context] = None) -> str:
        """
        Execute automatic Terraform document ingestion based on filter types.
        
        Args:
            filter_types: List of document types to ingest ('resource', 'data_source', 'best_practice', 'terraform')
            filter_services: Optional list of service names to filter by
            scan_dirs: Optional list of directories to scan for documents
        
        Returns:
            JSON-formatted string containing validated ingestion results
        """
        try:
            # Set context for this request if provided
            if context is not None:
                self.context = context
            
            # Ensure orchestrator is initialized (lazy initialization)
            self._ensure_orchestrator_initialized()
            
            start_time = datetime.now()
            
            self._safe_log(
                LogLevel.INFO, 
                f"Starting automatic Terraform document ingestion: filter_types={filter_types}"
            )
            
            # Validate input using Pydantic model
            validated_input = IngestionInput(
                filter_types=filter_types,
                filter_services=filter_services,
                scan_dirs=scan_dirs
            )
            
            # Execute automatic ingestion
            results, metrics = await self._ingest_automatically(validated_input)
            
            # Calculate processing time
            processing_time = (datetime.now() - start_time).total_seconds()
            metrics.processing_time_seconds = processing_time
            
            # Create validated output using Pydantic model
            output_data = IngestionOutput(
                operation_type="automatic",
                results=results,
                metrics=metrics,
                configuration={
                    "embedding_model": self.config.EMBEDDING_MODEL,
                    "embedding_provider": self.config.EMBEDDING_PROVIDER,
                    "embedding_dimensions": self.config.EMBEDDING_DIMENSIONS,
                    "neo4j_uri": self.config.NEO4J_URI,
                    "default_ingestion_config": self.orchestrator.config
                }
            )
            
            self._safe_log(
                LogLevel.INFO, 
                f"Automatic document ingestion completed successfully: {len(results)} documents processed",
                filter_types=filter_types,
                processing_time=processing_time
            )
            
            return self.format_response(output_data.model_dump(), success=True)
            
        except Exception as e:
            self._safe_log(
                LogLevel.ERROR, 
                f"Automatic document ingestion failed: {e}",
                filter_types=filter_types
            )
            return self.handle_error(e, context={"filter_types": filter_types})
    
    async def _ingest_automatically(self, input_data: IngestionInput) -> tuple[List[IngestionResult], IngestionMetrics]:
        """Automatically ingest documents based on filter types."""
        try:
            self._safe_log(
                LogLevel.INFO, 
                f"Starting automatic ingestion for filter types: {input_data.filter_types}"
            )
            
            # Process filter types and resolve to actual document types
            resolved_types = self._resolve_filter_types(input_data.filter_types)
            
            # Determine what to ingest based on resolved types
            index_path = None
            scan_dirs = input_data.scan_dirs or ["docs/", "terraform_mcp_server/docs/"]
            extra_docs = []
            
            # For best practices, always add the default best practice document
            if 'best_practice' in resolved_types:
                extra_docs.append({"path": "docs/terraform-aws-provider-best-practices.pdf", "type": "best_practice"})
            
            # Check if we need to ingest resources/data sources (from index)
            if any(doc_type in resolved_types for doc_type in ['resource', 'data_source']):
                index_path = self._get_default_index_path()
                self._safe_log(
                    LogLevel.INFO, 
                    f"Will ingest resources/data sources from index: {index_path}"
                )
            
            # Check if we need to ingest best practices (from scan + extra docs)
            if 'best_practice' in resolved_types:
                self._safe_log(
                    LogLevel.INFO, 
                    f"Will scan directories for best practices: {scan_dirs} and add default best practice document"
                )
            
            # Check if we need to ingest READMEs (from scan)
            if 'readme' in resolved_types:
                self._safe_log(
                    LogLevel.INFO, 
                    f"Will scan directories for READMEs: {scan_dirs}"
                )
            
            # Perform the unified ingestion
            self.orchestrator.unified_ingest(
                index_path=index_path,
                scan_dirs=scan_dirs,
                extra_docs=extra_docs,
                filter_types=resolved_types,
                filter_services=input_data.filter_services
            )
            
            # Create summary results
            results = []
            
            # Add result for index-based ingestion if applicable
            if index_path:
                results.append(IngestionResult(
                    path=index_path,
                    doc_type="index",
                    status="success",
                    error=None,
                    strategies=["index_based"],
                    chunks_created=None,
                    embeddings_generated=None
                ))
            
            # Add result for scan-based ingestion if applicable
            if 'best_practice' in resolved_types:
                results.append(IngestionResult(
                    path="scan",
                    doc_type="best_practice",
                    status="success",
                    error=None,
                    strategies=["scan_based"],
                    chunks_created=None,
                    embeddings_generated=None
                ))
            
            if 'readme' in resolved_types:
                results.append(IngestionResult(
                    path="scan",
                    doc_type="readme",
                    status="success",
                    error=None,
                    strategies=["scan_based"],
                    chunks_created=None,
                    embeddings_generated=None
                ))
            
            # Create metrics
            metrics = IngestionMetrics(
                total_documents=0,  # Not available for automatic ingestion
                successful_ingestions=len(results),
                failed_ingestions=0,
                skipped_ingestions=0,
                total_chunks_created=0,
                total_embeddings_generated=0,
                processing_time_seconds=0.0  # Will be set by caller
            )
            
            return results, metrics
            
        except Exception as e:
            self._safe_log(
                LogLevel.ERROR, 
                f"Automatic ingestion failed: {e}",
                filter_types=input_data.filter_types
            )
            
            result = IngestionResult(
                path="automatic",
                doc_type="automatic",
                status="failure",
                error=str(e),
                strategies=["automatic"],
                chunks_created=None,
                embeddings_generated=None
            )
            
            metrics = IngestionMetrics(
                total_documents=0,
                successful_ingestions=0,
                failed_ingestions=1,
                skipped_ingestions=0,
                total_chunks_created=0,
                total_embeddings_generated=0,
                processing_time_seconds=0.0
            )
            
            return [result], metrics
    
    def _resolve_filter_types(self, filter_types: List[str]) -> List[str]:
        """Resolve filter types to actual document types."""
        resolved_types = []
        
        for filter_type in filter_types:
            if filter_type == 'terraform':
                # 'terraform' means both resource and data_source
                resolved_types.extend(['resource', 'data_source'])
            elif filter_type == 'datasource':
                # Normalize 'datasource' to 'data_source' for consistency
                resolved_types.append('data_source')
            else:
                resolved_types.append(filter_type)
        
        # Remove duplicates while preserving order
        seen = set()
        unique_types = []
        for doc_type in resolved_types:
            if doc_type not in seen:
                seen.add(doc_type)
                unique_types.append(doc_type)
        
        return unique_types
    
    def _get_default_index_path(self) -> str:
        """Get the default index path for resources and data sources."""
        # Default to the AWS provider test index
        return "docs/AWS_PROVIDER_RESOURCES.md"
    
    def get_tool_health(self) -> Dict[str, Any]:
        """
        Get tool health status and diagnostics.
        
        Returns:
            Dictionary containing health information
        """
        try:
            self._safe_log(
                LogLevel.DEBUG, 
                "Health check requested for document ingestion tool"
            )
            
            health_info = {
                "status": "healthy",
                "components": {
                    "orchestrator": "initialized" if self._orchestrator_initialized else "not_initialized",
                    "configuration": "validated",
                    "pydantic_models": "loaded"
                },
                "configuration": {
                    "embedding_model": self.config.EMBEDDING_MODEL,
                    "embedding_provider": self.config.EMBEDDING_PROVIDER,
                    "embedding_dimensions": self.config.EMBEDDING_DIMENSIONS,
                    "neo4j_uri": self.config.NEO4J_URI,
                    "supported_doc_types": ["resource", "data_source", "best_practice", "readme"]
                },
                "validation": {
                    "input_schema": "pydantic",
                    "output_schema": "pydantic",
                    "models": ["DocumentInput", "IndexInput", "UnifiedInput", "IngestionOutput"]
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


def create_tf_ingestion_tool(dependencies: Dict[str, Any]) -> TFIngestionTool:
    """
    Factory function to create a TFIngestionTool instance.
    
    Args:
        dependencies: Dictionary containing required dependencies
        
    Returns:
        TFIngestionTool: Configured Terraform ingestion tool instance
        
    Raises:
        ConfigurationError: If required dependencies are missing
    """
    try:
        return TFIngestionTool(dependencies)
    except Exception as e:
        raise ConfigurationError(f"Failed to create TFIngestionTool: {str(e)}") 