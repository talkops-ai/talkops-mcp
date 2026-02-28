<p align="center">
  <img src="https://helm.sh/img/helm.svg" alt="Helm MCP Server" width="140"/>
</p>

<h1 align="center">Helm MCP Server</h1>

<p align="center">
  An MCP server that gives AI assistants full control over Helm — from chart discovery to production deployments.
</p>

<p align="center">
  <a href="https://github.com/talkops-ai/talkops-mcp/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-Apache%202.0-blue.svg?style=flat-square" alt="License"/></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/Python-3.12%2B-3776AB.svg?style=flat-square&logo=python&logoColor=white" alt="Python 3.12+"/></a>
  <a href="https://modelcontextprotocol.io/"><img src="https://img.shields.io/badge/MCP-Model%20Context%20Protocol-4A90D9.svg?style=flat-square" alt="MCP"/></a>
  <a href="https://helm.sh/"><img src="https://img.shields.io/badge/Helm-v3-0F1689.svg?style=flat-square&logo=helm&logoColor=white" alt="Helm v3"/></a>
  <a href="https://discord.gg/tSN2Qn9uM8"><img src="https://img.shields.io/badge/Discord-Join%20Us-5865F2.svg?style=flat-square&logo=discord&logoColor=white" alt="Discord"/></a>
</p>

<p align="center">
  <a href="#getting-started">Quick Start</a> · <a href="https://github.com/talkops-ai/talkops-mcp">Docs</a> · <a href="https://github.com/talkops-ai/talkops-mcp/issues/new?template=bug_report.md">Report Bug</a> · <a href="https://github.com/talkops-ai/talkops-mcp/issues/new?template=feature_request.md">Request Feature</a>
</p>

---

## Why Helm MCP Server?

**The problem.** Managing Kubernetes workloads through Helm is powerful, but the workflow is manual, error-prone, and demands context. You need to find the right chart, figure out which values to set, render manifests to verify what you're about to deploy, cross-check cluster state, validate dependencies — and that's before you even run `helm install`. If something goes wrong post-deploy, you're back to digging through release history, checking pod health, and hoping the rollback procedure is fresh in your mind.

AI assistants should be able to do all of this. But they can't — not without a structured interface to Helm and Kubernetes.

**What Helm MCP Server does.**

It exposes the full Helm lifecycle — discovery, validation, installation, monitoring, and rollback — as a set of MCP tools, resources, and prompts. Any MCP-compatible AI assistant (Claude, Cline, or your own agent) can use them to manage Helm operations the way a senior DevOps engineer would: search for charts, validate values against schemas, dry-run before deploying, monitor rollout health, and roll back if things go sideways.

Three things make this different:

1. **Safety-first design.** Every mutating operation can be locked behind a write-access toggle (`MCP_ALLOW_WRITE`). Dry-runs are always allowed. Manifests get rendered and validated before anything touches the cluster. The assistant operates with guardrails, not cowboy deploys.

2. **Full lifecycle, not just install.** Most Helm wrappers stop at `helm install`. This server covers chart discovery, repository management, value validation, manifest rendering, dependency checking, installation planning, deployment monitoring, status tracking, history, rollback, and uninstall. It's the whole workflow.

3. **Built-in operational knowledge.** The server ships with workflow guides, security checklists, troubleshooting runbooks, and upgrade procedures — exposed as MCP prompts. The assistant doesn't just execute commands; it follows best practices because the knowledge is baked into the protocol.

---

## Key Features

**Discovery & Search**
- Search Helm charts across repositories (Bitnami, ArtifactHub, custom repos)
- Get detailed chart metadata, versions, and documentation
- Access chart READMEs and values schemas directly through MCP resources

**Installation & Lifecycle**
- Install, upgrade, rollback, and uninstall Helm releases
- Dry-run installations to preview changes before they touch the cluster
- Support for custom values, multiple values files, and extra CLI arguments

**Validation & Safety**
- Validate chart values against JSON schemas before deployment
- Render and validate Kubernetes manifests ahead of time
- Check chart dependencies and cluster prerequisites
- Generate installation plans with resource estimates

