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
Base Abstract Class for MCP Tools.

This module provides the foundational abstract base class for all MCP tools
in the Terraform Knowledge Graph server. It implements best practices for
RAG applications including schema validation, error handling, and provenance tracking.
"""

import json
import logging
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Dict, Any, Optional, Type, Union
from dataclasses import asdict

from pydantic import BaseModel, ValidationError
from mcp.server.fastmcp import FastMCP, Context

logger = logging.getLogger(__name__)


class BaseMCPTool(ABC):
    """
    Abstract base class for all MCP tools in the RAG application.
    
    Provides:
    - Standardized interface for tool discovery and reflection
    - Centralized error handling and logging
    - Dependency injection pattern
    - Schema validation with Pydantic
    - Provenance tracking for auditability
    - FastMCP integration support
    
    All concrete tool implementations should inherit from this class
    and implement the required abstract methods.
    """
    
    def __init__(self, dependencies: Optional[Dict[str, Any]] = None):
        """
        Initialize the base tool with optional dependencies.
        
        Args:
            dependencies: Dictionary of service dependencies (e.g., database connections, config)
        """
        self.dependencies = dependencies or {}
        self._execution_count = 0
        self._error_count = 0
    
    @property
    @abstractmethod
    def tool_name_mcp(self) -> str:
        """
        MCP tool name for registration.
        
        This should be a unique, descriptive name that follows MCP naming conventions.
        Example: "query_knowledge_graph", "get_health_status"
        
        Returns:
            str: The MCP tool name
        """
        pass
    
    @property
    @abstractmethod
    def tool_description(self) -> str:
        """
        Human-readable description for tool discovery and reflection.
        
        This description should clearly explain what the tool does,
        what inputs it expects, and what outputs it produces.
        
        Returns:
            str: Human-readable tool description
        """
        pass
    
    @property
    def input_schema(self) -> Optional[Dict[str, Any]]:
        """
        JSON Schema for input validation (optional).
        
        Override this property to provide input validation schema.
        If not provided, no validation will be performed.
        
        Returns:
            Optional[Dict[str, Any]]: JSON Schema for input validation
        """
        return None
    
    @property
    def output_schema(self) -> Optional[Dict[str, Any]]:
        """
        JSON Schema for output validation (optional).
        
        Override this property to provide output validation schema.
        If not provided, no validation will be performed.
        
        Returns:
            Optional[Dict[str, Any]]: JSON Schema for output validation
        """
        return None
    
    @property
    def tool_metadata(self) -> Dict[str, Any]:
        """
        Additional metadata for tool discovery and reflection.
        
        Returns:
            Dict[str, Any]: Tool metadata including version, tags, etc.
        """
        return {
            "version": "1.0.0",
            "category": "knowledge_graph",
            "tags": [],
            "execution_count": self._execution_count,
            "error_count": self._error_count
        }
    
    @abstractmethod
    async def execute(self, **kwargs) -> str:
        """
        Main execution method for the tool.
        
        This is the core method that implements the tool's functionality.
        All concrete tools must implement this method.
        
        Args:
            **kwargs: Tool-specific parameters
            
        Returns:
            str: JSON-formatted response with tool results
            
        Raises:
            Exception: Any exception that occurs during execution
        """
        pass
    
    def validate_input(self, **kwargs) -> None:
        """
        Validate input parameters against the input schema.
        
        This method can be overridden by subclasses to provide custom validation logic.
        By default, it validates against the input_schema if provided.
        
        Args:
            **kwargs: Input parameters to validate
            
        Raises:
            ValidationError: If input validation fails
        """
        if self.input_schema:
            # Basic validation - subclasses can override for more complex validation
            try:
                # For now, just check if required fields are present
                # In a full implementation, you'd use a JSON Schema validator
                pass
            except Exception as e:
                raise ValidationError(f"Input validation failed: {str(e)}")
    
    def validate_output(self, output: Any) -> None:
        """
        Validate output against the output schema.
        
        Args:
            output: Output to validate
            
        Raises:
            ValidationError: If output validation fails
        """
        if self.output_schema:
            # Basic validation - subclasses can override for more complex validation
            try:
                # For now, just check if output is valid JSON
                if isinstance(output, str):
                    json.loads(output)
            except Exception as e:
                raise ValidationError(f"Output validation failed: {str(e)}")
    
    def format_response(self, data: Any, success: bool = True, metadata: Optional[Dict[str, Any]] = None) -> str:
        """
        Standardized response formatting with provenance tracking.
        
        Args:
            data: The response data
            success: Whether the operation was successful
            metadata: Additional metadata to include in the response
            
        Returns:
            str: JSON-formatted response
        """
        response = {
            "success": success,
            "data": data,
            "metadata": {
                "timestamp": datetime.utcnow().isoformat(),
                "tool": self.tool_name_mcp,
                "execution_id": f"{self.tool_name_mcp}_{self._execution_count}",
                **(metadata or {})
            }
        }
        
        # Add tool metadata
        response["metadata"].update(self.tool_metadata)
        
        return json.dumps(response, indent=2, default=str)
    
    def handle_error(self, exc: Exception, context: Optional[Dict[str, Any]] = None) -> str:
        """
        Centralized error handling with logging and structured error responses.
        
        Args:
            exc: The exception that occurred
            context: Additional context about the error
            
        Returns:
            str: JSON-formatted error response
        """
        self._error_count += 1
        
        # Log the error with context
        logger.error(
            f"Error in {self.tool_name_mcp}: {str(exc)}",
            extra={
                "tool": self.tool_name_mcp,
                "error_type": type(exc).__name__,
                "context": context
            }
        )
        
        # Create structured error response
        error_data = {
            "error": str(exc),
            "error_type": type(exc).__name__,
            "context": context or {}
        }
        
        return self.format_response(error_data, success=False)
    
    def get_dependency(self, name: str) -> Any:
        """
        Get a dependency by name.
        
        Args:
            name: Name of the dependency
            
        Returns:
            The dependency object
            
        Raises:
            KeyError: If dependency is not found
        """
        if name not in self.dependencies:
            raise KeyError(f"Dependency '{name}' not found. Available: {list(self.dependencies.keys())}")
        return self.dependencies[name]
    
    def has_dependency(self, name: str) -> bool:
        """
        Check if a dependency exists.
        
        Args:
            name: Name of the dependency
            
        Returns:
            bool: True if dependency exists, False otherwise
        """
        return name in self.dependencies
    
    async def execute_with_validation(self, **kwargs) -> str:
        """
        Execute the tool with full validation and error handling.
        
        This is the main entry point that should be called by the FastMCP wrapper.
        It handles input validation, execution, output validation, and error handling.
        
        Args:
            **kwargs: Tool-specific parameters (may include 'context' for MCP context)
            
        Returns:
            str: JSON-formatted response
        """
        self._execution_count += 1
        
        try:
            # Extract context if present
            context = kwargs.pop('context', None)
            
            # Validate input
            self.validate_input(**kwargs)
            
            # Execute the tool with context
            if context is not None:
                result = await self.execute(context=context, **kwargs)
            else:
                result = await self.execute(**kwargs)
            
            # Validate output
            self.validate_output(result)
            
            # Return formatted response
            return self.format_response(result, success=True)
            
        except Exception as exc:
            return self.handle_error(exc, context={"input_params": kwargs})


def register_tool_with_fastmcp(server: FastMCP, tool_class: Type[BaseMCPTool], dependencies: Dict[str, Any]):
    """
    Register a tool class with FastMCP using the decorator pattern.
    
    This function creates a FastMCP-compatible wrapper around a tool class,
    handling validation, execution, and error handling automatically.
    
    Args:
        server: The FastMCP server instance
        tool_class: The tool class to register (must inherit from BaseMCPTool)
        dependencies: Dependencies to inject into the tool
        
    Returns:
        The registered tool function
    """
    
    tool_instance = tool_class(dependencies)
    
    @server.tool(name=tool_instance.tool_name_mcp, description=tool_instance.tool_description)
    async def tool_wrapper(context: Context = None, **kwargs) -> str:
        """
        FastMCP wrapper for the tool.
        
        This wrapper handles the integration between FastMCP and the tool class,
        providing automatic validation, error handling, and response formatting.
        """
        return await tool_instance.execute_with_validation(context=context, **kwargs)
    
    return tool_wrapper


class ToolResponse(BaseModel):
    """
    Standardized response model for MCP tools.
    
    This Pydantic model ensures consistent response structure across all tools.
    """
    success: bool
    data: Any
    metadata: Dict[str, Any]
    
    class Config:
        arbitrary_types_allowed = True


class ToolError(BaseModel):
    """
    Standardized error model for MCP tools.
    
    This Pydantic model ensures consistent error structure across all tools.
    """
    error: str
    error_type: str
    context: Optional[Dict[str, Any]] = None
