<p align="center">
  <img src="../../assets/logo.png" alt="ArgoFlow MCP Server" width="140" onError="this.style.display='none'"/>
</p>

<h1 align="center">Argo Rollout MCP Server</h1>

<p align="center">
  An MCP server that gives AI assistants full control over Kubernetes progressive delivery — from scaling deployments to orchestrating canary network traffic.
</p>

<p align="center">
  <a href="https://github.com/talkops-ai/talkops-mcp/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-Apache%202.0-blue.svg?style=flat-square" alt="License"/></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/Python-3.10%2B-3776AB.svg?style=flat-square&logo=python&logoColor=white" alt="Python 3.10+"/></a>
  <a href="https://modelcontextprotocol.io/"><img src="https://img.shields.io/badge/MCP-Model%20Context%20Protocol-4A90D9.svg?style=flat-square" alt="MCP"/></a>
  <a href="https://argoproj.github.io/argo-rollouts/"><img src="https://img.shields.io/badge/Argo%20Rollouts-v1.6-EF7B4D.svg?style=flat-square&logo=argo&logoColor=white" alt="Argo Rollouts"/></a>
  <a href="https://discord.gg/tSN2Qn9uM8"><img src="https://img.shields.io/badge/Discord-Join%20Us-5865F2.svg?style=flat-square&logo=discord&logoColor=white" alt="Discord"/></a>
</p>

<p align="center">
  <a href="#getting-started">Quick Start</a> · <a href="docs/workflow-docs/WORKFLOW_JOURNEYS.md">User Guide</a> · <a href="https://github.com/talkops-ai/talkops-mcp/issues/new?template=bug_report.md">Report Bug</a> · <a href="https://github.com/talkops-ai/talkops-mcp/issues/new?template=feature_request.md">Request Feature</a>
</p>

---

## Why Argo Rollout MCP Server?

**The problem.** Moving from standard Kubernetes Deployments to progressive delivery is painful. You have to write massive Rollout YAML files, duplicate your services, and set up complex Prometheus queries just to make sure a deployment doesn't crash your system. And once a canary is running, you're constantly refreshing dashboards and running `kubectl` to figure out when it's safe to promote or abort.

AI assistants should be able to orchestrate this safely. But they can't — not without deeply understanding Argo Rollout structures, zero-downtime overlaps, and your live cluster state.

**What Argo Rollout MCP Server does.**

It exposes the full progressive delivery lifecycle — K8s deployment validation, YAML generation, canary stepping, blue-green cutovers, and health monitoring — as a set of MCP tools, resources, and prompts. Any MCP-compatible AI assistant (Claude, Cline, or your own agent) can use them to manage deployments the way a senior release engineer would.

Three things make this different:

1. **Zero YAML Onboarding.** The server has built-in execution generators. Ask the assistant to migrate an app, and it auto-fetches the live K8s Deployment, preserves all resource limits, probes, and env vars, and generates the exact Rollout CRD and Services needed directly into the cluster. No copy-pasting required.

2. **Intelligent Lifecycle Control.** This server doesn't just push YAML. It allows the AI to manage the live rollout: pausing, resuming, promoting, aborting, and seamlessly linking `AnalysisTemplate` CRDs to Prometheus for automated health checks.

3. **Built-in Playbooks.** The server ships with workflow paths for A/B testing, cost-aware deployments, and guided canary rollouts — exposed as MCP prompts. The assistant doesn't guess; it follows battle-tested deployment playbooks baked into the protocol.

---

## Key Features

**Deployment & Migration**
- Evaluate K8s Deployments for Rollout readiness
- Automatically convert Deployments into Rollouts (direct or workloadRef for Argo CD–managed apps)
- Convert Rollouts back into standard Deployments

**Lifecycle Orchestration**
- Create complex Canary, Blue-Green, and A/B configurations
- Update container images natively to trigger rollouts
- Promote canaries to the next step, or fully to 100%
- Pause and resume active progressive rollouts safely

**Observation & Context**
- Read real-time Rollout statuses (phase, ready replicas)
- View cluster-wide active traffic strategies
- Audit historical ReplicaSet hashes natively

**Validation & Safety**
- Instant emergency aborts throwing traffic back to stable
- Wrap Prometheus queries into AnalysisTemplates
- Deploy intelligent ML-based promotion flows

**Multi-Cluster Support**
- Connect natively across namespaces securely using `KUBECONFIG`

