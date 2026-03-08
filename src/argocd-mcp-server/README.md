<p align="center">
  <img src="https://argo-cd.readthedocs.io/en/stable/assets/logo.png" alt="ArgoCD MCP Server" width="140"/>
</p>

<h1 align="center">ArgoCD MCP Server</h1>

<p align="center">
  An MCP server that gives AI assistants full control over ArgoCD — from application discovery to GitOps deployments.
</p>

<p align="center">
  <a href="https://github.com/talkops-ai/talkops-mcp/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-Apache%202.0-blue.svg?style=flat-square" alt="License"/></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/Python-3.12%2B-3776AB.svg?style=flat-square&logo=python&logoColor=white" alt="Python 3.12+"/></a>
  <a href="https://modelcontextprotocol.io/"><img src="https://img.shields.io/badge/MCP-Model%20Context%20Protocol-4A90D9.svg?style=flat-square" alt="MCP"/></a>
  <a href="https://argo-cd.readthedocs.io/"><img src="https://img.shields.io/badge/ArgoCD-v2.x-0F1689.svg?style=flat-square&logo=argo&logoColor=white" alt="ArgoCD v2.x"/></a>
  <a href="https://discord.gg/tSN2Qn9uM8"><img src="https://img.shields.io/badge/Discord-Join%20Us-5865F2.svg?style=flat-square&logo=discord&logoColor=white" alt="Discord"/></a>
</p>

<p align="center">
  <a href="#getting-started">Quick Start</a> · <a href="https://github.com/talkops-ai/talkops-mcp/blob/main/src/argocd-mcp-server/USER_GUIDE.md">User Guide</a> · <a href="https://github.com/talkops-ai/talkops-mcp/issues/new?template=bug_report.md">Report Bug</a> · <a href="https://github.com/talkops-ai/talkops-mcp/issues/new?template=feature_request.md">Request Feature</a>
</p>

---

## Why ArgoCD MCP Server?

**The problem.** Managing Kubernetes applications via ArgoCD using GitOps principles is powerful, but diagnosing issues, monitoring rollouts, or safely orchestrating deployments often requires jumping between the UI, CLI, and Git repositories. You have to trace through application state, validate configurations, understand complex RBAC models, and painstakingly debug sync failures across multiple clusters.

AI assistants should be able to do all of this. But they can't — not without a structured interface to the ArgoCD API.

**What ArgoCD MCP Server does.**

It exposes the full ArgoCD lifecycle — discovery, configuration, deployment, monitoring, and rollback — as a set of MCP tools, resources, and prompts. Any MCP-compatible AI assistant (Claude, Cline, or your own agent) can use them to manage ArgoCD operations the way a senior Platform Engineer would: onboard repositories, validate application manifests, preview deployment diffs, execute syncs, and automatically troubleshoot issues when a deployment fails.

Three things make this different:

1. **Safety-first design.** Every mutating operation can be locked behind a write-access toggle (`MCP_ALLOW_WRITE`). Dry-runs are built natively into deployment operations. Deep validation happens before anything alters the GitOps state. The assistant operates with guardrails, keeping secrets out of its context window and enforcing read-only limits when exploring production.

2. **Full GitOps lifecycle, not just deployment.** Most ArgoCD integrations stop at triggering a sync. This server covers repository onboarding (HTTPS/SSH), project multi-tenancy configuration, application creation, drift detection, resource pruning, and root-cause analysis of deployment errors.

3. **Built-in operational knowledge.** The server ships with workflow guides for repository onboarding, full application deployments, diagnosing complex application issues, and emergency rollbacks — exposed as MCP prompts. The assistant doesn't just execute API calls; it follows GitOps best practices because the knowledge is baked into the protocol.

---

## Key Features

**Application Management**
- Create, update, and delete ArgoCD applications
- List applications across clusters with health and sync status
- Get detailed application information including resource breakdown
- Validate application configurations before deployment
- View application events and audit trails

