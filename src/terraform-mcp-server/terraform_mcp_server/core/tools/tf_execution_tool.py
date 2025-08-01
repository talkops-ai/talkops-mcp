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
Terraform Command Execution Tool Implementation.

This module implements the terraform_execution tool that provides secure
Terraform command execution capabilities with comprehensive validation,
security checks, and configurable parameters.
"""
import json
import os
import re
import subprocess
from typing import Dict, Any, Optional, List
from datetime import datetime
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

class TerraformExecutionInput(BaseModel):
    """
    Input model for Terraform execution requests.
    
    Validates and structures input parameters for Terraform command execution.
    """
    command: str = Field(
        ..., 
        description="The Terraform command to execute (init, plan, validate, apply, destroy)",
        min_length=1,
        max_length=20
    )
    working_directory: str = Field(
        ..., 
        description="Directory containing Terraform configuration files",
        min_length=1,
        max_length=500
    )
    variables: Optional[Dict[str, str]] = Field(
        default=None,
        description="Optional dictionary of Terraform variables to pass"
    )
    aws_region: Optional[str] = Field(
        default=None,
        description="Optional AWS region to use for the execution"
    )
    strip_ansi: bool = Field(
        default=True,
        description="Whether to strip ANSI color codes from command output"
    )
    timeout: Optional[int] = Field(
        default=None,
        ge=1,
        le=1800,
        description="Command execution timeout in seconds (1-1800)"
    )
    
    @field_validator('command')
    @classmethod
    def validate_command(cls, v):
        """Validate Terraform command is allowed."""
        allowed_commands = Config().TERRAFORM_ALLOWED_COMMANDS
        if v not in allowed_commands:
            raise ValueError(f"Command must be one of: {', '.join(allowed_commands)}")
        return v
    
    @field_validator('working_directory')
    @classmethod
    def validate_working_directory(cls, v):
        """Validate working directory path."""
        if not v or not v.strip():
            raise ValueError("Working directory cannot be empty")
        
        # Check for directory traversal attempts
        if '..' in v:
            raise ValueError("Invalid working directory path: directory traversal not allowed")
        
        # Allow specific root directories that are safe (from config)
        config = Config()
        allowed_root_dirs = config.TERRAFORM_ALLOWED_WORKING_DIRECTORIES
        if v.startswith('/') and v not in allowed_root_dirs:
            raise ValueError(f"Invalid working directory path: {v}. Only {', '.join(allowed_root_dirs)} are allowed as root directories")
        
        return v.strip()
    
    @field_validator('variables')
    @classmethod
    def validate_variables(cls, v):
        """Validate Terraform variables."""
        if v is not None:
            max_vars = Config().TERRAFORM_MAX_VARIABLES
            if len(v) > max_vars:
                raise ValueError(f"Too many variables. Maximum allowed: {max_vars}")
            
            # Check for dangerous patterns in variable names and values
            if Config().TERRAFORM_DANGEROUS_PATTERNS_ENABLED:
                dangerous_patterns = cls._get_dangerous_patterns()
                for var_name, var_value in v.items():
                    for pattern in dangerous_patterns:
                        if pattern in str(var_value) or pattern in str(var_name):
                            raise ValueError(f"Security violation: Dangerous pattern '{pattern}' detected in variable '{var_name}'")
        return v
    
    @field_validator('aws_region')
    @classmethod
    def validate_aws_region(cls, v):
        """Validate AWS region format."""
        if v is not None:
            # Basic AWS region validation
            if not re.match(r'^[a-z0-9-]+$', v):
                raise ValueError("Invalid AWS region format")
        return v
    
    @staticmethod
    def _get_dangerous_patterns() -> List[str]:
        """Get dangerous patterns for command injection detection."""
        return [
            '|', ';', '&', '&&', '||', '>', '>>', '<', '`', '$(',
            '--', 'rm', 'mv', 'cp', '/bin/', '/usr/bin/', '../', './',
            'sudo', 'chmod', 'chown', 'su', 'bash', 'sh', 'zsh',
            'curl', 'wget', 'ssh', 'scp', 'eval', 'exec', 'source',
            'cmd', 'powershell', 'pwsh', 'net', 'reg', 'runas',
            'del', 'rmdir', 'start', 'taskkill', 'sc', 'schtasks', 'wmic',
            '%SYSTEMROOT%', '%WINDIR%', '.bat', '.cmd', '.ps1'
        ]


class ExecutionResult(BaseModel):
    """
    Model for Terraform execution results.
    
    Represents the output and status of a Terraform command execution.
    """
    command: str = Field(..., description="The Terraform command that was executed")
    status: str = Field(..., description="Execution status (success/error)")
    return_code: Optional[int] = Field(None, description="The command's return code")
    stdout: Optional[str] = Field(None, description="Standard output from the command")
    stderr: str = Field(default="", description="Standard error output from the command")
    working_directory: str = Field(..., description="Directory where the command was executed")
    error_message: Optional[str] = Field(None, description="Error message if execution failed")
    outputs: Optional[Dict[str, Any]] = Field(None, description="Terraform outputs (for apply command)")
    execution_time: Optional[float] = Field(None, description="Execution time in seconds")
    
    @field_validator('status')
    @classmethod
    def validate_status(cls, v):
        """Validate status is valid."""
        if v not in ['success', 'error']:
            raise ValueError("Status must be 'success' or 'error'")
        return v


class ExecutionMetadata(BaseModel):
    """
    Model for execution metadata.
    
    Provides additional information about the execution context.
    """
    terraform_version: Optional[str] = Field(None, description="Terraform version used")
    aws_region: Optional[str] = Field(None, description="AWS region used")
    variables_count: int = Field(default=0, description="Number of variables passed")
    outputs_count: int = Field(default=0, description="Number of outputs returned")
    security_checks_passed: bool = Field(default=True, description="Whether security checks passed")


class TerraformExecutionOutput(BaseModel):
    """
    Output model for Terraform execution responses.
    
    Provides a structured response with execution results and metadata.
    """
    command: str = Field(..., description="Original command executed")
    status: str = Field(..., description="Execution status")
    result: ExecutionResult = Field(..., description="Execution result details")
    metadata: ExecutionMetadata = Field(..., description="Execution metadata")
    configuration: Dict[str, Any] = Field(..., description="Configuration used")


# =============================================================================
# Terraform Execution Tool Implementation
# =============================================================================

class TFExecutionTool(BaseMCPTool):
    """
    Terraform Command Execution Tool for secure Terraform operations.
    
    This tool provides secure execution of Terraform commands with comprehensive
    validation, security checks, and configurable parameters. It supports all
    standard Terraform commands with proper error handling and output processing.
    
    Features:
    - Pydantic input/output validation
    - Security pattern detection
    - Configurable timeouts and limits
    - ANSI output cleaning
    - AWS region support
    - Variable validation
    - Output extraction for apply commands
    - Comprehensive error handling
    - Context-aware logging with request IDs
    """
    
    def __init__(self, dependencies: Optional[Dict[str, Any]] = None):
        super().__init__(dependencies)
        self.config = Config()
        self.context = None  # Will be set during request execution
        self._validate_config()
    
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
        """Validate required configuration for Terraform execution."""
        required_configs = [
            'TERRAFORM_BINARY_PATH', 'TERRAFORM_ALLOWED_COMMANDS',
            'TERRAFORM_DEFAULT_TIMEOUT', 'TERRAFORM_MAX_TIMEOUT'
        ]
        
        missing_configs = []
        for config_name in required_configs:
            if not hasattr(self.config, config_name) or not getattr(self.config, config_name):
                missing_configs.append(config_name)
        
        if missing_configs:
            self._safe_log(
                LogLevel.ERROR, 
                f"Missing required configuration for Terraform execution: {missing_configs}"
            )
            raise ConfigurationError(
                f"Missing required configuration for Terraform execution: {missing_configs}"
            )
    
    @property
    def tool_name_mcp(self) -> str:
        """Return the MCP tool name."""
        return "terraform_execute"
    
    @property
    def tool_description(self) -> str:
        """Return the tool description for MCP registration."""
        return "Execute Terraform commands securely with comprehensive validation, security checks, and configurable parameters"
    
    @property
    def input_schema(self) -> Dict[str, Any]:
        """Define input schema for validation using Pydantic model."""
        return TerraformExecutionInput.schema()
    
    @property
    def output_schema(self) -> Dict[str, Any]:
        """Define output schema for validation using Pydantic model."""
        return TerraformExecutionOutput.schema()
    
    async def execute(self, command: str, working_directory: str, variables: Optional[Dict[str, str]] = None, 
                     aws_region: Optional[str] = None, strip_ansi: bool = True, timeout: Optional[int] = None,
                     context: Optional[Context] = None) -> str:
        """
        Execute Terraform command with comprehensive validation and security checks.
        
        Args:
            command: Terraform command to execute
            working_directory: Directory containing Terraform files
            variables: Optional Terraform variables
            aws_region: Optional AWS region
            strip_ansi: Whether to strip ANSI codes from output
            timeout: Command execution timeout in seconds
            context: MCP context for logging
        
        Returns:
            JSON-formatted string containing validated execution results
        """
        try:
            # Set context for this request if provided
            if context is not None:
                self.context = context
            
            # Validate input using Pydantic model
            input_data = TerraformExecutionInput(
                command=command,
                working_directory=working_directory,
                variables=variables,
                aws_region=aws_region,
                strip_ansi=strip_ansi,
                timeout=timeout
            )
            
            self._safe_log(
                LogLevel.INFO, 
                f"Executing Terraform command: {input_data.command} in {input_data.working_directory}"
            )
            
            # Perform additional security validations
            self._validate_working_directory_security(input_data.working_directory)
            
            # Execute the Terraform command
            result = self._execute_terraform_command(input_data)
            
            # Create validated output using Pydantic model
            output_data = TerraformExecutionOutput(
                command=input_data.command,
                status=result.status,
                result=result,
                metadata=ExecutionMetadata(
                    terraform_version=self._get_terraform_version(),
                    aws_region=input_data.aws_region,
                    variables_count=len(input_data.variables) if input_data.variables else 0,
                    outputs_count=len(result.outputs) if result.outputs else 0,
                    security_checks_passed=True
                ),
                configuration={
                    "terraform_binary_path": self.config.TERRAFORM_BINARY_PATH,
                    "allowed_commands": self.config.TERRAFORM_ALLOWED_COMMANDS,
                    "default_timeout": self.config.TERRAFORM_DEFAULT_TIMEOUT,
                    "max_timeout": self.config.TERRAFORM_MAX_TIMEOUT,
                    "security_enabled": self.config.TERRAFORM_SECURITY_ENABLED
                }
            )
            
            self._safe_log(
                LogLevel.INFO, 
                f"Terraform command completed: {result.status}, return_code={result.return_code}"
            )
            
            return self.format_response(output_data.model_dump(), success=True)
            
        except Exception as e:
            self._safe_log(
                LogLevel.ERROR, 
                f"Terraform execution failed: {e}",
                command=command,
                working_directory=working_directory
            )
            return self.handle_error(e, context={"command": command, "working_directory": working_directory})
    
    def _validate_working_directory_security(self, working_directory: str) -> None:
        """Validate working directory for security concerns."""
        if not self.config.TERRAFORM_WORKING_DIRECTORY_VALIDATION:
            return
        
        self._safe_log(
            LogLevel.DEBUG, 
            f"Validating working directory security: {working_directory}",
            blocked_dirs=self.config.TERRAFORM_BLOCKED_WORKING_DIRECTORIES,
            allowed_dirs=self.config.TERRAFORM_ALLOWED_WORKING_DIRECTORIES
        )
        
        # Check against blocked directories (exact match or subdirectory)
        for blocked_dir in self.config.TERRAFORM_BLOCKED_WORKING_DIRECTORIES:
            if (working_directory == blocked_dir or 
                working_directory.startswith(blocked_dir + os.sep)):
                self._safe_log(
                    LogLevel.WARNING, 
                    f"Working directory blocked: {working_directory} matches blocked pattern: {blocked_dir}"
                )
                raise ValueError(f"Working directory '{working_directory}' is blocked for security reasons")
        
        # Check directory depth to prevent traversal attacks
        depth = working_directory.count(os.sep)
        if depth > self.config.TERRAFORM_MAX_WORKING_DIRECTORY_DEPTH:
            raise ValueError(f"Working directory path too deep: {depth} levels (max: {self.config.TERRAFORM_MAX_WORKING_DIRECTORY_DEPTH})")
        
        # Check if directory exists and is accessible
        if not os.path.exists(working_directory):
            raise ValueError(f"Working directory does not exist: {working_directory}")
        
        if not os.path.isdir(working_directory):
            raise ValueError(f"Working directory is not a directory: {working_directory}")
        
        self._safe_log(
            LogLevel.DEBUG, 
            f"Working directory security validation passed: {working_directory}"
        )
    
    def _execute_terraform_command(self, input_data: TerraformExecutionInput) -> ExecutionResult:
        """
        Execute the actual Terraform command with proper error handling.
        
        Args:
            input_data: Validated input data
            
        Returns:
            ExecutionResult with command output and status
        """
        start_time = datetime.now()
        
        # Set environment variables
        env = os.environ.copy()
        if input_data.aws_region:
            env['AWS_REGION'] = input_data.aws_region
        
        # Build the command
        cmd = [self.config.TERRAFORM_BINARY_PATH, input_data.command]
        
        # Add auto-approve flag for applicable commands
        if input_data.command in self.config.TERRAFORM_AUTO_APPROVE_COMMANDS:
            self._safe_log(
                LogLevel.INFO, 
                f"Adding -auto-approve flag to {input_data.command} command"
            )
            cmd.append('-auto-approve')
        
        # Add variables for applicable commands
        if (input_data.command in self.config.TERRAFORM_VARIABLE_COMMANDS and 
            input_data.variables):
            self._safe_log(
                LogLevel.INFO, 
                f"Adding {len(input_data.variables)} variables to {input_data.command} command"
            )
            for key, value in input_data.variables.items():
                cmd.append(f'-var={key}={value}')
        
        # Set timeout
        timeout = input_data.timeout or self.config.TERRAFORM_DEFAULT_TIMEOUT
        timeout = min(timeout, self.config.TERRAFORM_MAX_TIMEOUT)
        
        # Execute command
        try:
            process = subprocess.run(
                cmd, 
                cwd=input_data.working_directory, 
                capture_output=True, 
                text=True, 
                env=env,
                timeout=timeout
            )
            
            # Calculate execution time
            execution_time = (datetime.now() - start_time).total_seconds()
            
            # Prepare output
            stdout = process.stdout
            stderr = process.stderr if process.stderr else ''
            
            # Clean output if requested
            if input_data.strip_ansi:
                stdout = self._clean_output_text(stdout)
                stderr = self._clean_output_text(stderr)
            
            # Truncate output if too long
            max_length = self.config.TERRAFORM_MAX_OUTPUT_LENGTH
            if stdout and len(stdout) > max_length:
                stdout = stdout[:max_length] + f"\n[Output truncated - max length: {max_length}]"
            if stderr and len(stderr) > max_length:
                stderr = stderr[:max_length] + f"\n[Error output truncated - max length: {max_length}]"
            
            # Create result
            result = ExecutionResult(
                command=f"terraform {input_data.command}",
                status='success' if process.returncode == 0 else 'error',
                return_code=process.returncode,
                stdout=stdout,
                stderr=stderr,
                working_directory=input_data.working_directory,
                error_message=None if process.returncode == 0 else f"Command failed with return code {process.returncode}",
                outputs=None,
                execution_time=execution_time
            )
            
            # Get outputs for successful apply commands
            if (input_data.command in self.config.TERRAFORM_OUTPUT_COMMANDS and 
                process.returncode == 0):
                result.outputs = self._get_terraform_outputs(input_data.working_directory, env, input_data.strip_ansi)
            
            return result
            
        except subprocess.TimeoutExpired:
            execution_time = (datetime.now() - start_time).total_seconds()
            return ExecutionResult(
                command=f"terraform {input_data.command}",
                status='error',
                return_code=None,
                stdout=None,
                stderr=f"Command timed out after {timeout} seconds",
                working_directory=input_data.working_directory,
                error_message=f"Command execution timed out after {timeout} seconds",
                outputs=None,
                execution_time=execution_time
            )
        except Exception as e:
            execution_time = (datetime.now() - start_time).total_seconds()
            return ExecutionResult(
                command=f"terraform {input_data.command}",
                status='error',
                return_code=None,
                stdout=None,
                stderr=str(e),
                working_directory=input_data.working_directory,
                error_message=str(e),
                outputs=None,
                execution_time=execution_time
            )
    
    def _clean_output_text(self, text: str) -> str:
        """
        Clean output text by removing or replacing problematic Unicode characters.
        
        Args:
            text: The text to clean
            
        Returns:
            Cleaned text with ASCII-friendly replacements
        """
        if not text:
            return text
        
        # Remove ANSI escape sequences
        ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
        text = ansi_escape.sub('', text)
        
        # Remove control characters (except common whitespace)
        control_chars = re.compile(r'[\x00-\x08\x0B-\x0C\x0E-\x1F\x7F-\x9F]')
        text = control_chars.sub('', text)
        
        # Replace HTML entities
        html_entities = {
            '-&gt;': '->', '&lt;': '<', '&gt;': '>', '&amp;': '&'
        }
        for entity, replacement in html_entities.items():
            text = text.replace(entity, replacement)
        
        # Replace box-drawing and special Unicode characters
        unicode_chars = {
            '\u2500': '-', '\u2502': '|', '\u2514': '+', '\u2518': '+',
            '\u2551': '|', '\u2550': '-', '\u2554': '+', '\u2557': '+',
            '\u255a': '+', '\u255d': '+', '\u256c': '+', '\u2588': '#',
            '\u25cf': '*', '\u2574': '-', '\u2576': '-', '\u2577': '|', '\u2575': '|'
        }
        for char, replacement in unicode_chars.items():
            text = text.replace(char, replacement)
        
        return text
    
    def _get_terraform_outputs(self, working_directory: str, env: Dict[str, str], strip_ansi: bool) -> Optional[Dict[str, Any]]:
        """
        Get Terraform outputs for successful apply commands.
        
        Args:
            working_directory: Directory containing Terraform files
            env: Environment variables
            strip_ansi: Whether to strip ANSI codes
            
        Returns:
            Dictionary of Terraform outputs or None if failed
        """
        try:
            self._safe_log(LogLevel.INFO, "Getting Terraform outputs")
            
            output_process = subprocess.run(
                [self.config.TERRAFORM_BINARY_PATH, 'output', '-json'],
                cwd=working_directory,
                capture_output=True,
                text=True,
                env=env,
                timeout=30  # Shorter timeout for output command
            )
            
            if output_process.returncode == 0 and output_process.stdout:
                output_stdout = output_process.stdout
                if strip_ansi:
                    output_stdout = self._clean_output_text(output_stdout)
                
                # Parse JSON output
                raw_outputs = json.loads(output_stdout)
                
                # Process outputs to extract values
                processed_outputs = {}
                for key, value in raw_outputs.items():
                    if isinstance(value, dict) and 'value' in value:
                        processed_outputs[key] = value['value']
                    else:
                        processed_outputs[key] = value
                
                self._safe_log(LogLevel.INFO, f"Extracted {len(processed_outputs)} Terraform outputs")
                return processed_outputs
                
        except Exception as e:
            self._safe_log(LogLevel.WARNING, f"Failed to get Terraform outputs: {e}")
        
        return None
    
    def _get_terraform_version(self) -> Optional[str]:
        """Get Terraform version for metadata."""
        try:
            result = subprocess.run(
                [self.config.TERRAFORM_BINARY_PATH, 'version'],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                # Extract version from output (e.g., "Terraform v1.5.0")
                version_match = re.search(r'Terraform v([\d.]+)', result.stdout)
                if version_match:
                    return version_match.group(1)
        except Exception:
            pass
        return None
    
    def get_tool_health(self) -> Dict[str, Any]:
        """
        Get tool health status and diagnostics.
        
        Returns:
            Dictionary containing health information
        """
        try:
            self._safe_log(LogLevel.DEBUG, "Health check requested for Terraform execution tool")
            
            # Check if Terraform binary is available
            terraform_available = False
            terraform_version = None
            try:
                result = subprocess.run(
                    [self.config.TERRAFORM_BINARY_PATH, 'version'],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                terraform_available = result.returncode == 0
                if terraform_available:
                    version_match = re.search(r'Terraform v([\d.]+)', result.stdout)
                    if version_match:
                        terraform_version = version_match.group(1)
            except Exception:
                pass
            
            health_info = {
                "status": "healthy" if terraform_available else "unhealthy",
                "components": {
                    "terraform_binary": "available" if terraform_available else "unavailable",
                    "configuration": "validated",
                    "security_checks": "enabled" if self.config.TERRAFORM_SECURITY_ENABLED else "disabled",
                    "pydantic_models": "loaded"
                },
                "configuration": {
                    "terraform_binary_path": self.config.TERRAFORM_BINARY_PATH,
                    "allowed_commands": self.config.TERRAFORM_ALLOWED_COMMANDS,
                    "default_timeout": self.config.TERRAFORM_DEFAULT_TIMEOUT,
                    "max_timeout": self.config.TERRAFORM_MAX_TIMEOUT,
                    "security_enabled": self.config.TERRAFORM_SECURITY_ENABLED
                },
                "terraform": {
                    "available": terraform_available,
                    "version": terraform_version
                },
                "validation": {
                    "input_schema": "pydantic",
                    "output_schema": "pydantic",
                    "models": ["TerraformExecutionInput", "TerraformExecutionOutput", "ExecutionResult"]
                }
            }
            
            self._safe_log(LogLevel.INFO, "Health check completed successfully")
            return health_info
            
        except Exception as e:
            self._safe_log(LogLevel.ERROR, f"Health check failed: {e}")
            return {
                "status": "unhealthy",
                "error": str(e),
                "components": {},
                "configuration": {},
                "terraform": {"available": False, "version": None},
                "validation": {}
            }


def create_tf_execution_tool(dependencies: Dict[str, Any]) -> TFExecutionTool:
    """
    Factory function to create a TFExecutionTool instance.
    
    Args:
        dependencies: Dictionary containing required dependencies
        
    Returns:
        TFExecutionTool: Configured Terraform execution tool instance
        
    Raises:
        ConfigurationError: If required dependencies are missing
    """
    try:
        return TFExecutionTool(dependencies)
    except Exception as e:
        raise ConfigurationError(f"Failed to create TFExecutionTool: {str(e)}") 