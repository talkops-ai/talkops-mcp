<p align="center">
  <img src="../../assets/logo.png" alt="Traefik MCP Server" width="140" onError="this.style.display='none'"/>
</p>

<h1 align="center">Traefik MCP Server</h1>

<p align="center">
  An MCP server that gives AI assistants full control over Kubernetes traffic routing — from circuit breakers to NGINX migrations.
</p>

<p align="center">
  <a href="https://github.com/talkops-ai/talkops-mcp/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-Apache%202.0-blue.svg?style=flat-square" alt="License"/></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/Python-3.10%2B-3776AB.svg?style=flat-square&logo=python&logoColor=white" alt="Python 3.10+"/></a>
  <a href="https://modelcontextprotocol.io/"><img src="https://img.shields.io/badge/MCP-Model%20Context%20Protocol-4A90D9.svg?style=flat-square" alt="MCP"/></a>
  <a href="https://traefik.io/"><img src="https://img.shields.io/badge/Traefik-v2.10%2B-24A1C1.svg?style=flat-square&logo=traefik&logoColor=white" alt="Traefik"/></a>
  <a href="https://discord.gg/tSN2Qn9uM8"><img src="https://img.shields.io/badge/Discord-Join%20Us-5865F2.svg?style=flat-square&logo=discord&logoColor=white" alt="Discord"/></a>
</p>

<p align="center">
  <a href="#getting-started">Quick Start</a> · <a href="https://github.com/talkops-ai/talkops-mcp">Docs</a> · <a href="https://github.com/talkops-ai/talkops-mcp/issues/new?template=bug_report.md">Report Bug</a> · <a href="https://github.com/talkops-ai/talkops-mcp/issues/new?template=feature_request.md">Request Feature</a>
</p>

---

## Why Traefik MCP Server?

**The problem.** Routing traffic in Kubernetes is notoriously complex. You're dealing with brittle Ingress definitions, messy NGINX annotations, middleware chains, and TLS certificates. Want to apply a simple rate limiter? You have to dig through Traefik documentation, write custom CRDs, and manually `kubectl apply` them while hoping you don't break existing routes. 

AI assistants should execute traffic configuration natively. But they can't — not without structured tools to natively read, write, and safely validate Traefik's custom resources.

**What Traefik MCP Server does.**

It exposes Traefik's powerful traffic shaping layer — `IngressRoute`, `Middleware`, and `TraefikService` CRDs — as a set of MCP tools, resources, and prompts. Any MCP-compatible AI assistant (Claude, Cline, or your own agent) can securely attach load balancing, apply rate limits, split traffic for canary deployments, and autonomously translate NGINX annotations into natively typed Traefik CRDs.

Three things make this different:

1. **Zero YAML Migration.** NGINX-to-Traefik migrations are fully automated natively. The assistant reads legacy NGINX annotations (like `limit-rps`), executes the `convert_nginx_ingress_to_traefik` tool, and pushes native Traefik middleware and routes directly.

2. **Instant Resiliency Connections.** You don't have to author middleware definitions by hand. The assistant natively synthesizes and applies generic circuit breakers, retries, and rate limits dynamically mapping them directly into active HTTP pipelines. 

3. **Advanced Micro-Observability.** Call a single context resource securely to expose exactly what percentage of traffic is hitting which pod, how many validation rules are in the chain, and the precise domain topologies globally.

---

## Key Features

**Edge Routing**
- Read robust K8s Service definitions instantly
- Establish exact weighted percentages (e.g. 90/10) directly targeting K8s objects dynamically
- Deploy secure `IngressRoute` rules seamlessly

**Middleware Generation**
- Automatically format and enforce `RateLimit` limitations per second
- Construct `Retry` and `CircuitBreaker` logic gracefully across target connections
- Attach independent modules onto active data plane networks effortlessly 

**Legacy Extrication**
- Scan legacy environments retrieving `Ingress` specs safely
- Unpack annotations transforming behaviors into isolated CRDs 
- Setup side-by-side verification tests safely