**Deployment & Operations**
- Sync applications to desired state (with dry-run support)
- Get deployment diffs to preview changes
- Monitor sync operations in real-time
- Rollback to previous versions with impact analysis
- Prune orphaned resources and execute hard/soft refreshes
- Cancel ongoing deployments

**Repository Management**
- Onboard GitHub repositories via HTTPS or SSH
- Validate repository connections before onboarding
- List, manage, and delete registered repositories
- Secure credential handling (never exposed to LLM)
- Generate Kubernetes secret manifests for disaster recovery

**Project Management (Multi-Tenancy)**
- Create ArgoCD projects with RBAC policies
- Configure source repositories, destination clusters, and namespaces
- Whitelist/blacklist cluster and namespace resources
- Manage project lifecycle and generate AppProject YAML manifests

**Monitoring & Debugging**
- Real-time application health metrics and deployment event streams
- Smart log analysis with automatic error detection
- Cluster-wide health and active sync operation tracking

**Built-in Guidance**
- Automated issue diagnosis workflows with recommendations
- End-to-end repository integrations and deployment guides
- Safe rollback decision and multi-tenancy setup procedures

---

## Architecture

The server is organized into layered service modules — tools on top, business logic in the middle, and ArgoCD API interactions at the bottom.

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
          │                    │                    │
    ┌─────▼─────┐      ┌──────▼──────┐      ┌──────▼──────┐
    │   Tools   │      │  Resources  │      │   Prompts   │
    │           │      │             │      │             │
    │ Apps      │      │ argocd://   │      │ Deployment  │
    │ Deploy    │      │    apps     │      │ Repo Setup  │
    │ Repos     │      │    metrics  │      │ Debugging   │
    │ Projects  │      │    sync     │      │ Rollback    │
    │ Diagnose  │      │             │      │ Projects    │
    │           │      │             │      │             │
    └─────┬─────┘      └──────┬──────┘      └──────┬──────┘
          │                   │                     │
          └───────────────────┼─────────────────────┘
                              │
                    ┌─────────▼──────────┐
                    │   Service Layer    │
                    │                    │
                    │  argocd_service.py │
                    │  argocd_mgmt.py    │
                    └─────────┬──────────┘
                              │
                    ┌─────────▼──────────┐
                    │     ArgoCD API     │
                    │     (HTTP/GRPC)    │
                    └────────────────────┘
```

**How it works in practice:**

1. An AI assistant connects to the server over HTTP (or stdio)
2. It discovers available tools, resources, and prompts automatically
3. When a user asks something like "Deploy my application from GitHub to the production cluster," the assistant coordinates repository onboarding, application creation, diff previews, sync execution, and monitoring.
4. The service layer translates tool calls into precise ArgoCD API requests, securely managing authentication tokens and credentials behind the scenes.
5. Results flow back to the assistant, giving it observability into real-time rollout status and application health.

---

## Table of Contents

- [Why ArgoCD MCP Server?](#why-argocd-mcp-server)
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
- [Security Considerations](#security-considerations)
- [Roadmap](#roadmap)
- [Contributing](#contributing)
- [FAQ](#faq)
- [Troubleshooting](#troubleshooting)
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
| **GitOps** | ArgoCD API (v2.x) |
| **Transport** | HTTP/SSE · stdio |
| **Infrastructure** | Docker · [uv](https://github.com/astral-sh/uv) |

---

## Getting Started

### Prerequisites

- **Docker** (recommended) or **Python 3.12+** (for local dev)
- **ArgoCD Server**: Running ArgoCD instance (v2.x)
- **Authentication**: ArgoCD API token
- **Git Credentials**: GitHub personal access token (HTTPS) or SSH private key (SSH)

**Getting the ArgoCD Token:**

You can quickly get a token using our helper script:

```bash
cd argocd_mcp_server/scripts
export ARGOCD_SERVER="https://localhost:8080"
export ARGOCD_USERNAME="admin"
export ARGOCD_PASSWORD="your-password"
export ARGOCD_VERIFY_TLS="false"

