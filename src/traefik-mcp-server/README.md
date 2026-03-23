<p align="center">
  <img src="https://raw.githubusercontent.com/traefik/traefik/master/docs/content/assets/img/traefik.logo.png" alt="Traefik MCP Server" width="140" onError="this.style.display='none'"/>
</p>

<h1 align="center">Traefik MCP Server</h1>

<p align="center">
  An MCP server that gives AI assistants the power to easily manage Kubernetes traffic for you—safely routing requests, adding instant protections like rate limits, and automatically upgrading outdated NGINX setups into modern Traefik configurations.
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

**The problem:** Managing Kubernetes traffic can be incredibly frustrating. Between brittle Ingress YAML files, messy NGINX annotations, and digging through documentation to figure out complex `Middleware` configurations, even a simple task like adding a rate limiter can feel overwhelming. If you want an AI assistant to do this for you, it usually struggles because it doesn't have a safe, structured way to interact with Traefik's custom resources natively.

**The solution:** The Traefik MCP Server gives AI assistants (like Claude or Cline) direct tools to manage your Kubernetes traffic for you safely and automatically. Instead of writing endless YAML by hand, your AI can now confidently control how your apps are routed.

Here's exactly what your AI assistant can now do for you:

1. **Automated NGINX-to-Traefik Migrations (with AI Problem-Solving):** Moving away from NGINX? The AI scans your old Ingress files, analyzes the messy annotations (like CORS, sticky sessions, or custom auth), and automatically converts them into modern Traefik resources. If the AI detects a legacy configuration that breaks the migration, it can use built-in "Supervised Autonomy" to intelligently bypass the broken rule and build a custom workaround on the fly.
2. **Effortless Traffic Splitting & Shadow Testing:** Need to test a new version of your app? Ask your AI to split traffic (e.g., 90% stable, 10% canary) or set up a "Shadow Launch" where live production traffic is copied to your new app for silent testing without users ever knowing.
3. **Instant App Protections:** You no longer need to write complex `Middleware` YAML manually. Simply tell the AI, "Add a rate limit and a circuit breaker to the frontend," and it will instantly build and attach those network security protections.
4. **Deep Network Insights:** Your AI gains advanced "Micro-Observability." It instantly knows exactly what percentage of traffic is hitting which container, what security middlewares are active, and if there are any immediate routing connection errors globally.

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

**Legacy Extrication & Supervised Autonomy**
- Scan legacy environments retrieving `Ingress` specs safely
- Unpack annotations transforming behaviors into isolated CRDs 
- Setup side-by-side verification tests safely
- Agentic Overrides explicitly bypassing breaking legacy configs securely via AI logic

**Advanced TCP & HTTP Routing**
- Route standard TCP streams natively bypassing HTTP abstraction logic (Postgres, Redis)
- Deploy simple non-weighted `IngressRoute` rules seamlessly

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
          ┌─────────────────────────┬─────────────────────────┐
          │                                                   │
    ┌─────▼─────┐                                       ┌─────▼─────┐
    │   Tools   │                                       │ Resources │
    │           │                                       │           │
    │ Weights   │                                       │ traefik://│
    │ NGINX Conv│                                       │           │
    │ Rate Limits│                                      │           │
    │ Splitting │                                       │           │
    │           │                                       │           │
    └─────┬─────┘                                       └─────┬─────┘
          │                                                   │
          └─────────────────────────┬─────────────────────────┘
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
  talkopsai/traefik-mcp-server:latest
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
  talkopsai/traefik-mcp-server:latest
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

**RBAC (typical):** read paths need `get/list/watch` on **ingresses** and `get/list` on **pods** (controller detection). Apply paths additionally need `create/patch/update` on **middlewares** and **serverstransports** (`traefik.io/v1alpha1`), and `patch` on **ingresses** and **services** in target namespaces. 

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

### Backend TLS, timeouts & sticky sessions
| Tool | Description |
|------|-------------|
| `traefik_manage_servers_transport` | Create/update or delete Traefik **ServersTransport** CRDs (`action=create\|delete`): backend dial/response timeouts, `insecureSkipVerify`. Link Services with `traefik.ingress.kubernetes.io/service.serverstransport`. |
| `traefik_configure_service_affinity` | **Enable** or **disable** Traefik sticky-cookie annotations on a Kubernetes **Service** (`action=enable\|disable`), matching NGINX migration semantics. |

### Generators
| Tool | Description |
|------|-------------|
| `traefik_generate_routing_manifest` | Generate TraefikService, IngressRoute, TCP manifests, etc. Use `manifest_type` (traefik_service, ingress_for_traefik_service, ingress_for_services, mirroring, ingress_route_tcp, middleware_tcp). Header/cookie routing is applied live via `traefik_manage_weighted_routing` (create). For **full** NGINX Ingress → Traefik translation (annotations, middlewares), use **`traefik_nginx_migration`** — not ad-hoc YAML snippets. |

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

## Usage

Supported workflows with prompt examples and links to detailed guides:

| Workflow | Prompt Example | Documentation |
|----------|----------------|---------------|
| **Traffic Flow (Weighted Canary)** | `"Create a 90/10 weighted canary route 'api-route' in production for api.example.com."` | [TRAFFIC_MANAGEMENT_TEST_GUIDE.md](docs/TRAEFIK_TRAFFIC_MANAGEMENT_TEST_GUIDE.md) |
| **Header-Based Canary** | `"Route only traffic with the header 'X-Canary: true' to the canary pod."` | [HEADER_CANARY_TEST_GUIDE.md](docs/TRAEFIK_HEADER_CANARY_TEST_GUIDE.md) |
| **Traffic Mirroring (Shadow Launch)** | `"Mirror 20% of production traffic to the new service without affecting user responses."` | [SHADOW_LAUNCH_TEST_GUIDE.md](docs/TRAEFIK_SHADOW_LAUNCH_TEST_GUIDE.md) |
| **TCP Routing & Middlewares** | `"Create a TCP route for Postgres on port 5432 with an IP Allowlist middleware."` | [TCP_ROUTING_TEST_GUIDE.md](docs/TRAEFIK_TCP_ROUTING_TEST_GUIDE.md) |
| **NGINX to Traefik Migration** | `"Run the NGINX to Traefik migration for the 'ecommerce' namespace to translate annotations."` | [NGINX_MIGRATION_TEST_GUIDE.md](docs/TRAEFIK_NGINX_MIGRATION_TEST_GUIDE.md) |
| **Agentic Override (Supervised Autonomy)**| `"Apply the migration but ignore the 'auth-url' annotation and inject my 'custom-auth' middleware."`| [WORKFLOW_JOURNEYS.md](docs/WORKFLOW_JOURNEYS.md) |
| **Instant App Protection** | `"Add a rate limit of 100 rps and a 5xx circuit breaker to the frontend route."` | [PROMPT_REFERENCE.md](docs/PROMPT_REFERENCE.md) |

See [WORKFLOW_JOURNEYS.md](docs/WORKFLOW_JOURNEYS.md) for the full workflow reference and [PROMPT_REFERENCE.md](docs/PROMPT_REFERENCE.md) for natural-language prompts.

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
- [x] Powerful weighted network routing generators and Simple IngressRoutes
- [x] TCP Routing and global Traffic Mirroring (Shadow Launch) capabilities
- [x] NGINX to Traefik automated conversion pipelines with AI Agentic Overrides
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