**Built-in Guidance**
- Pre-loaded AI prompts guiding conversational Canary, Blue-Green, and Cost-Aware progressive delivery

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
    │ Convert   │      │ argorollout:│      │ Onboarding  │
    │ Deploy    │      │    //       │      │ Canary      │
    │ Promote   │      │             │      │ Blue-Green  │
    │ Analysis  │      │             │      │ Cost-aware  │
    │ Abort     │      │             │      │             │
    │           │      │             │      │             │
    └─────┬─────┘      └──────┬──────┘      └──────┬──────┘
          │                   │                     │
          └───────────────────┼─────────────────────┘
                              │
                    ┌─────────▼──────────┐
                    │   Service Layer    │
                    │                    │
                    │ argo_service.py    │
                    │ generator_service  │
                    │ orchestration      │
                    └─────────┬──────────┘
                              │
                    ┌─────────▼──────────┐
                    │ Python K8s Client  │
                    │ (API interaction)  │
                    └────────────────────┘
```

**How it works in practice:**

1. An AI assistant connects to the server over HTTP (or stdio)
2. It discovers the extensive Argo-centric tools and resources automatically
3. When a user asks something like "Convert my staging frontend to a Canary", the assistant calls the appropriate tools in sequence — validate, generate, apply
4. Every mutating action translates into declarative K8s API patches
5. Results flow back to the assistant, which continuously monitors progress via resources

---

## Table of Contents

- [Why Argo Rollout MCP Server?](#why-argo-rollout-mcp-server)
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
- [Troubleshooting](#troubleshooting)
- [Security Considerations](#security-considerations)
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
| **Kubernetes** | Argo Rollouts CRDs · K8s Python Client |
| **Transport** | HTTP · stdio |
| **Infrastructure** | Docker · [uv](https://github.com/astral-sh/uv) |

---

## Getting Started

### Prerequisites

- **Docker** (recommended) or **Python 3.10+** (for local dev)
- **Access to a Kubernetes cluster** with a valid kubeconfig
- **Argo Rollouts Controller** installed on the target cluster. If it is not installed, you can install it via the [Helm MCP Server](https://github.com/talkops-ai/talkops-mcp/tree/main/src/helm-mcp-server).

### Quick Start with Docker (recommended)

Pull the image from [Docker Hub](https://hub.docker.com/r/talkopsai/argo-rollout-mcp-server) and run it:

```bash
docker run --rm -it \
  -p 8768:8768 \
  -v ~/.kube:/app/.kube:ro \
  -e K8S_KUBECONFIG=/app/.kube/config \
  talkopsai/argo-rollout-mcp-server:latest
```

> **Tip:** Mount the full `~/.kube` directory (not just `config`) so certificate paths referenced in your kubeconfig (e.g. minikube, kind) are available inside the container.

That's it. The server is now listening on `http://localhost:8768/mcp`.

Point your MCP client at it:

```json
{
  "mcpServers": {
    "argo-rollout": {
      "url": "http://localhost:8768/mcp",
      "description": "MCP Server for managing Argo Rollouts and K8s Progressive Delivery"
    }
  }
}
```

### Build from Source (Docker)

If you prefer to build the image yourself:

```bash
cd talkops-mcp/src/argo-rollout-mcp-server
docker build -t argo-rollout-mcp-server .

docker run --rm -it \
  -p 8768:8768 \
  -v ~/.kube:/app/.kube:ro \
  -e K8S_KUBECONFIG=/app/.kube/config \
  argo-rollout-mcp-server
```

### From Source (Python)

For development or if you want to run without Docker:

1. Install uv and set up:

```bash
# Install uv if not already installed
curl -LsSf https://astral.sh/uv/install.sh | sh

# Clone the repository
git clone https://github.com/talkops-ai/talkops-mcp.git
cd talkops-mcp/src/argo-rollout-mcp-server

# Create virtual environment and install
uv venv --python=3.12
source .venv/bin/activate  # On Unix/macOS
# .venv\Scripts\activate   # On Windows

uv pip install -e .
```

2. Run the server:

```bash
uv run argo-rollout-mcp-server
```

---

## Configuration

All configuration is via environment variables.

When running in Docker, pass overrides with `-e`:

```bash
docker run --rm -it \
  -p 8768:8768 \
  -v ~/.kube:/app/.kube:ro \
  -e K8S_KUBECONFIG=/app/.kube/config \
  -e K8S_CONTEXT=production-cluster \
  -e MCP_LOG_LEVEL=DEBUG \
  talkopsai/argo-rollout-mcp-server:latest
```