python fetch_argocd_token.py --output env
# Output: export ARGOCD_AUTH_TOKEN='eyJhbGc...'
```

### Quick Start with Docker (recommended)

Pull the image from Docker Hub and run:

```bash
docker run --rm -it \
  -p 8770:8770 \
  -e ARGOCD_SERVER_URL="https://host.docker.internal:8080" \
  -e ARGOCD_AUTH_TOKEN="your-token-here" \
  -e MCP_PORT=8770 \
  -e MCP_PATH="/mcp" \
  -e ARGOCD_INSECURE="true" \
  -e GIT_PASSWORD="your-github-pat" \
  -e MCP_ALLOW_WRITE=true \
  -e GIT_USERNAME="your-github-username" \
  talkopsai/argocd-mcp-server:latest
```

The server is now listening on `http://localhost:8770/mcp`. Note: using `host.docker.internal` is helpful if testing against local port-forwarded ArgoCD instance.

Point your MCP client at it:

```json
{
  "mcpServers": {
    "argocd-mcp-server": {
      "transport": "sse",
      "url": "http://localhost:8770/mcp",
      "description": "ArgoCD MCP Server for GitOps application management"
    }
  }
}
```

### Build from Source (Docker)

If you prefer to build the image yourself:

```bash
cd talkops-mcp/src/argocd-mcp-server
docker build -t talkopsai/argocd-mcp-server:latest .

docker run --rm -it \
  -p 8770:8770 \
  -e ARGOCD_SERVER_URL="https://host.docker.internal:8080" \
  -e ARGOCD_AUTH_TOKEN="your-token-here" \
  -e MCP_PORT=8770 \
  -e MCP_PATH="/mcp" \
  -e ARGOCD_INSECURE="true" \
  -e MCP_ALLOW_WRITE=true \
  talkopsai/argocd-mcp-server:latest
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
cd talkops-mcp/src/argocd-mcp-server

# Create virtual environment and install
uv venv --python=3.12
source .venv/bin/activate  # On Unix/macOS
# .venv\Scripts\activate   # On Windows

uv pip install -e .
```

3. Run the server:

```bash
export ARGOCD_SERVER_URL="https://argocd.example.com"
export ARGOCD_AUTH_TOKEN="your-token"
uv run argocd-mcp-server
```

---

## Configuration

All configuration is via environment variables. Sensible defaults are built in — you only need to override what you want to change.

### Server Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `MCP_SERVER_NAME` | `argocd-mcp-server` | Server name identifier |
| `MCP_SERVER_VERSION` | `0.1.0` | Server version string |
| `MCP_TRANSPORT` | `http` | Transport mode: `http` (HTTP/SSE) or `stdio` |
| `MCP_HOST` | `0.0.0.0` | Host address for HTTP/SSE server |
| `MCP_PORT` | `8770` | Port for HTTP/SSE server |
| `MCP_PATH` | `/mcp` | SSE endpoint path |
| `MCP_ALLOW_WRITE` | `false` | Enable write operations (see below) |
| `MCP_LOG_LEVEL` | `INFO` | Log level: `DEBUG`, `INFO`, `WARNING`, `ERROR` |

### ArgoCD & Git Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `ARGOCD_SERVER_URL` | `https://argocd-server...` | ArgoCD server URL |
| `ARGOCD_AUTH_TOKEN` | *(required)* | ArgoCD API authentication token |
| `ARGOCD_INSECURE` | `false` | Skip TLS verification |
| `ARGOCD_TIMEOUT` | `300` | Timeout in seconds for API operations |
| `GIT_USERNAME` | `""` | Git username |
| `GIT_PASSWORD` | *(required for HTTPS)*| GitHub personal access token |
| `SSH_PRIVATE_KEY_PATH`| `~/.ssh/id_rsa` | Path to SSH private key |

### Write Access Control

The `MCP_ALLOW_WRITE` flag is the primary safety mechanism. It controls whether the server accepts mutating operations against the ArgoCD API.

**When `false` (default) — read-only mode:** only safe operations are allowed:

| Allowed | Blocked |
|---------|---------|
| List, discover and validate applications/projects | `create_application`, `update_application` |
| Application diff previews and sync status monitoring | `sync_application` (unless `dry_run=true`) |
| Application logs and event analysis | `rollback_application`, `delete_application` |
| Repository and Project visibility | `onboard_repository_*`, `create_project` |
| Dry-run syncs | All DELETE operations |

**When `true` — write mode:** everything is enabled, giving the assistant full capability to deploy, sync, rollback, onboard, and manage projects.

**Use case:** By default keep it `false` for safe cluster observation. Set to `true` when testing workflows, onboarding, or deploying.

---

## Available Tools

### Application Management

| Tool | Description | Write Access Required |
|------|-------------|-----------------------|
| `list_applications` | List all applications in a cluster | No |
| `get_application_details` | Get detailed application information | No |
| `create_application` | Create a new ArgoCD application | Yes |
| `update_application` | Update application configuration | Yes |
| `delete_application` | Delete an ArgoCD application | Yes |
| `validate_application_config` | Validate application configuration | No |
| `get_application_events` | Get Kubernetes events for application | No |

### Deployment & Operations

| Tool | Description | Write Access Required |
|------|-------------|-----------------------|
| `sync_application` | Sync application to desired state | Yes (except dry-run) |
| `get_application_diff` | Preview changes before deployment | No |
| `get_sync_status` | Get current sync operation status | No |
| `rollback_application` | Rollback to previous/specific revision | Yes |
| `get_application_logs` | Get application logs with error detection | No |
| `prune_resources` | Remove resources not in desired state | Yes |
| `hard_refresh` / `soft_refresh` | Force or soft refresh application state | Yes |
| `cancel_deployment` | Cancel ongoing sync operation | Yes |

### Repository & Project Management

| Tool | Description | Write Access Required |
|------|-------------|-----------------------|
| `onboard_repository_https` / `ssh`| Onboard GitHub repository | Yes |
| `list_repositories` / `get_repository`| View registered repositories | No |
| `validate_repository_connection` | Validate connectivity before onboarding | No |
| `create_project` | Create ArgoCD project with RBAC | Yes |
| `list_projects` / `get_project` | View ArgoCD projects | No |

---

## Available Resources

| Resource URI | Description | Update Frequency |
|--------------|-------------|------------------|
| `argocd://applications/{cluster}` | List all applications and their state | Every 5s |
| `argocd://application-metrics/{cluster}/{app}` | Real-time application metrics | Every 10s |
| `argocd://sync-operations/{cluster}` | Active sync operations | Every 2s |
| `argocd://deployment-events/{cluster}` | Deployment event stream | Real-time |
| `argocd://cluster-health/{cluster}` | Overall cluster health | Every 30s |

---

## Available Prompts

| Prompt | Description |
|--------|-------------|
| `onboard_github_repository` | Step-by-step repository onboarding |
| `full_application_deployment` | End-to-end deployment from repo to app |
| `debug_application_issues` | Comprehensive troubleshooting |
| `rollback_decision` | Guided rollback with impact analysis |
| `setup_argocd_project` | Multi-tenancy project setup |
| `deploy_new_version` | Guided deployment workflow |
| `post_deployment_validation`| Comprehensive health check |

---

## Usage

**New to the ArgoCD MCP Server?**
See the **[Complete User Guide](./USER_GUIDE.md)** for detailed examples of how to interact with the server using natural language.

### Basic — Deploying an Application

```
"Deploy my application from https://github.com/myorg/myapp to production cluster"
```

The assistant will follow a safe deployment workflow:
1. Onboard repository (if needed) using `onboard_github_repository`
2. Create ArgoCD application
3. Show deployment preview diff
4. Execute deployment via `sync`
5. Validate success

### Debugging a failing app

```
"My app 'payment-service' is not working in production, help me debug it"
```

The assistant invokes `debug_application_issues` to:
1. Analyze application status and pod health
2. Check logs for errors automatically
3. Review Kubernetes events
4. Provide recommendations and root cause

