<p align="center">
  <img src="https://kargo.akuity.io/v1.0.0/assets/images/kargo-icon-d3fc04fccf54a8677ba1a069502b66cb.png" alt="Kargo MCP Server" width="140"/>
</p>

<h1 align="center">Kargo MCP Server</h1>

<p align="center">
  An MCP server that gives AI assistants full control over Akuity Kargo — orchestrating continuous promotion, verification, and progressive delivery pipelines across Kubernetes environments.
</p>

<p align="center">
  <a href="https://github.com/talkops-ai/talkops-mcp/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-Apache%202.0-blue.svg?style=flat-square" alt="License"/></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/Python-3.10%2B-3776AB.svg?style=flat-square&logo=python&logoColor=white" alt="Python 3.10+"/></a>
  <a href="https://modelcontextprotocol.io/"><img src="https://img.shields.io/badge/MCP-Model%20Context%20Protocol-4A90D9.svg?style=flat-square" alt="MCP"/></a>
  <a href="https://kargo.akuity.io/"><img src="https://img.shields.io/badge/Akuity%20Kargo-v1.0-2E8555.svg?style=flat-square" alt="Kargo"/></a>
  <a href="https://discord.gg/tSN2Qn9uM8"><img src="https://img.shields.io/badge/Discord-Join%20Us-5865F2.svg?style=flat-square&logo=discord&logoColor=white" alt="Discord"/></a>
</p>

<p align="center">
  <a href="#getting-started">Quick Start</a> · <a href="docs/workflow-docs/WORKFLOW_JOURNEYS.md">User Guide</a> · <a href="https://github.com/talkops-ai/talkops-mcp/issues/new?template=bug_report.md">Report Bug</a> · <a href="https://github.com/talkops-ai/talkops-mcp/issues/new?template=feature_request.md">Request Feature</a>
</p>

---

## Why Kargo MCP Server?

**The problem.** Managing multi-stage deployments across environments (Dev → Staging → Prod) often requires jumping between Argo CD UIs, GitOps repositories, and CI pipelines. Figuring out exactly which Git commit or container image is running in which environment, and safely promoting those artifacts forward, is a fragmented and manual process.

AI assistants should be able to orchestrate these delivery pipelines safely. But they can't — not without deeply understanding Kargo Projects, Stages, Warehouses, Freight, and Promotion logic.

**What Kargo MCP Server does.**

It exposes the full progressive delivery and promotion lifecycle — Pipeline DAG topology, Freight tracking, Manual Approvals, and Promotions — as a set of MCP tools, resources, and prompts. Any MCP-compatible AI assistant (Claude, Cline, or your own agent) can use them to manage deployments the way a senior release engineer would.

Three things make this different:

1. **Declarative Pipeline Management.** The server has built-in execution tools to query the exact DAG topology of your environments. Ask the assistant "What is running in Staging?" and it instantly correlates the running Freight (images, helm charts, commits) across your Kargo project.

2. **Intelligent Spec Building.** Users never write raw Kargo YAML. Warehouse subscriptions (image, git, chart) and PromotionTask steps are built from simple, intent-based parameters. Three built-in presets (`gitops-image-update`, `gitops-kustomize`, `gitops-helm-template`) cover 90% of GitOps workflows out of the box.

3. **Intelligent Lifecycle Control.** This server doesn't just push YAML. It allows the AI to manage live promotions: approving freight, creating promotions, aborting stuck releases, and reverifying stages seamlessly.

4. **Built-in Playbooks.** The server ships with workflow paths for Pipeline Onboarding, Manual Approvals, Rollbacks, and Troubleshooting — exposed as MCP prompts. The assistant doesn't guess; it follows battle-tested deployment playbooks baked into the protocol.

---

## Key Features

**Pipeline Tracking**
- Map the DAG topology of your delivery pipelines (Stages & Warehouses).
- Track the flow of `Freight` (Artifacts) across multiple environments.

**Lifecycle Orchestration**
- Trigger artifact discovery via Warehouse refreshes.
- Approve specific freight for high-risk stages.
- Create and execute `Promotion` tasks to move freight through the pipeline.
- Abort stuck promotions safely.

**Observation & Context**
- Read real-time Stage phases and current running Freight.
- View cluster-wide diagnostic status for your Kargo projects.
- Extract detailed YAML manifests instantly for deeper diagnostics.

**Validation & Safety**
- Re-trigger Analysis and Verifications for flaky environments.
- Rollback mechanisms built-in using a "Roll Forward" paradigm.

**Built-in Guidance**
- Pre-loaded AI prompts guiding conversational Pipeline Onboarding, Approvals, Promotions, and Troubleshooting.

---

## Architecture