**Deep Network Audits**
- Access specific path definitions validating backend availability metrics
- Identify traffic anomalies natively 

**Multi-Cluster Capability**
- Navigate strictly mapped Kubernetes context securely

**Built-in Guidance**
- Access specialized instructions executing migrations natively 

---

## Architecture

The server translates high-level MCP execution requests smoothly crossing directly into the Python Kubernetes sub-layer.

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
    │ Weights   │      │ traefik://  │      │ NGINX Mig   │
    │ NGINX Conv│      │             │      │ Resiliency  │
    │ Rate Limits│     │             │      │ Traffic     │
    │ Splitting │      │             │      │             │
    │           │      │             │      │             │
    └─────┬─────┘      └──────┬──────┘      └──────┬──────┘
          │                   │                     │
          └───────────────────┼─────────────────────┘
                              │
                    ┌─────────▼──────────┐
                    │   Service Layer    │
                    │                    │
                    │ traefik_service.py │
                    │ generator_service  │
                    └─────────┬──────────┘
                              │
                    ┌─────────▼──────────┐
                    │ Python K8s Client  │
                    │ (API interaction)  │
                    └────────────────────┘
```

**How it works in practice:**

1. An AI assistant accesses the server securely (HTTP or stdio).
2. The AI evaluates current constraints natively via API reads.
3. Upon intent (e.g., "Add a rate limit"), the AI hits specific execution tools mapping inputs dynamically.
4. Business layers patch the controller logically via the `KUBECONFIG`.
5. Traffic flows immediately transition. 

---

## Table of Contents

- [Why Traefik MCP Server?](#why-traefik-mcp-server)
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
| **Language** | Python 3.10+ |
| **MCP Framework** | [FastMCP](https://github.com/jlowin/fastmcp) |
| **Protocol** | [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) |
| **Kubernetes** | Traefik CRDs · kubectl · Python K8s Client |
| **Transport** | HTTP · stdio |
| **Infrastructure** | Docker · [uv](https://github.com/astral-sh/uv) |

---

## Getting Started

### Prerequisites

- **Docker** (recommended) or **Python 3.10+** (for local dev)
- **Access to a Kubernetes cluster** with a valid kubeconfig
- **Traefik Ingress Controller** installed on the target cluster

### Quick Start with Docker (recommended)

Pull the image and run it directly:

```bash
docker run --rm -it \
  -p 8769:8769 \
  -v ~/.kube/config:/app/.kube/config:ro \
  argoflow/traefik-mcp-server:latest
```

That's it. The server is now listening on `http://localhost:8769/mcp`.

Point your MCP client at it:

```json
{
  "mcpServers": {
    "traefik": {
      "url": "http://localhost:8769/mcp",
      "description": "MCP Server for managing Traefik Edge Routing and Middlewares"
    }
  }
}
```

### Build from Source (Docker)

If you prefer to build the image yourself:

```bash
cd talkops-mcp/src/argoflow-mcp-server/traefik-mcp-server
docker build -t traefik-mcp-server .

docker run --rm -it \
  -p 8769:8769 \
  -v ~/.kube/config:/app/.kube/config:ro \
  traefik-mcp-server
```

### From Source (Python)

For development or if you want to run without Docker:

1. Install [uv](https://docs.astral.sh/uv/getting-started/installation/) for dependency management.

2. Clone and set up:

```bash
git clone https://github.com/talkops-ai/talkops-mcp.git
cd talkops-mcp/src/traefik-mcp-server
uv venv
source .venv/bin/activate
uv pip install -e ".[dev]"
```

3. Run the server:

```bash
uv run traefik-mcp-server
```

Or, with the venv already activated: `traefik-mcp-server`.

4. Run tests (activate the venv first so `pytest` uses the project environment):

```bash
cd talkops-mcp/src/traefik-mcp-server
source .venv/bin/activate
pytest tests/
```

---

## Configuration

All configuration is via environment variables.

When running in Docker, pass overrides with `-e`:

```bash
docker run --rm -it \
  -p 8769:8769 \
  -v ~/.kube/config:/app/.kube/config:ro \
  -e K8S_CONTEXT=production-cluster \
  -e MCP_LOG_LEVEL=DEBUG \
  argoflow/traefik-mcp-server:latest
```

### Server Configuration

| Variable | Default | Description |
|----------|-------------|-------------|
| `MCP_SERVER_NAME` | `traefik-mcp-server`| Server name identifier |
| `MCP_SERVER_VERSION` | `0.1.0` | Server version string |
| `MCP_TRANSPORT` | `http` | Transport mode: `http` or `stdio` |
| `MCP_HOST` | `0.0.0.0` | Host address for HTTP server |
| `MCP_PORT` | `8769` | Port for HTTP server |
| `MCP_PATH` | `/mcp` | MCP endpoint path |
| `MCP_LOG_LEVEL` | `INFO` | Log level: `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `MCP_LOG_FORMAT` | `json` | Log format: `json` or `text` |

### Edge & Kubernetes

| Variable | Default | Description |
|----------|-------------|-------------|
| `K8S_KUBECONFIG` | `/app/.kube/config` | Path to kubeconfig file |
| `K8S_CONTEXT` | *(empty)* | Specific K8s context to force |
| `K8S_IN_CLUSTER` | `false` | True if running natively inside a pod |
| `MCP_ALLOW_WRITE` | `true` | Must be `true` for mutating cluster operations (e.g. `traefik_nginx_migration` with `action=apply`) |

### Write Access Control

`MCP_ALLOW_WRITE=true` (default) allows in-cluster **apply** for the NGINX migration pipeline. If false, mutating actions are blocked and YAML-only **migrate** still works. Inventory and analysis: MCP resources `traefik://migration/nginx-ingress-scan` and `traefik://migration/nginx-ingress-analyze`.

**RBAC (typical):** read paths need `get/list/watch` on **ingresses** and `get/list` on **pods** (controller detection). Apply paths additionally need `create/patch/update` on **middlewares** (`traefik.io/v1alpha1`) and `patch` on **ingresses** in target namespaces. 

---

## Available Tools

### Edge Routing & Traffic Splitting
| Tool | Description |
|------|-------------|
| `traefik_manage_weighted_routing` | Create, update, or delete weighted routes. Use `action` (create/update/delete) with route_name, hostname, stable_weight, canary_weight as needed. |
| `traefik_manage_simple_route` | Direct K8s Service IngressRoute: `action=create|delete` (upsert on create). |

### Native Middlewares & Resiliency
| Tool | Description |
|------|-------------|
| `traefik_manage_middleware` | Create, update, or delete Traefik `Middleware` CRDs. `action=create` upserts. **`middleware_type`**: `rate_limit`, `circuit_breaker`, `strip_prefix`, `redirect_scheme`, `inflight_req`, `headers`, `ip_allowlist`, `ip_denylist`, `forward_auth`, `buffering`, `replace_path`, `replace_path_regex`, `add_prefix`. Parameter matrix: [`docs/MIDDLEWARE_TOOLS.md`](docs/MIDDLEWARE_TOOLS.md). |
| `traefik_manage_traffic_mirroring` | Shadow traffic: `action=enable|disable|update` (mirror percent, optional attach/restore to WRR) |
| `traefik_manage_route_middlewares` | Attach or detach middlewares on an IngressRoute (action=attach \| detach) |

### Generators & Conversions
| Tool | Description |
|------|-------------|
| `traefik_generate_routing_manifest` | Generate TraefikService, IngressRoute, or header canary YAML. Use `manifest_type` (traefik_service, ingress_for_traefik_service, ingress_for_services, header_canary). |
| `convert_nginx_ingress_to_traefik`| Parse legacy Ingress annotations into native Traefik Custom Resources |

### NGINX Migrations
| Tool | Description |
|------|-------------|

| `traefik_nginx_migration` | **Migrate + revert**: `action=apply|generate|revert`. Apply/generate NGINX→Traefik bundle; revert undoes one Ingress. Optional **`migration_plan`**: per-Ingress overrides ([`docs/TICKET_MIGRATION_AGENT_INTELLIGENCE.md`](docs/TICKET_MIGRATION_AGENT_INTELLIGENCE.md), [test guide](docs/TRAEFIK_NGINX_MIGRATION_TEST_GUIDE.md)). Inventory: `traefik://migration/nginx-ingress-scan`; analysis: `traefik://migration/nginx-ingress-analyze` / `read_resource traefik://migration/nginx-runbook`. `action=apply` requires `MCP_ALLOW_WRITE=true`. Spec [`docs/ING_SWITCH_MCP_IMPLEMENTATION.md`](docs/ING_SWITCH_MCP_IMPLEMENTATION.md), tracker [`docs/ING_SWITCH_MIGRATION_TASK_TRACKER.md`](docs/ING_SWITCH_MIGRATION_TASK_TRACKER.md), audit [`docs/ING_SWITCH_MIGRATION_AUDIT.md`](docs/ING_SWITCH_MIGRATION_AUDIT.md). Reference code: [`docs/ing-switch/`](docs/ing-switch/). |

#### What the client receives (`traefik_nginx_migration`)
- For `action=apply`: Status on applied resources (Middlewares created, Ingresses patched).
- For `action=generate`: Agent guidelines and confirmation of generated artifacts.
- For `action=revert`: JSON status for the single-Ingress rollback.
- Guidance linking back to read-only MCP resources (`nginx-runbook`) for viewing full YAML.

---

## Available Resources

| Resource URI | Description |
|--------------|-------------|
| `traefik://traffic/routes/list` | Reads all dynamic `TraefikServices` operating globally in the cluster |
| `traefik://traffic/{namespace}/{route_name}/distribution`| Precise read-only overview of active rules (Weights, Attached Middlewares) |
| `traefik://metrics/{namespace}/{service}/summary`| Retrieve instantaneous 5xx/4xx error bounds and P99 latency maps |
| `traefik://metrics/prometheus/status`| Confirm metrics backend connectivity |
| `traefik://anomalies/detected` | Observe real-time flagged connection errors flagged natively |
| `traefik://anomalies/history/{namespace}` | Audit log covering historical anomaly detection |
| `traefik://migration/nginx-to-traefik` | Base status overview of active proxy migrations |
| `traefik://migration/nginx-to-traefik/{phase}`| Targeted analytics per migration phase (e.g., phase1, phase3) |
| `traefik://migration/nginx-ingress-scan` | **Live** Ingress inventory: **`paths`** + **`nginxAnnotations`** (`traefik.mcp/nginx-ingress-scan/2`) |
| `traefik://migration/nginx-ingress-scan/{namespace}` | Same digest scoped to one namespace |
| `traefik://migration/nginx-ingress-analyze` | Full NGINX→Traefik **compatibility** analysis, cluster-wide (`traefik.mcp/nginx-ingress-analyze/1`) |
| `traefik://migration/nginx-ingress-analyze/{namespace}` | Same analysis scoped to one namespace |

---

## Available Prompts

| Prompt | Description |
|--------|-------------|
| `nginx_to_traefik_migration_guide`| Highly granular step-by-step playbook (overview, phase1, phase2, phase3, phase4, monitoring, rollback) executing NGINX-to-Traefik migrations safely native to MCP. |

---

## Usage

### Applying Resiliency 

```
"The authorization API is getting slammed. Add a rate limit of 100 requests per second with a burst of 50 to the 'auth-route' IngressRoute in production. Also, attach a circuit breaker."
```

The AI automatically:
1. Calls Generators establishing `RateLimit` limitations in Python logic.
2. Synchronizes configurations attaching/detaching middlewares on routes (`traefik_manage_route_middlewares`).

### NGINX Migrations

```
"Start the NGINX to Traefik migration for 'checkout.myapp.com'. Analyze my legacy 'api-ingress' definition, and fully convert it natively."
```

### Validating Weight Split Distributions

```
"What is the current traffic split applied to 'api-service-route' in 'production'?"
```

The AI resolves metrics querying `traefik://traffic/production/api-service-route/distribution` reading active split topologies directly matching cluster state perfectly locally.

---

## Project Structure

```text
traefik-mcp-server/
├── traefik_mcp_server/            # Main package
│   ├── tools/                     # MCP Tools
│   │   ├── traffic.py             # Route manipulation
│   │   ├── middleware.py          # Protection logic
│   │   └── migrations/            # NGINX translation engines
│   ├── resources/                 # MCP Resources
│   │   ├── traffic_resources.py
│   │   └── anomaly_resources.py
│   ├── prompts/                   # MCP Prompts
│   │   └── setup_prompts.py
│   ├── services/                  # Business logic
│   │   ├── traefik_service.py     # Traefik native K8s wrapper
│   │   └── generator_service.py   # YAML conversion logic
│   ├── server/                    # FastMCP server setup
│   ├── exceptions/                # Error definitions
│   ├── config.py                  # Environment parsing
│   └── main.py                    # Entry point
├── tests/                         # Test suites natively
├── Dockerfile                     # Containerization
├── docker-entrypoint.sh           # System load sequence
├── pyproject.toml                 # Package definitions mapping Python 3.10
└── README.md                      # This documentation
```

---

## Roadmap

**Shipped:**

- [x] Full CRD support for `IngressRoute` and `TraefikService`
- [x] Powerful weighted network routing generators
- [x] NGINX to Traefik automated conversion pipelines natively
- [x] Context APIs fetching network configuration distribution

**Coming next:**

- [ ] Direct GatewayAPI (v1beta1) HTTPRoute translation
- [ ] Automated internal TLS bindings directly onto routes natively

See [open issues](https://github.com/talkops-ai/talkops-mcp/issues) for the full list of proposed feature sets proactively tracked transparently!

---

## Contributing

Contributions are welcome. The process is straightforward:

1. Fork the repo
2. Create a branch (`git checkout -b feature/NetworkFix`)
3. Make your changes and commit
4. Push and open a PR

If you're considering something bigger, open an issue first so we can align on the approach natively via discussions.

---

## FAQ

<details>
<summary><b>Which MCP clients work with this?</b></summary>
Any HTTP transport compatible client including Claude specifically mapping locally into <code>http://localhost:8769/mcp</code>.
</details>

<details>
<summary><b>Does this control pod orchestrations natively?</b></summary>
No. This orchestrates Edge proxies efficiently checking bounds physically. Orchestration logic mapping scaling metrics requires companion access using <b>Argo Rollout MCP Server</b> proactively!
</details>

<details>
<summary><b>Are execution patterns simulated locally?</b></summary>
Tools executed natively run valid mutation calls updating Traefik controllers directly dynamically across mapped structures locally natively across contexts perfectly!
</details>

---

## Troubleshooting

### Timeouts or Networking Errors

1. Verify execution bindings hitting correct IPs correctly directly. Verify context topologies mapping explicitly. Set your MCP HTTP timeouts longer directly resolving initial load bounds cleanly optimally properly globally.

### Migration Blocks

Examine exact resource naming mappings checking old annotations perfectly. 

---

## Security Considerations

- **Never hardcode generic authentication** directly into `BasicAuth` middleware rules.
- **Ensure network topologies securely match bounds.**
- **Execute tools locally checking variables prior securely natively.**

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

- [Model Context Protocol](https://modelcontextprotocol.io/) properly enabling agent capabilities.
- [FastMCP](https://github.com/jlowin/fastmcp) wrapper layer implementations directly securely natively!
- [Traefik Labs](https://traefik.io/) explicitly providing amazing proxies properly globally!