### Rolling Back

```
"URGENT: Latest deployment of checkout-service is broken, rollback immediately!"
```

The assistant reviews application history using the `rollback_decision` workflow, predicts impact, executes the rollback, and monitors restoration.

---

## Project Structure

```
argocd-mcp-server/
├── argocd_mcp_server/         # Main package
│   ├── tools/                 # MCP Tools (29 total)
│   │   ├── application_manager/
│   │   ├── deployment_executor/
│   │   ├── repository_mgmt/
│   │   └── project_mgmt/
│   ├── resources/             # Real-time data streams & static resources
│   ├── prompts/               # Deployment, repo, and debug workflows
│   ├── services/              # ArgoCD API client layer
│   ├── server/                # FastMCP server setup
│   ├── utils/                 # Security and helpers
│   └── main.py
├── scripts/                   # Helper scripts like fetch_argocd_token.py
├── tests/                     # Test suite
├── USER_GUIDE.md              # Complete end-user workflow examples
├── Dockerfile
├── pyproject.toml
└── README.md
```

---

## Security Considerations

- **Never hardcode secrets** in application values or pass credentials directly to the AI — use environment variables (`GIT_PASSWORD`, `ARGOCD_AUTH_TOKEN`, `SSH_PRIVATE_KEY_PATH`).
- **Run in read-only mode** (`MCP_ALLOW_WRITE=false`) when the assistant only needs to observe, summarize, and debug. Enable write mode only when orchestration execution is required.
- **Enforce TLS verification**: Do not use `ARGOCD_INSECURE=true` in production environments — verify TLS certificates.

---

## Roadmap

**Shipped:**

- [x] Full GitOps deployment lifecycle (create, diff, sync, rollback)
- [x] Respository management (HTTPS and SSH onboarding)
- [x] Multi-tenancy Project configuration management
- [x] Diagnostic workflows (intelligent logs analysis and events)
- [x] Streaming resources for real-time observability
- [x] Safe Write-access controls (`MCP_ALLOW_WRITE`)
- [x] Best-practice prompting for autonomous operations

**Coming next:**

- [ ] Comprehensive ApplicationSet management
- [ ] Helm value overrides native integration
- [ ] Integration with Argo Rollouts MCP Server for progressive delivery 
- [ ] Fine-grained RBAC mappings internally within MCP
- [ ] ChatOps notification hook setup

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
Any MCP-compatible client that supports HTTP/SSE transport — Claude Desktop, Cline, or custom agents.
</details>

<details>
<summary><b>Does the AI get access to my ArgoCD passwords?</b></summary>
No. The authentication token and Git credentials are provided to the server instance via environment variables. The MCP tools do not accept credentials as parameters, ensuring they never enter the conversation transcript.
</details>

<details>
<summary><b>Can I test deployments without actually deploying?</b></summary>
Yes. The <code>sync_application</code> tool natively supports a <code>dry_run</code> mode, and the assistant uses it extensively in its workflows along with evaluating application diffs.
</details>

---

## Troubleshooting

### Connection Timeout Errors

If you see timeout errors when connecting to the server, it's usually a client-side timeout issue or ArgoCD API latency.

**Fix:** increase the client timeout in your MCP configuration:

```json
{
  "url": "http://localhost:8770/mcp",
  "transport": "sse",
  "timeout": 300.0,
  "connect_timeout": 60.0
}
```

### ArgoCD Connection Errors

Ensure `ARGOCD_SERVER_URL` and `ARGOCD_AUTH_TOKEN` are correctly set. For local testing with self-signed certs, test with `ARGOCD_INSECURE=true`.

### Write Operations Blocked

If you see `ArgoCD {operation} is not allowed` or similar phrasing, the server is in read-only mode to prevent unintended cluster modifications. Restart the server with `MCP_ALLOW_WRITE=true` to enable changes.

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
- [ArgoCD](https://argo-cd.readthedocs.io/) — declarative, GitOps continuous delivery
- [uv](https://github.com/astral-sh/uv) — Python package management