The server is organized into layered service modules — tools on top, business logic in the middle, and the Python Kubernetes client at the bottom.

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
    │ Warehouse │      │ kargo://    │      │ Onboarding  │
    │ Stage     │      │    //       │      │ Approval    │
    │ Freight   │      │             │      │ Promotion   │
    │ Promotion │      │             │      │ Rollback    │
    │ Abort     │      │             │      │ Troubleshoot│
    │           │      │             │      │             │
    └─────┬─────┘      └──────┬──────┘      └──────┬──────┘
          │                   │                     │
          └───────────────────┼─────────────────────┘
                              │
                    ┌─────────▼──────────┐
                    │   Service Layer    │
                    │                    │
                    │ kargo_service.py   │
                    └─────────┬──────────┘
                              │
                    ┌─────────▼──────────┐
                    │ Python K8s Client  │
                    │ (API interaction)  │
                    └────────────────────┘
```

**How it works in practice:**

1. An AI assistant connects to the server over HTTP (or stdio).
2. It discovers the extensive Kargo-centric tools and resources automatically.
3. When a user asks something like "Promote the latest Staging payload to Production", the assistant calls the appropriate tools in sequence — verify stage, check freight, approve, promote.
4. Results flow back to the assistant, which continuously monitors progress via resources.

---

## Table of Contents

- [Why Kargo MCP Server?](#why-kargo-mcp-server)
- [Key Features](#key-features)
- [Architecture](#architecture)
- [Tech Stack](#tech-stack)
- [Getting Started](#getting-started)
- [Configuration](#configuration)
- [Available Tools](#available-tools)
- [Available Resources](#available-resources)
- [Available Prompts](#available-prompts)
- [Project Structure](#project-structure)
- [Contributing](#contributing)

---

## Tech Stack

| Category | Technologies |
|----------|-------------|
| **Language** | Python 3.12+ |
| **MCP Framework** | [FastMCP](https://github.com/jlowin/fastmcp) |
| **Protocol** | [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) |
| **Kubernetes** | Kargo CRDs · K8s Python Client |
| **Transport** | HTTP · stdio |
| **Infrastructure** | Docker · [uv](https://github.com/astral-sh/uv) |

---

## Getting Started

### Prerequisites

- **Docker** (recommended) or **Python 3.10+** (for local dev)
- **Access to a Kubernetes cluster** with a valid kubeconfig
- **Akuity Kargo** installed on the target cluster.

### Quick Start with Docker (recommended)

Pull the image and run it:

```bash
docker run --rm -it \
  -p 8766:8766 \
  -v ~/.kube:/app/.kube:ro \
  -e K8S_KUBECONFIG=/app/.kube/config \
  talkopsai/kargo-mcp-server:latest
```

> **Tip:** Mount the full `~/.kube` directory (not just `config`) so certificate paths referenced in your kubeconfig (e.g. minikube, kind) are available inside the container.

That's it. The server is now listening on `http://localhost:8766/mcp`.

Point your MCP client at it:

```json
{
  "mcpServers": {
    "kargo-mcp": {
      "url": "http://localhost:8766/mcp",
      "description": "MCP Server for managing Kargo pipelines and promotions"
    }
  }
}
```

### From Source (Python)

For development or if you want to run without Docker:

```bash
# Install uv if not already installed
curl -LsSf https://astral.sh/uv/install.sh | sh

# Clone the repository
git clone https://github.com/talkops-ai/talkops-mcp.git
cd talkops-mcp/src/kargo-mcp-server

# Create virtual environment and install
uv sync
source .venv/bin/activate

uv run kargo-mcp-server
```

---

## Configuration

All configuration is via environment variables.

### Server Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `MCP_SERVER_NAME` | `kargo-mcp-server`| Server name identifier |
| `MCP_TRANSPORT` | `http` | Transport mode: `http` or `stdio` |
| `MCP_HOST` | `0.0.0.0` | Host address for HTTP server |
| `MCP_PORT` | `8766` | Port for HTTP server |
| `MCP_LOG_LEVEL` | `INFO` | Log level: `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `MCP_ALLOW_WRITE` | `false` | Set to `true` to enable write-mutations (Promotions, Approvals, Aborts) |

### Kargo & Kubernetes

| Variable | Default | Description |
|----------|---------|-------------|
| `K8S_KUBECONFIG` | `~/.kube/config` | Path to kubeconfig file |
| `K8S_CONTEXT` | *(empty)* | Specific K8s context to force |
| `KARGO_CONTROLLER_NAMESPACE` | `kargo` | Namespace where Kargo controller runs |

---

## Available Tools

### Unified Management & Observation
| Tool | Description |
|------|-------------|
| `kargo_project_mgmt` | Manage Kargo projects (create, update, delete, list, get) |
| `kargo_stage_mgmt` | Manage stages (list, get, upsert, reverify) |
| `kargo_warehouse_mgmt` | Manage warehouses (list, get, upsert, refresh). Upsert uses declarative subscriptions — no raw YAML needed |
| `kargo_freight_mgmt` | Manage freight payloads (list, get, approve) |
| `kargo_promotion_mgmt` | Manage promotions (list, get, create, abort) |
| `kargo_promotion_task_mgmt` | Manage promotion tasks (list, get, upsert). Supports preset-based creation (`gitops-image-update`, `gitops-kustomize`, `gitops-helm-template`) or custom steps |
| `kargo_credentials_mgmt` | Manage repository credentials (list, get, create, delete) for Git/Helm/Image registries |
| `kargo_describe_topology` | Returns the DAG structure linking Warehouses and Stages |

---

## Available Resources

| Resource URI | Description |
|--------------|-------------|
| `kargo://projects` | List all Kargo projects |
| `kargo://projects/{project}`| Details of a specific project |
| `kargo://projects/{project}/stages`| All stages in a project |
| `kargo://projects/{project}/stages/{stage}` | Real-time health and phase of a stage |
| `kargo://projects/{project}/warehouses/{warehouse}` | Source artifact configuration |
| `kargo://projects/{project}/freight/{freight_id}` | Detailed artifact breakdown |
| `kargo://projects/{project}/promotions/{promotion}` | Live promotion task trace |

