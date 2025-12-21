# Helm MCP Server

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![MCP](https://img.shields.io/badge/MCP-Model%20Context%20Protocol-green.svg)](https://modelcontextprotocol.io/)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Helm](https://img.shields.io/badge/Helm-v3-blue.svg)](https://helm.sh/)
[![Discord](https://img.shields.io/badge/Discord-Join-5865F2?logo=discord&logoColor=white)](https://discord.gg/tSN2Qn9uM8)

A comprehensive **Model Context Protocol (MCP)** server for managing Kubernetes workloads via Helm. Designed for AI assistants to perform secure, production-grade Helm operations with full validation, monitoring, and best practices guidance.

---

## ✨ Features

### 🔍 Discovery & Search
- Search Helm charts across repositories (Bitnami, ArtifactHub, custom repos)
- Get detailed chart metadata, versions, and documentation
- Access chart READMEs and values schemas

### 🚀 Installation & Lifecycle Management
- Install, upgrade, rollback, and uninstall Helm releases
- Dry-run installations to preview changes before deployment
- Support for custom values, multiple values files, and extra CLI arguments

### ✅ Validation & Safety
- Validate chart values against JSON schemas
- Render and validate Kubernetes manifests before deployment
- Check chart dependencies and cluster prerequisites
- Generate installation plans with resource estimates

### 📊 Monitoring & Status
- Monitor deployment health asynchronously
- Get real-time release status and history
- List all releases across namespaces

### 🔧 Multi-Cluster Support
- List and switch between Kubernetes contexts
- Switch between clusters via kubeconfig context
- Namespace-scoped operations for isolation

### 📚 Built-in Guidance
- Comprehensive workflow guides and best practices
- Security checklists and troubleshooting guides
- Step-by-step procedures for upgrades and rollbacks

---

## 📦 Installation

### Prerequisites

- **Docker** (for Docker installation) or **Python 3.12+** (for local installation)
- **Helm CLI** ([Installation Guide](https://helm.sh/docs/intro/install/)) - Required for local installation, included in Docker image
- **kubectl** ([Installation Guide](https://kubernetes.io/docs/tasks/tools/)) - Required for local installation, included in Docker image
- **Access to Kubernetes cluster(s)** (kubeconfig)

### Option 1: Docker Hub (Recommended for Quick Start)

The easiest way to get started is using the pre-built Docker image from Docker Hub.

```bash
# Pull the image from Docker Hub
docker pull sandeep2014/talkops-mcp:helm-mcp-server-latest

# Run the server with default configuration (port 8765)
# Map container port 8765 to host port 8765
docker run --rm -it \
  -p 8765:8765 \
  -v ~/.kube/config:/app/.kube/config:ro \
  sandeep2014/talkops-mcp:helm-mcp-server-latest

# Run the server with custom environment variables
# Environment variables set via -e flags will override the defaults
# Map container port 9000 to host port 9000
docker run --rm -it \
  -p 9000:9000 \
  -v ~/.kube/config:/app/.kube/config:ro \
  -e MCP_PORT=9000 \
  -e MCP_LOG_LEVEL=DEBUG \
  -e MCP_ALLOW_WRITE=false \
  -e HELM_TIMEOUT=600 \
  sandeep2014/talkops-mcp:helm-mcp-server-latest

# Run in read-only mode (validation and monitoring only)
docker run --rm -it \
  -p 8765:8765 \
  -v ~/.kube/config:/app/.kube/config:ro \
  -e MCP_ALLOW_WRITE=false \
  sandeep2014/talkops-mcp:helm-mcp-server-latest

# Map container port to a different host port
# Container runs on 8765, but accessible on host at 8080
docker run --rm -it \
  -p 8080:8765 \
  -v ~/.kube/config:/app/.kube/config:ro \
  sandeep2014/talkops-mcp:helm-mcp-server-latest
```

### Option 2: Build from Source (Docker)

If you prefer to build the Docker image from source:

```bash
# Navigate to the helm-mcp-server directory
cd talkops-mcp/src/helm-mcp-server

# Build the image
docker build -t helm-mcp-server .

# Run the server
docker run --rm -it \
  -p 8765:8765 \
  -v ~/.kube/config:/app/.kube/config:ro \
  helm-mcp-server
```

### Option 3: Using uv

```bash
# Install uv if not already installed
curl -LsSf https://astral.sh/uv/install.sh | sh

# Clone the repository
git clone git@github.com:talkops-ai/talkops-mcp.git
cd talkops-mcp/src/helm-mcp-server

# Create virtual environment and install
uv venv --python=3.12
source .venv/bin/activate  # On Unix/macOS
# .venv\Scripts\activate   # On Windows

uv pip install -e .
```

### Option 4: Using pip

```bash
git clone git@github.com:talkops-ai/talkops-mcp.git
cd talkops-mcp/src/helm-mcp-server

python -m venv .venv
source .venv/bin/activate

pip install -e .
```

---

## ⚙️ Configuration

The Helm MCP Server can be configured using environment variables. All configuration options have sensible defaults, but you can override them to match your environment.

**Note**: When running in Docker, you can override any environment variable using the `-e` flag with `docker run`. The Docker image includes an entrypoint script that sets default values, but any environment variables you provide via `docker run -e` will take precedence over the defaults.

### Environment Variables

#### Server Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `MCP_SERVER_NAME` | `helm-mcp-server` | Server name identifier |
| `MCP_SERVER_VERSION` | `0.2.0` | Server version string |
| `MCP_TRANSPORT` | `http` | Transport mode: `http` (HTTP/SSE) or `stdio` |
| `MCP_HOST` | `0.0.0.0` | Host address for HTTP/SSE server |
| `MCP_PORT` | `8765` | Port for HTTP/SSE server |
| `MCP_PATH` | `/sse` | SSE endpoint path |
| `MCP_ALLOW_WRITE` | `true` | **Enable write operations** (see [Write Access Control](#write-access-control)) |
| `MCP_HTTP_TIMEOUT` | `300` | HTTP request timeout in seconds |
| `MCP_HTTP_KEEPALIVE_TIMEOUT` | `5` | HTTP keepalive timeout in seconds |
| `MCP_HTTP_CONNECT_TIMEOUT` | `60` | HTTP connection timeout in seconds (also used as initialization timeout) |
| `MCP_LOG_LEVEL` | `INFO` | Logging level: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` |
| `MCP_LOG_FORMAT` | `json` | Log format: `json` or `text` |

#### Helm Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `HELM_TIMEOUT` | `300` | Timeout in seconds for Helm operations |

#### Kubernetes Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `K8S_TIMEOUT` | `30` | Timeout in seconds for Kubernetes API operations |
| `KUBECONFIG` | `~/.kube/config` | Path to kubeconfig file |

### Write Access Control

The `MCP_ALLOW_WRITE` environment variable controls whether **mutating operations** are allowed. This is a critical security feature that prevents accidental modifications to your Kubernetes cluster.

#### When `MCP_ALLOW_WRITE=true` (Default)

All operations are enabled, including:
- ✅ **Install** (`helm_install_chart`) - Install new Helm releases
- ✅ **Upgrade** (`helm_upgrade_release`) - Upgrade existing releases
- ✅ **Rollback** (`helm_rollback_release`) - Rollback to previous revisions
- ✅ **Uninstall** (`helm_uninstall_release`) - Remove Helm releases
- ✅ **Dry-run** operations - Preview changes without applying

#### When `MCP_ALLOW_WRITE=false` (Read-Only Mode)

Only **read-only operations** are allowed:
- ✅ **Discovery** - Search charts, get chart info
- ✅ **Validation** - Validate values, render manifests, check dependencies
- ✅ **Monitoring** - Get release status, list releases
- ✅ **Dry-run** operations - Preview installations without applying
- ❌ **Install** - Blocked (raises `HelmOperationError`)
- ❌ **Upgrade** - Blocked (raises `HelmOperationError`)
- ❌ **Rollback** - Blocked (raises `HelmOperationError`)
- ❌ **Uninstall** - Blocked (raises `HelmOperationError`)

**Use Case**: Set `MCP_ALLOW_WRITE=false` when you want to use the server for discovery, validation, and monitoring only, preventing any accidental deployments or modifications.

**Note**: Dry-run operations (`dry_run=True`) are always allowed, even when `MCP_ALLOW_WRITE=false`, as they don't modify the cluster.

### MCP Client Configuration

**This section shows how to configure MCP clients** (such as Claude Desktop, Cline, or other MCP-compatible applications) **to connect to and use the Helm MCP Server**. 

**Important**: The Helm MCP Server must be running before configuring your client. Start the server using one of the installation methods above, then configure your client to connect to it.

#### Step 1: Start the Server

First, start the Helm MCP Server using Docker or local installation:

**Using Docker:**
```bash
docker run --rm -it \
  -p 9000:9000 \
  -v ~/.kube/config:/app/.kube/config:ro \
  -e MCP_PORT=9000 \
  -e MCP_ALLOW_WRITE=true \
  -e MCP_LOG_LEVEL=INFO \
  sandeep2014/talkops-mcp:helm-mcp-server-latest
```

**Using Local Installation:**
```bash
cd /path/to/talkops-mcp/src/helm-mcp-server
source .venv/bin/activate
helm-mcp-server
```

#### Step 2: Configure the Client

Once the server is running, configure your MCP client to connect to it using SSE (Server-Sent Events) transport:

```json
{
  "mcpServers": {
    "helm-mcp-server": {
      "transport": "sse",
      "url": "http://localhost:9000/sse",
      "description": "Helm MCP Server for managing Kubernetes workloads via Helm",
      "disabled": false,
      "autoApprove": []
    }
  }
}
```

**Note**: Replace `9000` with the port you configured when starting the server. The default port is `8765` if not specified.

#### Read-Only Mode Configuration

For a read-only configuration (validation and monitoring only), start the server with `MCP_ALLOW_WRITE=false`:

```bash
docker run --rm -it \
  -p 9000:9000 \
  -v ~/.kube/config:/app/.kube/config:ro \
  -e MCP_PORT=9000 \
  -e MCP_ALLOW_WRITE=false \
  -e MCP_LOG_LEVEL=INFO \
  sandeep2014/talkops-mcp:helm-mcp-server-latest
```

Then use the same client configuration as above.

---

## 🛠️ Available Tools

### Discovery Tools

| Tool | Description |
|------|-------------|
| `helm_search_charts` | Search for Helm charts in repositories |
| `helm_get_chart_info` | Get detailed chart metadata and documentation |
| `helm_ensure_repository` | Ensure a Helm repository exists, adding it if necessary |

### Installation Tools

| Tool | Description |
|------|-------------|
| `helm_install_chart` | Install a Helm chart to cluster |
| `helm_upgrade_release` | Upgrade an existing Helm release |
| `helm_rollback_release` | Rollback to a previous revision |
| `helm_uninstall_release` | Uninstall a Helm release |
| `helm_dry_run_install` | Preview installation without deploying |

### Validation Tools

| Tool | Description |
|------|-------------|
| `helm_validate_values` | Validate chart values against schema |
| `helm_render_manifests` | Render Kubernetes manifests from chart |
| `helm_validate_manifests` | Validate rendered Kubernetes manifests |
| `helm_check_dependencies` | Check if chart dependencies are available |
| `helm_get_installation_plan` | Generate installation plan with resource estimates |

### Kubernetes Tools

| Tool | Description |
|------|-------------|
| `kubernetes_get_cluster_info` | Get cluster information |
| `kubernetes_list_namespaces` | List all Kubernetes namespaces |
| `kubernetes_list_contexts` | List all available Kubernetes contexts from kubeconfig |
| `kubernetes_set_context` | Set/switch to a specific Kubernetes context |
| `kubernetes_get_helm_releases` | List all Helm releases in cluster |
| `kubernetes_check_prerequisites` | Check cluster prerequisites |

### Monitoring Tools

| Tool | Description |
|------|-------------|
| `helm_monitor_deployment` | Monitor deployment health asynchronously |
| `helm_get_release_status` | Get current status of a Helm release |

---

## 📁 Available Resources

| Resource URI | Description |
|--------------|-------------|
| `helm://releases` | List all Helm releases in cluster |
| `helm://releases/{release_name}` | Get detailed release information |
| `helm://charts` | List available charts in repositories |
| `helm://charts/{repo}/{name}` | Get specific chart metadata |
| `helm://charts/{repo}/{name}/readme` | Get chart README documentation |
| `kubernetes://cluster-info` | Get Kubernetes cluster information |
| `kubernetes://namespaces` | List all Kubernetes namespaces |
| `helm://best_practices` | Helm Best Practices guide |

---

## 💬 Available Prompts

| Prompt | Description | Arguments |
|--------|-------------|-----------|
| `helm_workflow_guide` | Complete workflow documentation | — |
| `helm_quick_start` | Quick start for common operations | — |
| `helm_installation_guidelines` | Installation best practices | — |
| `helm_troubleshooting_guide` | Troubleshooting common issues | `error_type` |
| `helm_security_checklist` | Security considerations | — |
| `helm_upgrade_guide` | Upgrade guide for charts | `chart_name` |
| `helm_rollback_procedures` | Rollback step-by-step guide | `release_name` |

---

## 📖 Usage Examples

### Installing a Chart

```
"Install PostgreSQL from Bitnami in the database namespace"
```

The AI assistant will:
1. Search for the chart using `helm_search_charts`
2. Validate values with `helm_validate_values`
3. Preview with `helm_dry_run_install`
4. Install using `helm_install_chart`
5. Monitor with `helm_monitor_deployment`

### Upgrading a Release

```
"Upgrade my-app release to version 2.0 with increased replicas"
```

### Troubleshooting

```
"My pods are in CrashLoopBackOff after deploying redis"
```

The assistant will use `helm_troubleshooting_guide` with `error_type="pod-crashloop"`.

### Rolling Back

```
"Rollback my-release to the previous version"
```

### More Examples

- "Search for nginx ingress charts"
- "List all Helm releases in the production namespace"
- "What are the security best practices for Helm deployments?"
- "Show me the installation plan for prometheus-stack"
- "Uninstall the test-release from staging"

**For more detailed workflow information, best practices, and comprehensive guides, see the [Helm Workflow Guide](helm_mcp_server/static/HELM_WORKFLOW_GUIDE.md).**

---

## 🏗️ Architecture

```
helm-mcp-server/
├── helm_mcp_server/           # Main package
│   ├── tools/                 # MCP Tools
│   │   ├── discovery/         # Chart search and info
│   │   ├── installation/      # Install, upgrade, rollback, uninstall
│   │   ├── validation/        # Values and manifest validation
│   │   ├── kubernetes/         # Cluster operations
│   │   └── monitoring/        # Deployment monitoring
│   ├── resources/             # MCP Resources
│   │   ├── helm_resources.py
│   │   ├── chart_resources.py
│   │   ├── kubernetes_resources.py
│   │   └── static_resources.py
│   ├── prompts/               # MCP Prompts
│   │   ├── installation_prompts.py
│   │   ├── troubleshooting_prompts.py
│   │   ├── security_prompts.py
│   │   ├── upgrade_prompts.py
│   │   ├── rollback_prompts.py
│   │   └── workflow_prompts.py
│   ├── services/              # Business logic
│   │   ├── helm_service.py
│   │   ├── kubernetes_service.py
│   │   └── validation_service.py
│   ├── server/                # FastMCP server setup
│   │   ├── bootstrap.py
│   │   ├── core.py
│   │   └── middleware.py
│   ├── exceptions/             # Custom exceptions
│   ├── utils/                 # Utility functions
│   ├── static/                 # Static documentation
│   │   ├── HELM_BEST_PRACTICES.md
│   │   ├── HELM_WORKFLOW_GUIDE.md
│   │   └── HELM_MCP_INSTRUCTIONS.md
│   ├── config.py              # Configuration management
│   └── main.py                # Application entry point
├── tests/                      # Test suite
├── pyproject.toml             # Project configuration
└── README.md                  # This file
```

---

## 🔒 Security Considerations

- **Never hardcode secrets** in values files — use Kubernetes Secrets or external secret managers
- **Use namespace isolation** for different environments
- **Follow RBAC principles** — grant minimum required permissions
- **Pin chart versions** for reproducible deployments
- **Review rendered manifests** before applying to production
- **Use the `helm_security_checklist` prompt** for comprehensive security guidance

---

## 🧪 Development

### Running Locally

```bash
# Navigate to the helm-mcp-server directory
cd talkops-mcp/src/helm-mcp-server

# Install in development mode
uv pip install -e .

# Run the server
uv run helm-mcp-server
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
- [Helm](https://helm.sh/) for Kubernetes package management

---

## 🔧 Troubleshooting

### Connection Timeout Errors

If you encounter `httpx.ConnectTimeout` errors when connecting to the server, this is typically a client-side timeout issue. The client's connection timeout may be too short.

**Solution:** Increase the client timeout values in your MCP client configuration:

```python
# Recommended client configuration
{
    "url": f"http://{host}:{port}/sse",
    "transport": "sse",
    "timeout": 300.0,           # Increase from 30.0 to 300 seconds
    "connect_timeout": 60.0      # Increase from 10.0 to 60 seconds
}
```

**Why this happens:**
- The server may take time to initialize (loading tools, resources, prompts)
- Network latency between client and server
- The default client timeout of 10 seconds may be insufficient

**Server-side configuration:**
The server has configurable timeout settings via environment variables:
- `MCP_HTTP_TIMEOUT` (default: 300s) - HTTP request timeout
- `MCP_HTTP_CONNECT_TIMEOUT` (default: 60s) - Connection timeout
- `MCP_HTTP_KEEPALIVE_TIMEOUT` (default: 5s) - Keepalive timeout

### Chart Not Found Errors

If you see "chart not found" errors, ensure:
1. The chart exists in the specified repository
2. Run `helm repo update` to refresh repository indexes
3. Check the repository name is correct (e.g., `bitnami`, `argo`, etc.)

### Helm Command Timeouts

If Helm operations timeout, increase the timeout:
```bash
export HELM_TIMEOUT=600  # 10 minutes
```

---

## 📞 Support

For questions, issues, or feature requests:
- Open an issue on GitHub
- Join our [Discord server](https://discord.gg/tSN2Qn9uM8) to raise requests and get community support
- Check the `helm_workflow_guide` prompt for detailed documentation
- Consult the `helm://best_practices` resource for guidance
