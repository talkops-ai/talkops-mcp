# Terraform Execution Tool Documentation

## Overview

The Terraform Execution Tool (`terraform_execute`) is a secure, enterprise-grade MCP tool that provides comprehensive Terraform command execution capabilities with extensive validation, security checks, and configurable parameters. It's designed to safely execute Terraform operations in controlled environments while providing detailed feedback and metadata.

## Tool Information

- **MCP Tool Name**: `terraform_execute`
- **Description**: Execute Terraform commands securely with comprehensive validation, security checks, and configurable parameters
- **Base Class**: `TFExecutionTool` extends `BaseMCPTool`

## Core Features

### 🔒 Security Features

#### Command Whitelisting
- **Allowed Commands**: `init`, `plan`, `validate`, `apply`, `destroy`
- **Validation**: Commands are validated against the whitelist before execution
- **Configuration**: Controlled via `TERRAFORM_ALLOWED_COMMANDS` config

#### Working Directory Security
- **Directory Traversal Protection**: Blocks paths containing `..`
- **Allowed Root Directories**: Only `/tmp` and `/var/tmp` by default
- **Depth Limiting**: Maximum directory depth of 10 levels
- **Existence Validation**: Ensures directory exists and is accessible
- **Blocked Directories**: System directories like `/etc`, `/usr`, `/bin` are blocked

#### Variable Security
- **Pattern Detection**: Scans for dangerous patterns in variable names and values
- **Dangerous Patterns**: Includes command injection patterns, system commands, and file operations
- **Maximum Variables**: Limited to 100 variables per execution
- **Cross-Platform**: Detects patterns for both Unix and Windows systems

#### Timeout Management
- **Default Timeout**: 300 seconds (5 minutes)
- **Maximum Timeout**: 1800 seconds (30 minutes)
- **Configurable**: Per-request timeout override
- **Process Termination**: Automatic termination on timeout

### 🛠️ Execution Features

#### Command Processing
- **Auto-Approval**: Automatic `-auto-approve` flag for `apply` and `destroy` commands
- **Variable Injection**: Secure variable passing via `-var` flags
- **Environment Variables**: AWS region support via `AWS_REGION` environment variable
- **Output Extraction**: Automatic output retrieval for successful `apply` commands

#### Output Processing
- **ANSI Code Removal**: Configurable ANSI color code stripping
- **Unicode Normalization**: Box-drawing and special character replacement
- **Output Truncation**: Maximum output length of 10,000 characters
- **Error Handling**: Comprehensive error capture and reporting

#### Metadata Collection
- **Execution Time**: Precise timing of command execution
- **Terraform Version**: Automatic version detection
- **Return Codes**: Standard process return code tracking
- **Security Status**: Validation of security checks

## Input Parameters

### Required Parameters

| Parameter | Type | Description | Validation |
|-----------|------|-------------|------------|
| `command` | string | Terraform command to execute | Must be in allowed commands list |
| `working_directory` | string | Directory containing Terraform files | Security validation, existence check |

### Optional Parameters

| Parameter | Type | Default | Description | Validation |
|-----------|------|---------|-------------|------------|
| `variables` | dict | None | Terraform variables to pass | Pattern detection, max 100 |
| `aws_region` | string | None | AWS region for execution | Format validation |
| `strip_ansi` | boolean | True | Remove ANSI color codes | None |
| `timeout` | integer | 300 | Execution timeout in seconds | 1-1800 range |

## Output Structure

### Success Response

```json
{
  "success": true,
  "data": {
    "command": "terraform plan",
    "status": "success",
    "result": {
      "command": "terraform plan",
      "status": "success",
      "return_code": 0,
      "stdout": "Terraform will perform the following actions...",
      "stderr": "",
      "working_directory": "/tmp/terraform-project",
      "error_message": null,
      "outputs": null,
      "execution_time": 2.45
    },
    "metadata": {
      "terraform_version": "1.5.0",
      "aws_region": "us-west-2",
      "variables_count": 2,
      "outputs_count": 0,
      "security_checks_passed": true
    },
    "configuration": {
      "terraform_binary_path": "terraform",
      "allowed_commands": ["init", "plan", "validate", "apply", "destroy"],
      "default_timeout": 300,
      "max_timeout": 1800,
      "security_enabled": true
    }
  },
  "metadata": {
    "timestamp": "2025-08-01T13:21:14.246401",
    "tool": "terraform_execute",
    "execution_id": "terraform_execute_0",
    "version": "1.0.0"
  }
}
```