**Monitoring & Status**
- Monitor deployment health asynchronously after install/upgrade
- Get real-time release status and full revision history
- List all releases across namespaces with a single call

**Multi-Cluster Support**
- List and switch between Kubernetes contexts from kubeconfig
- Namespace-scoped operations for environment isolation

**Built-in Guidance**
- Comprehensive workflow guides and best practices as MCP prompts
- Security checklists and troubleshooting guides ready to use
- Step-by-step procedures for upgrades, rollbacks, and incident response

---

## Architecture

The server is organized into layered service modules — tools on top, business logic in the middle, and Helm/Kubernetes CLIs at the bottom.

```
                    ┌─────────────────────────┐
                    │     MCP Client          │
                    │ (Claude, Cline, Agent)  │
                    └──────────┬──────────────┘
                               │
                    ┌──────────▼──────────────┐
                    │   FastMCP Server Core   │
                    │    (HTTP / stdio)       │
                    └──────────┬──────────────┘
                               │
          ┌────────────────────┼────────────────────┐
          │                    │                     │
    ┌─────▼─────┐      ┌──────▼──────┐      ┌──────▼──────┐
    │   Tools   │      │  Resources  │      │   Prompts   │
    │           │      │             │      │             │
    │ Discovery │      │ helm://     │      │ Workflow    │
    │ Install   │      │ kubernetes: │      │ Security    │
    │ Validate  │      │    //       │      │ Upgrade     │
    │ Monitor   │      │             │      │ Rollback    │
    │ K8s ops   │      │             │      │ Trouble-    │
    │           │      │             │      │   shoot     │
    └─────┬─────┘      └──────┬──────┘      └──────┬──────┘
          │                   │                     │
          └───────────────────┼─────────────────────┘
                              │
                    ┌─────────▼──────────┐
                    │   Service Layer    │
                    │                    │
                    │  helm_service.py   │
                    │  k8s_service.py    │
                    │  validation.py     │
                    └─────────┬──────────┘
                              │
                    ┌─────────▼──────────┐
                    │  Helm CLI / kubectl│
                    │  (subprocess)      │
                    └────────────────────┘
```

**How it works in practice:**

1. An AI assistant connects to the server over HTTP (or stdio)
2. It discovers available tools, resources, and prompts automatically
3. When a user asks something like "Deploy PostgreSQL to the database namespace," the assistant calls the appropriate tools in sequence — search, validate, dry-run, install, monitor
4. The service layer translates tool calls into Helm CLI and kubectl commands
5. Results flow back to the assistant, which presents them conversationally

---

## Table of Contents