*Note: Individual entity resources (e.g., `{stage}`, `{freight_id}`) return a Markdown-formatted JSON summary followed by the full YAML manifest equivalent for detailed context ingestion.*

---

## Usage

Supported workflows with prompt examples and links to detailed guides:

| Workflow | Prompt Example | Documentation |
|----------|----------------|---------------|
| **Pipeline Onboarding** — Discover DAG | `"Verify the staging-to-prod promotion pipeline for the 'demo-project' project."` | [ONBOARDING_TEST_GUIDE.md](docs/workflow-docs/ONBOARDING_TEST_GUIDE.md) |
| **Manual Approval** — Gate high-risk stages | `"Find the latest freight for 'prod' in 'demo-project' and approve it."` | [APPROVAL_TEST_GUIDE.md](docs/workflow-docs/APPROVAL_TEST_GUIDE.md) |
| **Promotion Execution** — Move freight | `"Promote the currently approved freight to the 'prod' stage in 'demo-project'."` | [PROMOTION_TEST_GUIDE.md](docs/workflow-docs/PROMOTION_TEST_GUIDE.md) |
| **Emergency Rollback** — Roll Forward paradigm | `"Abort the stuck promotion in 'prod' and rollback to the previous stable freight ID."` | [ROLLBACK_TEST_GUIDE.md](docs/workflow-docs/ROLLBACK_TEST_GUIDE.md) |
| **Troubleshooting** — Diagnostics | `"Diagnose why the 'test' stage in 'demo-project' is degraded and not promoting."` | [TROUBLESHOOTING_TEST_GUIDE.md](docs/workflow-docs/TROUBLESHOOTING_TEST_GUIDE.md) |

### Guided Prompts

Use these MCP prompts to guide your AI assistant step-by-step through complex Kargo workflows.

| Prompt | Use Case |
|--------|----------|
| `kargo-pipeline-onboarding-guided`| Walkthrough for discovering and verifying a new pipeline |
| `kargo-approval-guided` | Workflow for safely identifying and approving Freight |
| `kargo-promotion-guided`| Guide to executing and verifying a promotion |
| `kargo-rollback-guided` | Playbook for rolling back a broken stage using the "Roll Forward" paradigm |
| `kargo-troubleshoot-guided`| Diagnostic steps for fixing broken or stuck promotions |

See [WORKFLOW_JOURNEYS.md](docs/workflow-docs/WORKFLOW_JOURNEYS.md) for the full workflow reference detailing exactly how tools and resources coordinate under the hood.

---

## Project Structure

```text
kargo-mcp-server/
├── kargo_mcp_server/              # Main package
│   ├── tools/                     # Mutating & Read Tools
│   │   ├── warehouse/             # Warehouse management (declarative subscriptions)
│   │   ├── promotion_task/        # PromotionTask management (preset-based)
│   │   ├── stage/                 # Stage management
│   │   ├── freight/               # Freight management
│   │   ├── promotion/             # Promotion management
│   │   ├── credentials/           # Repository credential management
│   │   ├── diagnostics/           # Pipeline topology diagnostics
│   │   └── project/               # Project management
│   ├── resources/                 # Read-only State via kargo:// URIs
│   ├── prompts/                   # Guided Workflow Prompts
│   ├── services/                  # Core K8s API integration
│   ├── models/                    # Pydantic schema validation
│   ├── utils/                     # Spec builders & helpers
│   │   ├── warehouse_spec_builder.py     # Subscription → WarehouseSpec
│   │   └── promotion_task_spec_builder.py # Preset → PromotionTaskSpec
│   ├── static/                    # Best practices & step catalogue
│   ├── exceptions/                # Error typing
│   ├── config.py                  # Env config
│   └── main.py                    # FastMCP Entry point
├── docs/                          # Deep workflow guides
├── tests/                         # Pytest suite
├── pyproject.toml                 # uv dependency management
└── README.md                      # This file
```

---

## Contributing

Contributions are welcome! Please open an issue first to discuss any major changes.

1. Fork the repo
2. Create a branch (`git checkout -b feature/your-feature`)
3. Make your changes and commit
4. Push and open a PR

## License

Apache 2.0 — see [LICENSE](../../LICENSE).
