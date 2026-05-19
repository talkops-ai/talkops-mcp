"""Terraform command execution tool — MCP registration layer.

Wraps the existing TFExecutionTool execution logic in a Traefik-style
BaseTool class with @mcp.tool() registration and pydantic.Field
parameter annotations.
"""

import logging
from typing import Any, Dict, Optional

from pydantic import Field
from fastmcp import Context

from terraform_mcp_server.tools.base import BaseTool
from terraform_mcp_server.core.tools.tf_execution_tool import TFExecutionTool

logger = logging.getLogger(__name__)


class TerraformExecutionTools(BaseTool):
    """MCP tool registration for Terraform command execution.
    
    Delegates execution to the existing TFExecutionTool in core/tools/,
    preserving the public MCP tool name and JSON response contract.
    
    Can be gated by server_config.allow_dangerous_execution.
    """
    
    def register(self, mcp_instance) -> None:
        """Register terraform_execute with the MCP instance."""
        server_config = self.server_config
        
        @mcp_instance.tool()
        async def terraform_execute(
            command: str = Field(
                description=(
                    "Terraform command to execute: "
                    "init, plan, validate, apply, destroy"
                ),
            ),
            working_directory: str = Field(
                description="Directory containing Terraform configuration files",
            ),
            variables: Optional[Dict[str, str]] = Field(
                default=None,
                description="Terraform variables to pass (key-value pairs)",
            ),
            aws_region: Optional[str] = Field(
                default=None,
                description="AWS region to use for execution",
            ),
            strip_ansi: bool = Field(
                default=True,
                description="Strip ANSI color codes from command output",
            ),
            timeout: Optional[int] = Field(
                default=None,
                ge=1,
                le=1800,
                description="Execution timeout in seconds (1-1800)",
            ),
            context: Context = None,
        ) -> str:
            """Execute Terraform commands securely with validation.
            
            Provides secure execution of Terraform commands with
            comprehensive validation, security checks, configurable
            timeouts, ANSI output cleaning, and AWS region support.
            
            Dangerous commands (apply, destroy) require the
            MCP_ALLOW_DANGEROUS_EXECUTION flag to be enabled.
            """
            # Gate dangerous operations
            dangerous_commands = {'apply', 'destroy'}
            if (
                command in dangerous_commands
                and server_config is not None
                and not server_config.allow_dangerous_execution
            ):
                import json
                return json.dumps({
                    "success": False,
                    "error": (
                        f"Command '{command}' is blocked. Set "
                        "MCP_ALLOW_DANGEROUS_EXECUTION=true to enable."
                    ),
                }, indent=2)
            
            execution_tool = TFExecutionTool({})
            
            return await execution_tool.execute(
                command=command,
                working_directory=working_directory,
                variables=variables,
                aws_region=aws_region,
                strip_ansi=strip_ansi,
                timeout=timeout,
                context=context,
            )