### Error Response

```json
{
  "success": false,
  "data": {
    "command": "terraform plan",
    "status": "error",
    "result": {
      "command": "terraform plan",
      "status": "error",
      "return_code": 1,
      "stdout": "",
      "stderr": "Error: No configuration files",
      "working_directory": "/tmp",
      "error_message": "Command failed with return code 1",
      "outputs": null,
      "execution_time": 0.129
    },
    "metadata": {
      "terraform_version": "1.12.2",
      "aws_region": null,
      "variables_count": 0,
      "outputs_count": 0,
      "security_checks_passed": true
    },
    "configuration": {
      "terraform_binary_path": "terraform",
      "allowed_commands": ["init", "plan", "validate", "apply", "destroy"],
      "default_timeout": 300,
      "max_timeout": 1800,
      "security_enabled": true
    }
  },
  "metadata": {
    "timestamp": "2025-08-01T13:21:14.246401",
    "tool": "terraform_execute",
    "execution_id": "terraform_execute_0",
    "version": "1.0.0"
  }
}
```

## Usage Examples

### Basic Terraform Init

**User Query**: "Can you initialize terraform in this directory - /tmp/terraform-project"

**MCP Tool Invocation**:
```python
# The AI agent automatically calls the terraform_execute tool
result = await terraform_execute(
    command="init",
    working_directory="/tmp/terraform-project"
)
```

**Response**: The tool initializes Terraform in the specified directory and returns execution status.

### Terraform Plan with Variables

**User Query**: "Can you run terraform plan in /tmp/terraform-project with environment=production, instance_count=3, instance_type=t3.micro, and use AWS region us-west-2"

**MCP Tool Invocation**:
```python
# The AI agent automatically calls the terraform_execute tool
result = await terraform_execute(
    command="plan",
    working_directory="/tmp/terraform-project",
    variables={
        "environment": "production",
        "instance_count": "3",
        "instance_type": "t3.micro"
    },
    aws_region="us-west-2",
    timeout=600  # 10 minutes
)
```

**Response**: The tool executes terraform plan with the specified variables and returns the plan output.

### Terraform Apply with Auto-Approval

**User Query**: "Apply the terraform configuration in /tmp/terraform-project with environment=production and clean up the output by removing color codes"

**MCP Tool Invocation**:
```python
# The AI agent automatically calls the terraform_execute tool
result = await terraform_execute(
    command="apply",
    working_directory="/tmp/terraform-project",
    variables={
        "environment": "production"
    },
    strip_ansi=True  # Remove color codes from output
)
```

**Response**: The tool applies the Terraform configuration with auto-approval and returns the apply results.

### Terraform Validate

**User Query**: "Validate the terraform configuration in /tmp/terraform-project"

**MCP Tool Invocation**:
```python
# The AI agent automatically calls the terraform_execute tool
result = await terraform_execute(
    command="validate",
    working_directory="/tmp/terraform-project"
)
```

**Response**: The tool validates the Terraform configuration and returns validation results.

### Terraform Destroy

**User Query**: "Destroy the infrastructure in /tmp/terraform-project with environment=production"

**MCP Tool Invocation**:
```python
# The AI agent automatically calls the terraform_execute tool
result = await terraform_execute(
    command="destroy",
    working_directory="/tmp/terraform-project",
    variables={
        "environment": "production"
    }
)
```

**Response**: The tool destroys the infrastructure with auto-approval and returns the destroy results.

## Security Patterns Detected

The tool scans for the following dangerous patterns in variables:

### Command Injection Patterns
- `|`, `;`, `&`, `&&`, `||`, `>`, `>>`, `<`, `` ` ``, `$(`
- `--`, `rm`, `mv`, `cp`, `/bin/`, `/usr/bin/`, `../`, `./`

### System Commands
- `sudo`, `chmod`, `chown`, `su`, `bash`, `sh`, `zsh`
- `curl`, `wget`, `ssh`, `scp`, `eval`, `exec`, `source`

### Windows Commands
- `cmd`, `powershell`, `pwsh`, `net`, `reg`, `runas`
- `del`, `rmdir`, `start`, `taskkill`, `sc`, `schtasks`, `wmic`
- `%SYSTEMROOT%`, `%WINDIR%`, `.bat`, `.cmd`, `.ps1`

## Configuration

### Required Configuration

| Config Key | Default | Description |
|------------|---------|-------------|
| `TERRAFORM_BINARY_PATH` | "terraform" | Path to Terraform binary |
| `TERRAFORM_ALLOWED_COMMANDS` | ["init", "plan", "validate", "apply", "destroy"] | Whitelist of allowed commands |
| `TERRAFORM_DEFAULT_TIMEOUT` | 300 | Default execution timeout in seconds |
| `TERRAFORM_MAX_TIMEOUT` | 1800 | Maximum execution timeout in seconds |

### Security Configuration

| Config Key | Default | Description |
|------------|---------|-------------|
| `TERRAFORM_SECURITY_ENABLED` | True | Enable security features |
| `TERRAFORM_DANGEROUS_PATTERNS_ENABLED` | True | Enable pattern detection |
| `TERRAFORM_WORKING_DIRECTORY_VALIDATION` | True | Enable directory validation |
| `TERRAFORM_MAX_WORKING_DIRECTORY_DEPTH` | 10 | Maximum directory depth |
| `TERRAFORM_ALLOWED_WORKING_DIRECTORIES` | ["/tmp", "/var/tmp"] | Allowed root directories |
| `TERRAFORM_BLOCKED_WORKING_DIRECTORIES` | ["/etc", "/usr", "/bin", "/sbin", "/boot", "/dev", "/proc", "/sys"] | Blocked directories |

### Execution Configuration

| Config Key | Default | Description |
|------------|---------|-------------|
| `TERRAFORM_AUTO_APPROVE_COMMANDS` | ["apply", "destroy"] | Commands that get auto-approval |
| `TERRAFORM_VARIABLE_COMMANDS` | ["plan", "apply", "destroy"] | Commands that accept variables |
| `TERRAFORM_OUTPUT_COMMANDS` | ["apply"] | Commands that generate outputs |
| `TERRAFORM_MAX_VARIABLES` | 100 | Maximum number of variables |
| `TERRAFORM_MAX_OUTPUT_LENGTH` | 10000 | Maximum output length |

## Best Practices

### Security
1. **Always validate working directories** before execution
2. **Use specific timeouts** for long-running operations
3. **Review variables** for dangerous patterns
4. **Monitor execution logs** for security events

### Performance
1. **Set appropriate timeouts** based on operation complexity
2. **Use output truncation** for large outputs
3. **Enable ANSI stripping** for cleaner output processing
4. **Monitor execution times** for optimization

### Error Handling
1. **Check return codes** for operation success
2. **Parse error messages** for debugging
3. **Use metadata** for operation tracking
4. **Implement retry logic** for transient failures

## Limitations

1. **Command Restrictions**: Only supports whitelisted Terraform commands
2. **Directory Restrictions**: Limited to safe working directories
3. **Variable Limits**: Maximum 100 variables per execution
4. **Output Limits**: Maximum 10,000 character output length
5. **Timeout Limits**: Maximum 30-minute execution timeout
6. **Platform Dependencies**: Requires Terraform CLI to be installed

## Troubleshooting

### Common Issues

1. **"No configuration files" Error**
   - Ensure working directory contains `.tf` files
   - Check directory permissions

2. **"Command not found" Error**
   - Verify Terraform is installed and in PATH
   - Check `TERRAFORM_BINARY_PATH` configuration

3. **"Permission denied" Error**
   - Check working directory permissions
   - Verify user has access to Terraform binary

4. **"Timeout exceeded" Error**
   - Increase timeout for complex operations
   - Check network connectivity for remote state

5. **"Security violation" Error**
   - Review variables for dangerous patterns
   - Use safe variable names and values