### Server Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `MCP_SERVER_NAME` | `argo-rollout-mcp-server`| Server name identifier |
| `MCP_SERVER_VERSION` | `0.1.0` | Server version string |
| `MCP_TRANSPORT` | `http` | Transport mode: `http` or `stdio` |
| `MCP_HOST` | `0.0.0.0` | Host address for HTTP server |
| `MCP_PORT` | `8768` | Port for HTTP server |
| `MCP_PATH` | `/mcp` | MCP endpoint path |
| `MCP_LOG_LEVEL` | `INFO` | Log level: `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `MCP_LOG_FORMAT` | `json` | Log format: `json` or `text` |

### Argo & Kubernetes

| Variable | Default | Description |
|----------|---------|-------------|
| `K8S_KUBECONFIG` | `/app/.kube/config` | Path to kubeconfig file |
| `K8S_CONTEXT` | *(empty)* | Specific K8s context to force |
| `K8S_IN_CLUSTER` | `false` | True if running inside a pod natively |

### Prometheus (Metrics Resources)

| Variable | Default | Description |
|----------|---------|-------------|
| `PROMETHEUS_URL` | `http://prometheus:9090` | Prometheus server URL for metrics (request rate, error rate, latency). When unreachable, metrics resources return placeholder data. |

### Write Access Control
Note: Global read-only `MCP_ALLOW_WRITE` flags are implemented logically at the command layer ensuring non-destructive `apply=False` calls when restricted.

### Troubleshooting Docker Warnings

| Symptom | Fix |
|--------|-----|
| `InsecureRequestWarning: Unverified HTTPS request` | Suppressed by default when connecting to clusters with self-signed certs (Docker Desktop, minikube, kind). No action needed. |
| `Invalid kube-config file. Expected object with name in contexts list` | Mount the full `~/.kube` directory: `-v ~/.kube:/app/.kube:ro`. Ensure each context in your kubeconfig has a non-empty `name` field. If using minikube/kind, their cert paths must be inside the mounted dir. |

---

## Available Tools

### Migration & Generations
| Tool | Description |
|------|-------------|
| `convert_deployment_to_rollout` | Convert K8s Deployment → Argo Rollout (direct or workloadRef migration; auto-applies Services and CRDs) |
| `convert_rollout_to_deployment` | Reverse migration back to standard K8s Deployments |
| `argo_manage_legacy_deployment` | Unified: scale, delete, or generate scale-down manifest for legacy Deployments (workloadRef migration) |
| `create_stable_canary_services` | (Advanced/legacy) Generate stable+canary Services. Prefer `convert_deployment_to_rollout(mode='generate_services_only', app_name='...')` |
| `generate_argocd_ignore_differences` | Create ArgoCD sync rules for safe Rollout integrations |
| `validate_deployment_ready` | Check Deployment readiness score before touching the cluster |

### Lifecycle Orchestration & Operations
| Tool | Description |
|------|-------------|
| `argo_create_rollout` | Create new Argo Rollout (canary, bluegreen, rolling) |
| `argo_delete_rollout` | Safely remove a Rollout from the cluster |
| `argo_update_rollout` | Unified: update image (direct or workloadRef), strategy, traffic routing, or workloadRef scale-down |
| `argo_manage_rollout_lifecycle` | Unified lifecycle: promote, promote_full, pause, resume, abort, skip_analysis |

### Validation, Traffic & Observation
| Tool | Description |
|------|-------------|
| `argo_configure_analysis_template` | Configure AnalysisTemplate: execute (create+link) or generate_yaml (GitOps review) |
| `argo_create_experiment` | Instantiate ephemeral A/B test pods |
| `argo_delete_experiment` | Clean up experimentation runs |

---

## Available Resources

| Resource URI | Description |
|--------------|-------------|
| `argorollout://rollouts/list` | All rollouts overview across the cluster |
| `argorollout://rollouts/{namespace}/{name}/detail`| Specific live rollout status (phase, readyReplicas) |
| `argorollout://experiments/{namespace}/{name}/status`| Metrics and progression for live A/B experiments |
| `argorollout://health/summary` | Cluster-wide orchestration health overview |
| `argorollout://health/{namespace}/{name}/details`| Deep-dive into specific application crash statuses |
| `argorollout://metrics/{namespace}/{service}/summary`| Prometheus bounds mapping |
| `argorollout://metrics/prometheus/status`| Validation of active metric endpoints |
| `argorollout://history/all` | Global audit trail of all deployed revisions |
| `argorollout://history/{namespace}/{deployment}`| Specific rollout history trail of old ReplicaSets and images |
| `argorollout://cluster/health` | Root cluster readiness check |
| `argorollout://cluster/namespaces` | Available namespaces map |