- [Why Helm MCP Server?](#why-helm-mcp-server)
- [Key Features](#key-features)
- [Architecture](#architecture)
- [Tech Stack](#tech-stack)
- [Getting Started](#getting-started)
- [Configuration](#configuration)
- [Available Tools](#available-tools)
- [Available Resources](#available-resources)
- [Available Prompts](#available-prompts)
- [Usage](#usage)
- [Project Structure](#project-structure)
- [Roadmap](#roadmap)
- [Contributing](#contributing)
- [FAQ](#faq)
- [License](#license)
- [Contact](#contact)
- [Acknowledgments](#acknowledgments)

---

## Tech Stack

| Category | Technologies |
|----------|-------------|
| **Language** | Python 3.12+ |
| **MCP Framework** | [FastMCP](https://github.com/jlowin/fastmcp) |
| **Protocol** | [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) |
| **Kubernetes** | Helm v3 · kubectl |
| **Transport** | HTTP · stdio |
| **Infrastructure** | Docker · [uv](https://github.com/astral-sh/uv) |

---

## Getting Started

### Prerequisites

- **Docker** (recommended) or **Python 3.12+** (for local dev)
- **Helm CLI** ([install](https://helm.sh/docs/intro/install/)) — included in the Docker image
- **kubectl** ([install](https://kubernetes.io/docs/tasks/tools/)) — included in the Docker image
- **Access to a Kubernetes cluster** with a valid kubeconfig

### Quick Start with Docker (recommended)

Pull the image from Docker Hub and run:

```bash
docker run --rm -it \
  -p 8765:8765 \
  -v ~/.kube/config:/app/.kube/config:ro \
  talkopsai/helm-mcp-server:latest
```

That's it. The server is now listening on `http://localhost:8765/mcp`.

Point your MCP client at it:

```json
{
  "mcpServers": {
    "helm-mcp-server": {
      "url": "http://localhost:8765/mcp",
      "description": "Helm MCP Server for managing Kubernetes workloads via Helm"
    }
  }
}
```

### Build from Source (Docker)

If you prefer to build the image yourself:

```bash
cd talkops-mcp/src/helm-mcp-server
docker build -t helm-mcp-server .

docker run --rm -it \
  -p 8765:8765 \
  -v ~/.kube/config:/app/.kube/config:ro \
  helm-mcp-server
```

### From Source (Python)

For development or if you want to run without Docker:

1. Install [uv](https://docs.astral.sh/uv/getting-started/installation/) for dependency management.

2. Clone and set up:

```bash
# Install uv if not already installed
curl -LsSf https://astral.sh/uv/install.sh | sh

# Clone the repository
git clone https://github.com/talkops-ai/talkops-mcp.git
cd talkops-mcp/src/helm-mcp-server

# Create virtual environment and install
uv venv --python=3.12
source .venv/bin/activate  # On Unix/macOS
# .venv\Scripts\activate   # On Windows

uv pip install -e .
```

3. Run the server:

```bash
uv run helm-mcp-server
```

Alternatively, with pip:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
helm-mcp-server
```

---

## Configuration

All configuration is via environment variables. Sensible defaults are built in — you only need to override what you want to change.

When running in Docker, pass overrides with `-e`:

```bash
docker run --rm -it \
  -p 9000:9000 \
  -v ~/.kube/config:/app/.kube/config:ro \
  -e MCP_PORT=9000 \
  -e MCP_LOG_LEVEL=DEBUG \
  -e MCP_ALLOW_WRITE=false \
  talkopsai/helm-mcp-server:latest
```

### Server Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `MCP_SERVER_NAME` | `helm-mcp-server` | Server name identifier |
| `MCP_SERVER_VERSION` | `0.2.0` | Server version string |
| `MCP_TRANSPORT` | `http` | Transport mode: `http` or `stdio` |
| `MCP_HOST` | `0.0.0.0` | Host address for HTTP server |
| `MCP_PORT` | `8765` | Port for HTTP server |
| `MCP_PATH` | `/mcp` | MCP endpoint path |
| `MCP_ALLOW_WRITE` | `true` | Enable mutating operations (see below) |
| `MCP_HTTP_TIMEOUT` | `300` | HTTP request timeout (seconds) |
| `MCP_HTTP_KEEPALIVE_TIMEOUT` | `5` | HTTP keepalive timeout (seconds) |
| `MCP_HTTP_CONNECT_TIMEOUT` | `60` | Connection timeout (seconds) |
| `MCP_LOG_LEVEL` | `INFO` | Log level: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` |
| `MCP_LOG_FORMAT` | `json` | Log format: `json` or `text` |

### Helm & Kubernetes

| Variable | Default | Description |
|----------|---------|-------------|
| `HELM_TIMEOUT` | `300` | Timeout for Helm operations (seconds) |
| `K8S_TIMEOUT` | `30` | Timeout for Kubernetes API calls (seconds) |
| `KUBECONFIG` | `~/.kube/config` | Path to kubeconfig file |

### Write Access Control

The `MCP_ALLOW_WRITE` flag is the primary safety mechanism. It controls whether the server accepts mutating operations.

**When `true` (default)** — everything is enabled: install, upgrade, rollback, uninstall, plus all read operations.

**When `false` (read-only mode)** — only safe operations are allowed:

| Allowed | Blocked |
|---------|---------|
| Chart search and discovery | `helm_install_chart` |
| Value validation | `helm_upgrade_release` |
| Manifest rendering | `helm_rollback_release` |
| Dependency checking | `helm_uninstall_release` |
| Release status and monitoring | |
| Dry-run operations | |

Dry-runs are always permitted regardless of this setting — they don't modify the cluster.

**Use case:** Set `MCP_ALLOW_WRITE=false` when you want the assistant to be able to explore, validate, and plan — but not actually change anything in the cluster.

---

## Available Tools

### Discovery

| Tool | Description |
|------|-------------|
| `helm_search_charts` | Search for Helm charts across configured repositories |
| `helm_get_chart_info` | Get detailed chart metadata, versions, and documentation |
| `helm_ensure_repository` | Add a Helm repository if it doesn't already exist |

### Installation & Lifecycle

| Tool | Description |
|------|-------------|
| `helm_install_chart` | Install a Helm chart to the cluster |
| `helm_upgrade_release` | Upgrade an existing release |
| `helm_rollback_release` | Rollback to a previous revision |
| `helm_uninstall_release` | Uninstall a release |
| `helm_dry_run_install` | Preview an installation without deploying |

### Validation

| Tool | Description |
|------|-------------|
| `helm_validate_values` | Validate values against the chart's JSON schema |
| `helm_render_manifests` | Render Kubernetes manifests from a chart |
| `helm_validate_manifests` | Validate rendered manifests for correctness |
| `helm_check_dependencies` | Check if chart dependencies are satisfied |
| `helm_get_installation_plan` | Generate an installation plan with resource estimates |

### Kubernetes

| Tool | Description |
|------|-------------|
| `kubernetes_get_cluster_info` | Get cluster information |
| `kubernetes_list_namespaces` | List all namespaces |
| `kubernetes_list_contexts` | List available kubeconfig contexts |
| `kubernetes_set_context` | Switch to a specific context |
| `kubernetes_get_helm_releases` | List all Helm releases in the cluster |
| `kubernetes_check_prerequisites` | Check cluster prerequisites for a chart |

### Monitoring

| Tool | Description |
|------|-------------|
| `helm_monitor_deployment` | Monitor deployment health after install/upgrade |
| `helm_get_release_status` | Get the current status of a release |

---

## Available Resources

| Resource URI | Description |
|--------------|-------------|
| `helm://releases` | List all Helm releases in the cluster |
| `helm://releases/{release_name}` | Detailed info for a specific release |
| `helm://charts` | List available charts across repositories |
| `helm://charts/{repo}/{name}` | Get chart metadata |
| `helm://charts/{repo}/{name}/readme` | Get chart README |
| `kubernetes://cluster-info` | Kubernetes cluster information |
| `kubernetes://namespaces` | List all namespaces |
| `helm://best_practices` | Helm best practices guide |

---

## Available Prompts

| Prompt | Description | Arguments |
|--------|-------------|-----------|
| `helm_workflow_guide` | End-to-end workflow documentation | — |
| `helm_quick_start` | Quick start for common operations | — |
| `helm_installation_guidelines` | Installation best practices | — |
| `helm_troubleshooting_guide` | Troubleshooting common issues | `error_type` |
| `helm_security_checklist` | Security considerations checklist | — |
| `helm_upgrade_guide` | Upgrade procedure for a chart | `chart_name` |
| `helm_rollback_procedures` | Rollback step-by-step guide | `release_name` |

---

## Usage

### Basic — installing a chart

```
"Install PostgreSQL from Bitnami in the database namespace"
```

The assistant will follow the safe deployment workflow automatically:
1. Search for the chart (`helm_search_charts`)
2. Validate values (`helm_validate_values`)
3. Preview with a dry-run (`helm_dry_run_install`)
4. Install (`helm_install_chart`)
5. Monitor the rollout (`helm_monitor_deployment`)

### Upgrading a release

```
"Upgrade my-app to version 2.0 with 3 replicas"
```

### Troubleshooting a deployment

```
"My pods are in CrashLoopBackOff after deploying redis"
```

The assistant will pull the `helm_troubleshooting_guide` prompt with `error_type="pod-crashloop"` and walk through the diagnosis.

### Rolling back

```
"Rollback my-release to the previous version"
```

### More examples

- "Search for nginx ingress charts"
- "List all Helm releases in the production namespace"
- "What are the security best practices for Helm deployments?"
- "Show me the installation plan for prometheus-stack"
- "Uninstall test-release from staging"

For detailed workflow guides and best practices, the assistant can access the `helm_workflow_guide` prompt or the `helm://best_practices` resource directly.

---

## Project Structure

```
helm-mcp-server/
├── helm_mcp_server/               # Main package
│   ├── tools/                     # MCP Tools
│   │   ├── discovery/             # Chart search, metadata, repo management
│   │   ├── installation/          # Install, upgrade, rollback, uninstall
│   │   ├── validation/            # Values + manifest validation
│   │   ├── kubernetes/            # Cluster operations (contexts, namespaces)
│   │   └── monitoring/            # Deployment health monitoring
│   ├── resources/                 # MCP Resources
│   │   ├── helm_resources.py      # Release resources
│   │   ├── chart_resources.py     # Chart resources
│   │   ├── kubernetes_resources.py# Cluster resources
│   │   └── static_resources.py    # Best practices guide
│   ├── prompts/                   # MCP Prompts
│   │   ├── installation_prompts.py
│   │   ├── troubleshooting_prompts.py
│   │   ├── security_prompts.py
│   │   ├── upgrade_prompts.py
│   │   ├── rollback_prompts.py
│   │   └── workflow_prompts.py
│   ├── services/                  # Business logic
│   │   ├── helm_service.py        # Helm CLI wrapper
│   │   ├── kubernetes_service.py  # kubectl / K8s API wrapper
│   │   └── validation_service.py  # Schema and manifest validation
│   ├── server/                    # FastMCP server setup
│   │   ├── bootstrap.py           # Tool/resource/prompt registration
│   │   ├── core.py                # Server initialization
│   │   └── middleware.py          # Request middleware
│   ├── exceptions/                # Custom exception types
│   ├── utils/                     # Utility functions
│   ├── static/                    # Static documentation
│   │   ├── HELM_BEST_PRACTICES.md
│   │   ├── HELM_WORKFLOW_GUIDE.md
│   │   └── HELM_MCP_INSTRUCTIONS.md
│   ├── config.py                  # Configuration management (env vars)
│   └── main.py                    # Application entry point
├── tests/                         # Test suite
├── Dockerfile                     # Container build
├── pyproject.toml                 # Metadata + dependencies
└── README.md                     # This file
```

---

## Roadmap

**Shipped:**

- [x] Full Helm lifecycle — search, install, upgrade, rollback, uninstall
- [x] Value validation against JSON schemas
- [x] Manifest rendering and validation before deployment
- [x] Dry-run support for safe previews
- [x] Multi-cluster / multi-context support
- [x] Deployment health monitoring
- [x] Write access control (`MCP_ALLOW_WRITE`)
- [x] Built-in workflow guides, security checklists, and troubleshooting prompts
- [x] Docker image with Helm + kubectl included
- [x] HTTP and stdio transport

**Coming next:**

- [ ] Comprehensive unit and integration test suite
- [ ] Authentication and authorization layer for secure, multi-tenant access
- [ ] OCI registry support for chart discovery
- [ ] Helm secrets integration (SOPS, sealed-secrets)
- [ ] Chart diff on upgrades (show what's changing before applying)
- [ ] Release comparison across environments
- [ ] Webhook notifications for deployment events

See [open issues](https://github.com/talkops-ai/talkops-mcp/issues) for the full list of proposed features.

---

## Contributing

Contributions are welcome. The process is straightforward:

1. Fork the repo
2. Create a branch (`git checkout -b feature/your-feature`)
3. Make your changes and commit
4. Push and open a PR

If you're considering something bigger, open an issue first so we can align on the approach.

---

## FAQ

<details>
<summary><b>Which MCP clients work with this?</b></summary>

Any MCP-compatible client that supports HTTP transport — Claude Desktop, Cline, or your own custom agent. Point the client at `http://localhost:8765/mcp`.
</details>

<details>
<summary><b>Does it actually run Helm commands or just simulate them?</b></summary>

It runs real Helm commands. The server wraps the Helm CLI and kubectl, executing them as subprocesses. This means your kubeconfig, RBAC permissions, and cluster state all apply as you'd expect.
</details>

<details>
<summary><b>Can I use it in read-only mode for safety?</b></summary>

Yes. Set <code>MCP_ALLOW_WRITE=false</code> and the server will only expose discovery, validation, and monitoring tools. All mutating operations (install, upgrade, rollback, uninstall) will be blocked. Dry-runs are always allowed.
</details>

<details>
<summary><b>What if I get connection timeout errors?</b></summary>

Increase your client's connection timeout. The server may take a moment to initialize. Set the client's <code>connect_timeout</code> to at least 60 seconds and <code>timeout</code> to 300 seconds. See the <a href="#troubleshooting">Troubleshooting</a> section for details.
</details>

<details>
<summary><b>Does it support multiple clusters?</b></summary>

Yes. The server can list all contexts from your kubeconfig and switch between them. Use <code>kubernetes_list_contexts</code> to see available clusters and <code>kubernetes_set_context</code> to switch.
</details>

<details>
<summary><b>Do I need Helm and kubectl installed locally?</b></summary>

Only if you're running from source. The Docker image includes both Helm v3 and kubectl — just mount your kubeconfig and go.
</details>

---

## Troubleshooting

### Connection Timeout Errors

If you see `httpx.ConnectTimeout` when connecting to the server, it's usually a client-side timeout issue. The server takes a few seconds to initialize and register all tools, resources, and prompts.

**Fix:** increase the client timeout:

```json
{
  "url": "http://localhost:8765/mcp",
  "transport": "http",
  "timeout": 300,
  "connect_timeout": 60
}
```

The server also has configurable timeouts: `MCP_HTTP_TIMEOUT` (default 300s), `MCP_HTTP_CONNECT_TIMEOUT` (default 60s), `MCP_HTTP_KEEPALIVE_TIMEOUT` (default 5s).

### Chart Not Found

1. Make sure the chart exists in the specified repository
2. Run `helm repo update` to refresh repository indexes
3. Double-check the repository name (e.g., `bitnami`, `argo`)

### Helm Operations Timing Out

Increase the Helm timeout:

```bash
export HELM_TIMEOUT=600  # 10 minutes
```

Or pass `-e HELM_TIMEOUT=600` when running with Docker.

---

## Security Considerations

- **Never hardcode secrets** in values files — use Kubernetes Secrets or external secret managers
- **Use namespace isolation** for different environments
- **Follow RBAC principles** — grant minimum required permissions
- **Pin chart versions** for reproducible deployments
- **Review rendered manifests** before applying to production
- **Use the `helm_security_checklist` prompt** for comprehensive guidance
- **Run in read-only mode** (`MCP_ALLOW_WRITE=false`) when the assistant only needs to observe

---

## License

Apache 2.0 — see [LICENSE](LICENSE).

---

## Contact

**TalkOps AI** — [github.com/talkops-ai](https://github.com/talkops-ai)

**Project:** [github.com/talkops-ai/talkops-mcp](https://github.com/talkops-ai/talkops-mcp)

**Discord:** [Join the community](https://discord.gg/tSN2Qn9uM8)

---

## Acknowledgments

- [Model Context Protocol](https://modelcontextprotocol.io/) — the protocol that makes this possible
- [FastMCP](https://github.com/jlowin/fastmcp) — Python MCP framework
- [Helm](https://helm.sh/) — Kubernetes package management
- [uv](https://github.com/astral-sh/uv) — Python package management
