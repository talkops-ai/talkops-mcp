# ArgoCD MCP Server

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![MCP](https://img.shields.io/badge/MCP-Model%20Context%20Protocol-green.svg)](https://modelcontextprotocol.io/)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![ArgoCD](https://img.shields.io/badge/ArgoCD-v2.x-blue.svg)](https://argo-cd.readthedocs.io/)
[![Discord](https://img.shields.io/badge/Discord-Join-5865F2?logo=discord&logoColor=white)](https://discord.gg/tSN2Qn9uM8)

A comprehensive **Model Context Protocol (MCP)** server for managing Kubernetes applications via ArgoCD using GitOps principles. Designed for AI assistants to perform secure, production-grade ArgoCD operations with deep observability, validation, and guided workflows.

---

## ✨ Features

### 🎯 Application Management
- Create, update, and delete ArgoCD applications
- List applications across clusters with health and sync status
- Get detailed application information including resource breakdown
- Validate application configurations before deployment
- View application events and audit trails

### 🚀 Deployment & Operations
- Sync applications to desired state (with dry-run support)
- Get deployment diffs to preview changes
- Monitor sync operations in real-time
- Rollback to previous versions with impact analysis
- Prune orphaned resources
- Hard and soft refresh operations
- Cancel ongoing deployments

### 📦 Repository Management
- Onboard GitHub repositories via HTTPS or SSH
- Validate repository connections before onboarding
- List and manage registered repositories
- Delete repositories from ArgoCD
- Generate Kubernetes secret manifests for disaster recovery
- Secure credential handling (never exposed to LLM)

### 🏢 Project Management (Multi-Tenancy)
- Create ArgoCD projects with RBAC policies
- Define source repository patterns (wildcards supported)
- Configure destination clusters and namespaces
- Whitelist/blacklist cluster and namespace resources
- Generate AppProject YAML manifests
- Manage project lifecycle

### 🔍 Monitoring & Debugging
- Real-time application health metrics
- Smart log analysis with automatic error detection
- Cluster-wide health overview
- Active sync operation tracking  
- Deployment event streams
- Comprehensive troubleshooting workflows

### 📚 Guided Workflows (Prompts)
- **Repository onboarding**: Step-by-step GitHub integration
- **Full deployment**: End-to-end from repo to running app
- **Debugging**: Automated issue diagnosis with recommendations
- **Rollback**: Guided recovery with history and impact preview
- **Project setup**: Multi-tenancy configuration assistant  
- **Deployment validation**: Comprehensive post-deployment checks

### 🔒 Security & Safety
- **Read-only mode**: Disable all mutating operations
- **Credential isolation**: Secrets never passed to LLM
- **Write access control**: Granular operation permissions
- **TLS verification**: Secure ArgoCD connections
- **Environment variable security**: Best practices enforced
- **Dry-run support**: Preview changes before applying

---

## 📖 User Guide

**New to the ArgoCD MCP Server? Start here!**

See the **[Complete User Guide](./USER_GUIDE.md)** for detailed examples of how to interact with the server using natural language.

### What's in the User Guide?

- **🎯 Real User Queries**: Learn what to ask the AI agent
- **🤖 Complete Workflows**: See step-by-step what happens behind the scenes
- **📊 Example Outputs**: Know exactly what responses to expect
- **⏱️ Time Estimates**: Understand how long operations take

### Quick Examples from the Guide:

**Deploy an Application:**
```
You: "Deploy my application from https://github.com/myorg/myapp to production cluster"

Agent: Uses full_application_deployment prompt
→ Onboards repository (if needed)
→ Creates ArgoCD application
→ Shows deployment preview
→ Executes deployment
→ Monitors progress
→ Validates success

Time: ~1-2 minutes | Requires: 1 confirmation
```

**Debug an Issue:**
```
You: "My app 'payment-service' is not working in production, help me debug it"

Agent: Uses debug_application_issues prompt
→ Analyzes application status (1/3 pods failing)
→ Detects errors in logs (15 database connection errors)
→ Reviews events (CrashLoopBackOff pattern)
→ Identifies root cause (database connectivity)
→ Provides 4 immediate fixes + 4 preventive measures

Time: ~15 seconds | Fully automated
```

**Rollback a Deployment:**
```
You: "URGENT: Latest deployment of checkout-service is broken, rollback immediately!"

Agent: Uses rollback_decision prompt
→ Shows deployment history (v3.2.0 failed → v3.1.5 stable)
→ Previews rollback changes
→ Executes rollback (42 seconds)
→ Validates recovery (0% error rate)

Time: ~1 minute | Requires: 1 confirmation (or auto in emergency)
```

**👉 [Read the Full User Guide](./USER_GUIDE.md)** for 5 complete workflow examples with detailed agent flows, tool chains, and realistic outputs.

---

## 📋 Prerequisites

- **ArgoCD Server**: Running ArgoCD instance (v2.x)
- **Authentication**: ArgoCD API token ([How to get token](#getting-argocd-token))
- **Git Credentials**: For repository onboarding
  - **HTTPS**: GitHub personal access token
  - **SSH**: SSH private key (~/.ssh/id_rsa or custom path)
- **Python 3.12+** (for local installation)

### Getting ArgoCD Token

Use the provided Python script to fetch your ArgoCD authentication token:

```bash
# Navigate to the scripts directory
cd argocd_mcp_server/scripts

# Option 1: Using environment variables (recommended)
export ARGOCD_SERVER="https://localhost:8080"  # or your ArgoCD server URL
export ARGOCD_USERNAME="admin"
export ARGOCD_PASSWORD="your-password"
export ARGOCD_VERIFY_TLS="false"  # Set to "false" for self-signed certs

python fetch_argocd_token.py

# Option 2: Using command-line arguments
python fetch_argocd_token.py \
  --server https://localhost:8080 \
  --username admin \
  --password your-password \
  --insecure  # Skip TLS verification for self-signed certs

# Option 3: Get export command directly
python fetch_argocd_token.py --output env
# Output: export ARGOCD_AUTH_TOKEN='eyJhbGc...'
```

**Environment Variables:**
- `ARGOCD_SERVER` - ArgoCD server URL (required)
- `ARGOCD_USERNAME` - Username (default: `admin`)
- `ARGOCD_PASSWORD` - Password (required)
- `ARGOCD_VERIFY_TLS` - Set to `false` for self-signed certificates

The script will:
1. Authenticate with your ArgoCD server
2. Retrieve the API token
3. Validate the token by making a test API call
4. Output the token (use `--output env` for export command)

---

## 📦 Installation

### Option 1: Docker (Recommended for Quick Start)

The easiest way to get started is using the pre-built Docker image from Docker Hub.

#### Pull and Run

```bash
# Pull the latest image
docker pull sandeep2014/talkops-mcp:argocd-mcp-server-latest

# Run with default configuration (read-only mode)
docker run --rm -it \
  -p 8765:8765 \
  -v ~/.ssh/id_ed25519:/app/.ssh/id_rsa:ro \
  -e ARGOCD_SERVER_URL="https://argocd.example.com" \
  -e SSH_PRIVATE_KEY_PATH=/app/.ssh/id_rsa \
  -e ARGOCD_AUTH_TOKEN="your-token-here" \
  sandeep2014/talkops-mcp:argocd-mcp-server-latest

# Run with write access enabled
docker run --rm -it \
  -p 8765:8765 \
  -v ~/.ssh/id_ed25519:/app/.ssh/id_rsa:ro \
  -e ARGOCD_SERVER_URL="https://host.docker.internal:8080" \
  -e ARGOCD_AUTH_TOKEN="your-token-here" \
  -e ARGOCD_INSECURE="true" \
  -e SSH_PRIVATE_KEY_PATH=/app/.ssh/id_rsa \
  -e MCP_ALLOW_WRITE="true" \
  sandeep2014/talkops-mcp:argocd-mcp-server-latest
```

### Option 2: Using uv

```bash
# Install uv if not already installed
curl -LsSf https://astral.sh/uv/install.sh | sh

# Clone the repository
git clone git@github.com:talkops-ai/talkops-mcp.git
cd talkops-mcp/src/argocd-mcp-server

# Create virtual environment and install
uv venv --python=3.12
source .venv/bin/activate  # On Unix/macOS
# .venv\Scripts\activate   # On Windows

uv pip install -e .
uv run argocd-mcp-server
```

### Option 3: Using pip

```bash
git clone git@github.com:talkops-ai/talkops-mcp.git
cd talkops-mcp/src/argocd-mcp-server

python -m venv .venv
source .venv/bin/activate

pip install -e .
```


#### For ArgoCD Running on Host Machine (Port-Forwarded)

If your ArgoCD server is running in a local Kubernetes cluster and you've port-forwarded it to your host machine (e.g., `kubectl port-forward svc/argocd-server -n argocd 8080:443`), use `host.docker.internal`:

```bash
docker run --rm -it \
  -p 8765:8765 \
  -v ~/.ssh/id_ed25519:/app/.ssh/id_rsa:ro \
  -e ARGOCD_SERVER_URL="https://host.docker.internal:8080" \
  -e ARGOCD_AUTH_TOKEN="your-token-here" \
  -e SSH_PRIVATE_KEY_PATH=/app/.ssh/id_rsa \
  -e ARGOCD_INSECURE="true" \
  -e MCP_ALLOW_WRITE="true" \
  sandeep2014/talkops-mcp:argocd-mcp-server-latest
```

**Note:** `host.docker.internal` is a special DNS name that resolves to your host machine from inside the Docker container (Mac/Windows only). This allows the container to access services port-forwarded to `localhost` on your host.

#### With SSH Repository Onboarding

```bash
docker run --rm -it \
  -p 8765:8765 \
  -v ~/.ssh/id_ed25519:/app/.ssh/id_rsa:ro \
  -e ARGOCD_SERVER_URL="https://argocd.example.com" \
  -e ARGOCD_AUTH_TOKEN="your-token-here" \
  -e GIT_PASSWORD="ghp_your_github_token" \
  -e MCP_ALLOW_WRITE="true" \
  sandeep2014/talkops-mcp:argocd-mcp-server-latest
```

#### Build from Source (Optional)

If you prefer to build the Docker image yourself:

```bash
# Navigate to the argocd-mcp-server directory
cd talkops-mcp/src/argocd-mcp-server

# Build the image
docker build -t argocd-mcp-server .

# Run your built image
docker run --rm -it \
  -p 8765:8765 \
  -e ARGOCD_AUTH_TOKEN="your-token" \
  argocd-mcp-server
```

#### Using Docker Compose

See the included `docker-compose.yml` for a complete example with all configuration options.

```bash
# Set required environment variables
export ARGOCD_SERVER_URL="https://argocd.example.com"
export ARGOCD_AUTH_TOKEN="your-token"
export GIT_PASSWORD="ghp_your_github_token"

# Start the server
docker-compose up
```

---

## ⚙️ Configuration

The ArgoCD MCP Server can be configured using environment variables. All configuration options have sensible defaults.

### Environment Variables

#### Server Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `MCP_SERVER_NAME` | `argocd-mcp-server` | Server name identifier |
| `MCP_SERVER_VERSION` | `0.1.0` | Server version string |
| `MCP_TRANSPORT` | `http` | Transport mode: `http` (HTTP/SSE) or `stdio` |
| `MCP_HOST` | `0.0.0.0` | Host address for HTTP/SSE server |
| `MCP_PORT` | `8765` | Port for HTTP/SSE server |
| `MCP_PATH` | `/sse` | SSE endpoint path |
| `MCP_ALLOW_WRITE` | `false` | **Enable write operations** (see [Write Access Control](#write-access-control)) |
| `MCP_HTTP_TIMEOUT` | `300` | HTTP request timeout in seconds |
| `MCP_HTTP_KEEPALIVE_TIMEOUT` | `5` | HTTP keepalive timeout in seconds |
| `MCP_HTTP_CONNECT_TIMEOUT` | `60` | HTTP connection timeout in seconds |
| `MCP_LOG_LEVEL` | `INFO` | Logging level: `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `MCP_LOG_FORMAT` | `json` | Log format: `json` or `text` |

#### ArgoCD Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `ARGOCD_SERVER_URL` | `https://argocd-server.argocd.svc:443` | ArgoCD server URL |
| `ARGOCD_AUTH_TOKEN` | *(required)* | ArgoCD API authentication token |
| `ARGOCD_INSECURE` | `false` | Skip TLS verification (not recommended for production) |
| `ARGOCD_TIMEOUT` | `300` | Timeout in seconds for ArgoCD API operations |

#### Git Repository Credentials

| Variable | Default | Description |
|----------|---------|-------------|
| `GIT_USERNAME` | `""` | Git username (optional for token-only auth) |
| `GIT_PASSWORD` | *(required for HTTPS)* | GitHub personal access token |
| `SSH_PRIVATE_KEY_PATH` | `~/.ssh/id_rsa` | Path to SSH private key for SSH repos |

### Write Access Control

The `MCP_ALLOW_WRITE` environment variable controls whether **mutating operations** are allowed. This is a critical security feature.

#### When `MCP_ALLOW_WRITE=false` (Default - Read-Only Mode) 🛡️

Only **read-only operations** are allowed:
- ✅ **Discovery**: List applications, repositories, projects
- ✅ **Monitoring**: Get status, logs, events, metrics
- ✅ **Validation**: Check configs, preview diffs
- ✅ **Dry-run**: Sync with `dry_run=true` (preview only)
- ❌ **Create**: Applications, projects, repositories - BLOCKED
- ❌ **Update**: Application configs - BLOCKED
- ❌ **Delete**: Applications, projects, repositories - BLOCKED
- ❌ **Sync**: Deploy applications - BLOCKED (dry-run allowed)
- ❌ **Rollback**: Revert deployments - BLOCKED

**Error message when blocked:**
```
ArgoCDOperationError: ArgoCD {operation} is not allowed.
This MCP server is configured for read-only operations.
To enable write operations, set environment variable: MCP_ALLOW_WRITE=true
```

#### When `MCP_ALLOW_WRITE=true` (Write Mode) ✅

All operations are enabled:
- ✅ All read-only operations
- ✅ **Create**: Applications, projects, repositories
- ✅ **Update**: Modify application configurations
- ✅ **Delete**: Remove applications, projects, repositories
- ✅ **Sync**: Deploy and update applications
- ✅ **Rollback**: Revert to previous versions

**Use Cases:**
- **Production monitoring**: `MCP_ALLOW_WRITE=false` - Prevent accidental changes
- **Audit/Compliance**: Read-only mode for dashboards and reporting
- **Development**: `MCP_ALLOW_WRITE=true` - Full control for dev/staging
- **Emergency access**: Temporarily enable for critical operations

**Note**: Sync operations with `dry_run=true` are always allowed in read-only mode.

### Quick Start Configuration

```bash
# Minimal configuration (read-only mode)
export ARGOCD_SERVER_URL="https://argocd.example.com"
export ARGOCD_AUTH_TOKEN="your-token-here"

# Enable write operations
export MCP_ALLOW_WRITE="true"

# For HTTPS repository onboarding
export GIT_PASSWORD="ghp_your_github_token"

# For SSH repository onboarding  
export SSH_PRIVATE_KEY_PATH="~/.ssh/id_rsa"

# Optional: Disable TLS verification (dev only)
export ARGOCD_INSECURE="true"
```

---

## 🖥️ MCP Client Configuration

**This section shows how to configure MCP clients** (such as Claude Desktop, Cline, or other MCP-compatible applications) **to connect to the ArgoCD MCP Server**.

### Step 1: Start the Server

#### Option A: Using Docker (Recommended)

Start the ArgoCD MCP Server using the pre-built Docker image:

```bash
# Pull the latest image
docker pull sandeep2014/talkops-mcp:argocd-mcp-server-latest

# Start the server (for port-forwarded ArgoCD)
docker run --rm -it \
  -p 8765:8765 \
  -v ~/.ssh/id_ed25519:/app/.ssh/id_rsa:ro \
  -e ARGOCD_SERVER_URL="https://host.docker.internal:8080" \
  -e ARGOCD_AUTH_TOKEN="your-token-here" \
  -e ARGOCD_INSECURE="true" \
  -e SSH_PRIVATE_KEY_PATH=/app/.ssh/id_rsa \
  -e MCP_ALLOW_WRITE="true" \
  sandeep2014/talkops-mcp:argocd-mcp-server-latest
```

Expected output:
```
🚀 Starting ArgoCD MCP Server
📋 Configuration:
   Server: argocd-mcp-server v0.1.0
   Transport: http
   Listen: 0.0.0.0:8765/sse
   Write Mode: true
   Log Level: INFO

🔗 ArgoCD Configuration:
   Server URL: https://host.docker.internal:8080
   Auth Token: ***SET***
   Insecure: true

✅ Starting server...

INFO:     Started server process [1]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8765 (Press CTRL+C to quit)
```

### Step 2: Configure the Client

Once the server is running, configure your MCP client to connect using SSE (Server-Sent Events):

```json
{
  "mcpServers": {
    "argocd-mcp-server": {
      "transport": "sse",
      "url": "http://localhost:8765/sse",
      "description": "ArgoCD MCP Server for GitOps application management",
      "disabled": false,
      "autoApprove": [],
      "timeout": 300.0,
      "connect_timeout": 60.0
    }
  }
}
```

**Configuration Notes:**
- Replace `8765` with the port you configured (`MCP_PORT`)
- `timeout`: Request timeout in seconds (default: 300)
- `connect_timeout`: Connection establishment timeout (default: 60)
- `autoApprove`: List of tools that don't require user confirmation (use with caution)

### Read-Only Mode Configuration

For a read-only configuration (monitoring and validation only):

```bash
# Start in read-only mode
export MCP_ALLOW_WRITE="false"
argocd-mcp-server
```

Use the same client configuration. Write operations will be automatically blocked with helpful error messages.

---

## 🛠️ Available Tools

### Application Management Tools

| Tool | Description | Write Access Required |
|------|-------------|-----------------------|
| `list_applications` | List all applications in a cluster | No ✅ |
| `get_application_details` | Get detailed application information | No ✅ |
| `create_application` | Create a new ArgoCD application | Yes ✋ |
| `update_application` | Update application configuration | Yes ✋ |
| `delete_application` | Delete an ArgoCD application | Yes ✋ |
| `validate_application_config` | Validate application configuration | No ✅ |
| `get_application_events` | Get Kubernetes events for application | No ✅ |

### Deployment & Operations Tools

| Tool | Description | Write Access Required |
|------|-------------|-----------------------|
| `sync_application` | Sync application to desired state | Yes ✋ (dry-run allowed) |
| `get_application_diff` | Preview changes before deployment | No ✅ |
| `get_sync_status` | Get current sync operation status | No ✅ |
| `rollback_application` | Rollback to previous revision | Yes ✋ |
| `rollback_to_revision` | Rollback to specific revision | Yes ✋ |
| `get_application_logs` | Get application logs with error detection | No ✅ |
| `prune_resources` | Remove resources not in desired state | Yes ✋ |
| `hard_refresh` | Force refresh application state | Yes ✋ |
| `soft_refresh` | Soft refresh application state | Yes ✋ |
| `cancel_deployment` | Cancel ongoing sync operation | Yes ✋ |

### Repository Management Tools

| Tool | Description | Write Access Required |
|------|-------------|-----------------------|
| `onboard_repository_https` | Onboard GitHub repository via HTTPS | Yes ✋ |
| `onboard_repository_ssh` | Onboard GitHub repository via SSH | Yes ✋ |
| `list_repositories` | List all registered repositories | No ✅ |
| `get_repository` | Get repository details | No ✅ |
| `validate_repository_connection` | Validate repository connectivity | No ✅ |
| `delete_repository` | Delete a repository from ArgoCD | Yes ✋ |
| `generate_repository_secret_manifest` | Generate Kubernetes secret YAML | No ✅ |

### Project Management Tools

| Tool | Description | Write Access Required |
|------|-------------|-----------------------|
| `create_project` | Create ArgoCD project with RBAC | Yes ✋ |
| `list_projects` | List all ArgoCD projects | No ✅ |
| `get_project` | Get project details | No ✅ |
| `delete_project` | Delete an ArgoCD project | Yes ✋ |
| `generate_project_manifest` | Generate AppProject YAML | No ✅ |

**Legend:**
- ✅ = Available in read-only mode
- ✋ = Requires `MCP_ALLOW_WRITE=true`

---

## 📁 Available Resources

Resources provide real-time data streams that can be monitored by AI agents.

| Resource URI | Description | Update Frequency |
|--------------|-------------|------------------|
| `argocd://applications/{cluster}` | List all applications and their state | Every 5 seconds |
| `argocd://application-metrics/{cluster}/{app}` | Real-time application metrics | Every 10 seconds |
| `argocd://sync-operations/{cluster}` | Active sync operations | Every 2 seconds |
| `argocd://deployment-events/{cluster}` | Deployment event stream | Real-time |
| `argocd://cluster-health/{cluster}` | Overall cluster health | Every 30 seconds |

**Usage Example:**
```
"Monitor the sync operation for my-app in production cluster"
```

The agent will subscribe to `argocd://sync-operations/production` and provide real-time updates.

---

## 💬 Available Prompts

Prompts are guided workflows that orchestrate multiple tools to accomplish complex tasks.

| Prompt | Description | Tools Used |
|--------|-------------|------------|
| `onboard_github_repository` | Step-by-step repository onboarding | 4 tools (validate → onboard → verify) |
| `full_application_deployment` | End-to-end deployment from repo to app | 11 tools (repo → create → diff → sync → validate) |
| `debug_application_issues` | Comprehensive troubleshooting | 5 tools (status → logs → events → config) |
| `rollback_decision` | Guided rollback with impact analysis | 8 tools (assess → preview → execute → validate) |
| `setup_argocd_project` | Multi-tenancy project setup | 4 tools (create → verify → manifest) |
| `deploy_new_version` | Guided deployment workflow | 7 tools (validate → diff → sync → monitor) |
| `post_deployment_validation` | Comprehensive health check | 4 tools (status → config → logs → metrics) |

**Usage Example:**
```
"Help me onboard my GitHub repository https://github.com/myorg/myapp"
```

The agent will invoke the `onboard_github_repository` prompt and guide you through the process.

---

## 💻 Usage Examples

### Repository Onboarding

```
"I want to onboard my GitHub repository https://github.com/myorg/myapp to ArgoCD"
```

The AI will:
1. Check environment credentials
2. Validate repository connection
3. Onboard to ArgoCD
4. Verify registration

### Application Deployment

```
"Deploy my application from https://github.com/myorg/myapp to production cluster"
```

The AI will:
1. Onboard repository (if needed)
2. Create ArgoCD application
3. Show deployment preview
4. Execute deployment
5. Monitor progress
6. Validate success

### Debugging

```
"My app 'payment-service' is not working in production, help me debug it"
```

The AI will:
1. Analyze application status
2. Check logs for errors
3. Review Kubernetes events
4. Identify root cause
5. Provide recommendations

### Monitoring

```
"Show me the health status of all applications in production"
```

The AI will access the `argocd://applications/production` resource.

---

## 🏗️ Architecture

```
argocd-mcp-server/
├── argocd_mcp_server/         # Main package
│   ├── tools/                 # MCP Tools (29 total)
│   │   ├── application_manager/   # Application lifecycle tools
│   │   │   ├── app_operations.py
│   │   │   └── config_operations.py
│   │   ├── deployment_executor/   # Deployment and sync tools
│   │   │   └── deployment_operations.py
│   │   ├── repository_mgmt/       # Repository management tools
│   │   │   └── repository_operations.py
│   │   └── project_mgmt/          # Project management tools
│   │       └── project_operations.py
│   ├── resources/             # MCP Resources (5 total)
│   │   ├── argocd_resources.py    # Real-time data streams
│   │   └── workflow_resource.py   # Static documentation
│   ├── prompts/               # MCP Prompts (7 total)
│   │   ├── deployment_workflows.py
│   │   └── repository_workflows.py
│   ├── services/              # Business logic layer
│   │   ├── argocd_service.py      # ArgoCD API operations
│   │   └── argocd_mgmt.py         # Repository & project management
│   ├── server/                # FastMCP server setup
│   │   ├── bootstrap.py           # Initialization
│   │   ├── core.py                # FastMCP configuration
│   │   └── middleware.py          # HTTP middleware
│   ├── exceptions/             # Custom exceptions
│   │   └── exceptions.py
│   ├── utils/                 # Utility functions
│   │   └── argocd_helper.py       # Security helpers
│   ├── static/                 # Static documentation
│   │   ├── ARGOCD_WORKFLOW.md     # Architecture guide
│   │   └── ARGOCD_MCP_INSTRUCTIONS.md
│   ├── config.py              # Configuration management
│   └── main.py                # Application entry point
├── scripts/                    # Helper scripts
│   └── fetch_argocd_token.sh  # Token retrieval script
├── tests/                      # Test suite
├── USER_GUIDE.md              # Complete user guide
├── pyproject.toml             # Project configuration
└── README.md                  # This file
```

---

## 🔒 Security

### Write Access Control
- **🛡️ Read-Only Mode**: By default (`MCP_ALLOW_WRITE=false`), the server prevents all mutating operations
- **Protected Operations**: Create, update, delete, sync, rollback operations are blocked with helpful error messages
- **Dry-Run Support**: Sync operations with `dry_run=true` are allowed even in read-only mode
- **Use Cases**:
  - **Audit/Monitoring**: Use for dashboards without write access

### Credential Management
- **🔐 No Credentials in Tool Parameters**: All sensitive credentials (passwords, tokens, SSH keys) are read from environment variables or secure file paths to prevent exposure to LLM models
- **HTTPS Repositories**: Git credentials are read from `GIT_USERNAME` and `GIT_PASSWORD` environment variables
- **SSH Repositories**: SSH private key is read from `SSH_PRIVATE_KEY_PATH` (defaults to `~/.ssh/id_rsa`)
- **ArgoCD Token**: Passed via `ARGOCD_AUTH_TOKEN` environment variable, never as command arguments

### TLS & Network Security
- **TLS Verification**: Full certificate verification enabled by default
- **Development Mode**: Set `ARGOCD_INSECURE="true"` to bypass TLS verification (not recommended for production)

### Best Practices
✅ **DO**: Use environment variables for all secrets  
✅ **DO**: Rotate credentials regularly  
✅ **DO**: Use deploy keys instead of personal SSH keys for production  
✅ **DO**: Run in read-only mode for production monitoring  
❌ **DON'T**: Pass credentials as command-line arguments  
❌ **DON'T**: Commit credentials to version control  
❌ **DON'T**: Enable write access in production without careful consideration

---

## 📚 Documentation

### User Documentation
- **[User Guide](./USER_GUIDE.md)** - Complete guide with workflow examples, natural language queries, and expected outputs
  - Repository onboarding workflow
  - Application deployment workflow  
  - Debugging workflow
  - Rollback workflow
  - Monitoring & metrics

### Technical Documentation
- **[ArgoCD Workflow Architecture](./argocd_mcp_server/static/ARGOCD_WORKFLOW.md)** - Detailed architecture and tool descriptions
- **[MCP Instructions](./argocd_mcp_server/static/ARGOCD_MCP_INSTRUCTIONS.md)** - Configuration and best practices

---

## 🧪 Development

### Running Locally

```bash
# Navigate to the server directory
cd talkops-mcp/src/argocd-mcp-server

# Install in development mode
uv pip install -e .

# Set environment variables
export ARGOCD_SERVER_URL="https://argocd.example.com"
export ARGOCD_AUTH_TOKEN="your-token"
export MCP_ALLOW_WRITE="true"

# Run the server
uv run argocd-mcp-server
```

---

## 🔧 Troubleshooting

### Connection Timeout Errors

If you encounter `httpx.ConnectTimeout` errors when connecting to the server, increase client timeout values:

```json
{
  "url": "http://localhost:9000/sse",
  "transport": "sse",
  "timeout": 300.0,        // Increase from default 30s
  "connect_timeout": 60.0   // Increase from default 10s
}
```

**Why this happens:**
- Server initialization can take time (loading tools, resources, prompts)
- Network latency between client and server
- Default client timeout may be too short

### ArgoCD Connection Errors

**Error**: `ArgoCDConnectionError: Failed to connect to ArgoCD`

**Solutions:**
1. Verify `ARGOCD_SERVER_URL` is correct
2. Check `ARGOCD_AUTH_TOKEN` is valid
3. Ensure ArgoCD server is accessible
4. Check network connectivity
5. Try with `ARGOCD_INSECURE=true` for dev environments

### Repository Onboarding Failures

**Error**: `GIT_PASSWORD environment variable is not set`

**Solution:**
```bash
export GIT_PASSWORD="ghp_your_github_token"
```

Generate token at: https://github.com/settings/tokens (requires `repo` scope)

**Error**: SSH key not found

**Solution:**
```bash
# Use default location
export SSH_PRIVATE_KEY_PATH="~/.ssh/id_rsa"

# Or custom location
export SSH_PRIVATE_KEY_PATH="/path/to/your/key"

# Ensure key has correct permissions
chmod 600 ~/.ssh/id_rsa
```

### Write Operations Blocked

**Error**: `ArgoCD {operation} is not allowed. This MCP server is configured for read-only operations.`

**Solution:**
```bash
# Enable write operations
export MCP_ALLOW_WRITE="true"

# Restart the server
argocd-mcp-server
```

---

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

---

## 📄 License

This project is licensed under the Apache License 2.0 — see the [LICENSE](LICENSE) file for details.

---

## 🙏 Acknowledgments

- [Model Context Protocol](https://modelcontextprotocol.io/) for the MCP specification
- [FastMCP](https://github.com/jlowin/fastmcp) for the Python MCP framework
- [ArgoCD](https://argo-cd.readthedocs.io/) for GitOps application delivery

---

## 📞 Support

For questions, issues, or feature requests:
- **GitHub Issues**: Open an issue for bug reports or feature requests
- **Documentation**: Check the [User Guide](./USER_GUIDE.md) and [Technical Docs](./argocd_mcp_server/static/)
- **Community**: Join our [Discord server](https://discord.gg/tSN2Qn9uM8) to raise requests and get community support

---

**Made with ❤️ for the GitOps and AI community**