---

## Available Prompts

| Prompt | Description |
|--------|-------------|
| `onboard_application_guided`| Zero YAML first-time conversion (Deployment → Rollout; direct or workloadRef) |
| `canary_deployment_guided` | Progressive traffic execution playbook (5% → 100%) |
| `blue_green_deployment_guided`| Zero-downtime cutover workflows with instant rollback hooks |
| `rolling_update_guided` | Safe traditional rollout patterns |
| `cost_optimized_deployment_guided`| Cost-conscious best practices (orchestration tools are future enhancement) |
| `multi_cluster_canary_guided` | Sequential regional rollout; switch kubeconfig context per region |

---

## Usage

Supported workflows with prompt examples and links to detailed guides:

| Workflow | Prompt Example | Documentation |
|----------|----------------|---------------|
| **Onboarding** — Deployment → Rollout | `"Migrate my 'api-service' deployment in 'production' to Argo Rollouts safely."` | [ONBOARDING_TEST_GUIDE.md](docs/workflow-docs/ONBOARDING_TEST_GUIDE.md) |
| **workloadRef Migration** — Argo CD / Helm | `"Convert the hello-world deployment in default to an Argo Rollout using workloadRef — keep the Deployment running, scale_down=never. Apply to cluster."` | [WORKLOAD_REF_MIGRATION_TEST_GUIDE.md](docs/workflow-docs/WORKLOAD_REF_MIGRATION_TEST_GUIDE.md) |
| **Deployment Strategies** — Rolling, Canary, Blue-Green | `"Deploy hello-world:v2 to the hello-world rollout in default."` — `"Convert the frontend in staging to a blue-green rollout. Auto-promote after 300s."` | [DEPLOYMENT_STRATEGIES_TEST_GUIDE.md](docs/workflow-docs/DEPLOYMENT_STRATEGIES_TEST_GUIDE.md) |
| **A/B Testing** — Experiments | `"Run an A/B test experiment called 'ui-experiment' in production using baseline and candidate for 1 hour."` | [AB_TESTING_TEST_GUIDE.md](docs/workflow-docs/AB_TESTING_TEST_GUIDE.md) |
| **Argo CD GitOps** — ignoreDifferences | `"Generate ArgoCD ignoreDifferences for hello-world in default with include_deployment_replicas for workloadRef."` | [ARGOCD_GITOPS_TEST_GUIDE.md](docs/workflow-docs/ARGOCD_GITOPS_TEST_GUIDE.md) |
| **Reverse Migration** — Rollout → Deployment | `"Convert the hello-world rollout in default back to a standard Kubernetes Deployment."` | [REVERSE_MIGRATION_TEST_GUIDE.md](docs/workflow-docs/REVERSE_MIGRATION_TEST_GUIDE.md) |
| **Zero-Downtime Migration** — Argo CD | `"Convert hello-world deployment to workloadRef rollout for zero-downtime migration under Argo CD."` | [ZERO_DOWNTIME_MIGRATION_TEST_GUIDE.md](docs/workflow-docs/ZERO_DOWNTIME_MIGRATION_TEST_GUIDE.md) |
| **Emergency Abort** | `"Abort the payment rollout in production immediately — roll back to stable."` | [WORKFLOW_JOURNEYS.md](docs/workflow-docs/WORKFLOW_JOURNEYS.md) § Monitoring |

### Guided Prompts

Use MCP prompts for step-by-step workflows:

| Prompt | Use Case |
|--------|----------|
| `onboard_application_guided` | First-time Deployment → Rollout conversion |
| `canary_deployment_guided` | Progressive canary (5% → 100%) |
| `blue_green_deployment_guided` | Blue-green cutover |
| `rolling_update_guided` | Standard rolling update |
| `cost_optimized_deployment_guided` | Cost-conscious best practices |
| `multi_cluster_canary_guided` | Sequential regional rollout |

See [WORKFLOW_JOURNEYS.md](docs/workflow-docs/WORKFLOW_JOURNEYS.md) for the full workflow reference and [PROMPT_REFERENCE.md](docs/prompts/PROMPT_REFERENCE.md) for natural-language prompts.

---

## Project Structure

```text
argo-rollout-mcp-server/
├── argo_rollout_mcp_server/       # Main package
│   ├── tools/                     # MCP Tools
│   │   ├── argo/                  # Rollout operations
│   │   ├── generators/            # Conversion engines
│   │   └── orchestration/         # Policy execution (orch_* — excluded)
│   ├── resources/                 # MCP Resources
│   │   ├── rollout_resources.py
│   │   ├── health_resources.py
│   │   ├── metrics_resources.py
│   │   ├── history_resources.py
│   │   └── cluster_resources.py
│   ├── prompts/                   # MCP Prompts
│   │   ├── onboarding_deployment.py
│   │   ├── canary_deployment.py
│   │   ├── bluegreen_deployment.py
│   │   ├── rolling_update.py
│   │   ├── cost_optimized.py
│   │   └── multicluster_canary.py
│   ├── services/                  # Business logic
│   │   ├── argo_rollouts_service.py  # K8s client wrapper for CRDs
│   │   ├── generator_service.py
│   │   └── orchestration_service.py
│   ├── server/                    # FastMCP server setup
│   ├── exceptions/                # Custom exception types
│   ├── config.py                  # Configuration management
│   └── main.py                    # Application entry point
├── Dockerfile                     # Container build
├── docker-entrypoint.sh           # Run setup
├── pyproject.toml                 # Metadata + dependencies
└── README.md                      # This file
```

---

## Roadmap

**Shipped:**

- [x] Full progressive delivery lifecycle — deploy, promote, pause, abort
- [x] Automated generation of Rollouts from Deployments (zero-YAML)
- [x] Integration with Prometheus `AnalysisTemplates`
- [x] Read-only context exposure via Resources
- [x] Pre-packaged AI prompts for A/B testing and Canary operations
- [x] Docker image structure

**Coming next:**

- [ ] Orchestration tools (`orch_*`) — currently mockup implementations (simulated metrics/costs); excluded from this release. See [ENHANCEMENT-Tool-Consolidation-Audit.md](docs/ENHANCEMENT-Tool-Consolidation-Audit.md) Phase 4.
- [ ] Direct GatewayAPI (v1beta1) CRD support 
- [ ] Detailed pod diff viewing natively 
- [ ] Deep rollback linking to Git SHA hashes

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

Any MCP-compatible client that supports HTTP transport — Claude Desktop, Cline, or your own custom agent. Point the client at `http://localhost:8768/mcp`.
</details>

<details>
<summary><b>Does this support Traefik or other ingress traffic weights?</b></summary>

This server is **Argo Rollout specific**. It manages rollouts, analysis, promotion, and abort. Use `argo_update_rollout(update_type='traffic_routing')` to link a canary rollout to an existing weighted traffic service (e.g., TraefikService) by name — the traffic service must be created separately via your ingress controller or CI/CD. For full Traefik route creation and middleware, use a companion Traefik MCP Server if available.
</details>

<details>
<summary><b>Does it actually create K8s resources?</b></summary>

Yes. Tools like `convert_deployment_to_rollout` with `apply=True` will directly patch and create CRDs in your connected Kubernetes cluster using your mounted `KUBECONFIG`.
</details>

---

## Troubleshooting

### Connection Errors

If your MCP client times out reaching port `8768`, verify your kubeconfig volume mount inside Docker.

### K8s Connectivity

1. Ensure your Cluster's context matches `K8S_CONTEXT`
2. If using Docker Desktop natively, you may need `--network host`

---

## Security Considerations

- **Never hardcode secrets** in configuration deployments
- **Use namespace isolation** where necessary
- **Ensure appropriate RBAC permissions** inside your KUBECONFIG for CRD manipulation
- **Review generated strategies** (`apply=False`) prior to executing true migrations natively

---

## License

Apache 2.0 — see [LICENSE](../../LICENSE).

---

## Contact

**TalkOps AI** — [github.com/talkops-ai](https://github.com/talkops-ai)

**Project:** [github.com/talkops-ai/talkops-mcp](https://github.com/talkops-ai/talkops-mcp)

**Discord:** [Join the community](https://discord.gg/tSN2Qn9uM8)

---

## Acknowledgments

- [Model Context Protocol](https://modelcontextprotocol.io/) 
- [FastMCP](https://github.com/jlowin/fastmcp) 
- [Argo Rollouts](https://argoproj.github.io/argo-rollouts/)
