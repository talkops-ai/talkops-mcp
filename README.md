# TalkOps MCP Servers

A suite of Model Context Protocol (MCP) servers for DevOps tools and technologies, enabling AI assistants and automation to interact with modern infrastructure and deployment technologies.

This repository serves as the **central hub and MCP registry** for all MCP servers built to support a wide range of DevOps tools and workflows. Each MCP server provides a standardized interface for AI agents and automation platforms to interact with specific tools, services, or platforms, making it easier to integrate, automate, and extend DevOps operations across diverse environments.

- **Kubernetes Package Management:** For managing Kubernetes workloads, the Helm MCP Server enables AI-driven Helm chart operations and best practices.
- **CI/CD, Build & Release:** Dedicated MCP servers (e.g., ArgoCD MCP Server, Argo Rollout MCP Server, Kargo MCP Server) provide automation and orchestration for continuous integration, delivery, and deployment pipelines.
- **Integration & Traffic:** Dedicated MCP Servers like Traefik MCP Server enables AI-driven edge routing, weighted canary traffic, traffic mirroring, NGINX-to-Traefik migration, and instant middleware protections (rate limit, circuit breaker).
- **Observability & Monitoring:** For monitoring and observability, specialized MCP servers are available for Prometheus, Alertmanager, Loki, Tempo, and OpenTelemetry, enabling deep, cross-pillar diagnostics across metrics, logs, traces, and pipelines.

The vision for TalkOps MCP Servers is to offer a **modular, extensible, and unified platform** where each DevOps domain—whether Kubernetes package management, CI/CD, traffic management, or observability—can be managed through a dedicated MCP server. This approach empowers AI agents and automation tools to deliver intelligent, context-aware DevOps workflows, regardless of the underlying technology stack.

## Table of Contents

- [TalkOps MCP Servers](#talkops-mcp-servers)
  - [Table of Contents](#table-of-contents)
  - [Quick start](#quick-start)
  - [Available MCP Servers](#available-mcp-servers)
    - [📦 Kubernetes Package Management](#kubernetes-package-management)
    - [🚀 CI/CD & GitOps](#cicd--gitops)
    - [📊 Observability & Monitoring](#observability--monitoring)
    - [📡 Integration & Traffic](#integration--traffic)
  - [Contributing](#contributing)
  - [License](#license)
  - [Support](#-support)

---

## Quick start

Every server is published on PyPI (`talkops-<server-name>`) and on Docker Hub (`talkopsai/<server-name>`).

**With [uv](https://docs.astral.sh/uv/getting-started/installation/) (PyPI)** — downloads and runs in one step:

```json
{
  "mcpServers": {
    "prometheus": {
      "command": "uvx",
      "args": ["--from", "talkops-prometheus-mcp-server", "prometheus-mcp-server", "--read-only"],
      "env": { "PROMETHEUS_BASE_URL": "http://localhost:9090" }
    }
  }
}
```

**Or with [Docker](https://docs.docker.com/get-docker/) (Docker Hub)** — no local Python setup needed:

```json
{
  "mcpServers": {
    "prometheus": {
      "command": "docker",
      "args": [
        "run", "-i", "--rm",
        "-e", "MCP_TRANSPORT=stdio",
        "-e", "PROMETHEUS_BASE_URL",
        "talkopsai/prometheus-mcp-server:latest",
        "--read-only"
      ],
      "env": { "PROMETHEUS_BASE_URL": "http://host.docker.internal:9090" }
    }
  }
}
```

A few things are the same across every server:

- **Safe by default.** Servers start read-only (Prometheus is the one exception; see its README). You opt in to changes with `--allow-write` or `-e MCP_ALLOW_WRITE=true`.
- **stdio or HTTP.** Use `stdio` for local MCP clients, or run `docker run --rm -p <port>:<port> talkopsai/<server-name>:latest` (or `MCP_TRANSPORT=http`) to share one HTTP endpoint across clients (Traefik is `stdio` only).
- **Agent Skills included.** Each server ships playbooks in its `skills/` folder that teach your assistant how to use the tools well.

Each server's README has its exact setup, settings, and example prompts.

---

## Available MCP Servers

<a id="kubernetes-package-management"></a>
### 📦 Kubernetes Package Management

| Server | What it does | Run it (PyPI / Docker) | Video |
|--------|--------------|------------------------|-------|
| [Helm](src/helm-mcp-server) | Find, install, upgrade, and roll back Helm charts, with a plan before every change. | `uvx --from talkops-helm-mcp-server helm-mcp-server`<br>`docker pull talkopsai/helm-mcp-server:latest` | [▶ Watch](https://youtu.be/efU7TatQCqI?si=YYZC9BvBqmeq93_x) |

<a id="cicd--gitops"></a>
### 🚀 CI/CD & GitOps

| Server | What it does | Run it (PyPI / Docker) | Video |
|--------|--------------|------------------------|-------|
| [ArgoCD](src/argocd-mcp-server) | Check app health, preview and run syncs, roll back, and onboard repos and projects. | `uvx --from talkops-argocd-mcp-server argocd-mcp-server`<br>`docker pull talkopsai/argocd-mcp-server:latest` | [▶ Overview](https://youtu.be/5V0wo4jkUtQ)<br>[▶ Demo](https://youtu.be/gfMLUK9YcGc) |
| [Argo Rollouts](src/argo-rollout-mcp-server) | Move Deployments to Rollouts and run canary and blue-green releases gated on metrics. | `uvx --from talkops-argo-rollout-mcp-server argo-rollout-mcp-server`<br>`docker pull talkopsai/argo-rollout-mcp-server:latest` | [▶ Quick Walk](https://youtu.be/tPd6i7F8_e4?si=4jJjZzLyb6DD6lDL)<br>[▶ Migration](https://youtu.be/Kb0VNf6uGAs?si=bOGqnETYwDYHLapN)<br>[▶ Canary](https://youtu.be/E7riLSKC8Tg?si=VmD0pecfA19ryE9E)<br>[▶ Blue-Green](https://youtu.be/mb_gUr6KmYE?si=swU-irIyR3UyOZZn)<br>[▶ A/B Testing](https://youtu.be/yEXinOu2718?si=s2FWRNjFcG3W7Myp) |
| [Kargo](src/kargo-mcp-server) | See what's deployed where, promote and approve freight, and roll back stages. | `uvx --from talkops-kargo-mcp-server kargo-mcp-server`<br>`docker pull talkopsai/kargo-mcp-server:latest` | — |

<a id="observability--monitoring"></a>
### 📊 Observability & Monitoring

| Server | What it does | Run it (PyPI / Docker) | Video |
|--------|--------------|------------------------|-------|
| [Prometheus](src/prometheus-mcp-server) | Run PromQL, check SLOs, test alert rules, and cut expensive metrics. Works with Thanos, Mimir, and more. | `uvx --from talkops-prometheus-mcp-server prometheus-mcp-server`<br>`docker pull talkopsai/prometheus-mcp-server:latest` | — |
| [Alertmanager](src/alertmanager-mcp-server) | See what's firing, find out why an alert didn't notify, and create safe silences. | `uvx --from talkops-alertmanager-mcp-server alertmanager-mcp-server`<br>`docker pull talkopsai/alertmanager-mcp-server:latest` | — |
| [Grafana Loki](src/loki-mcp-server) | Search logs, summarize errors, compare releases, and follow a trace ID across services. | `uvx --from talkops-loki-mcp-server loki-mcp-server`<br>`docker pull talkopsai/loki-mcp-server:latest` | — |
| [Grafana Tempo](src/tempo-mcp-server) | Search traces with TraceQL, find slow spans, and map service dependencies. | `uvx --from talkops-tempo-mcp-server tempo-mcp-server`<br>`docker pull talkopsai/tempo-mcp-server:latest` | — |
| [OpenTelemetry](src/opentelemetry-mcp-server) | Set up collectors, auto-instrument workloads, tune sampling, and debug pipelines. | `uvx --from talkops-opentelemetry-mcp-server opentelemetry-mcp-server`<br>`docker pull talkopsai/opentelemetry-mcp-server:latest` | — |

<a id="integration--traffic"></a>
### 📡 Integration & Traffic

| Server | What it does | Run it (PyPI / Docker) | Video |
|--------|--------------|------------------------|-------|
| [Traefik](src/traefik-mcp-server) | Manage routes, canary traffic, middlewares, and TLS, and explain 404s and 502s. | `uvx --from talkops-traefik-mcp-server traefik-mcp-server`<br>`docker pull talkopsai/traefik-mcp-server:latest` | — |

---

## Contributing

Contributions are welcome! Please open an issue or pull request on the project repository.

## License

This project is licensed under the Apache-2.0 License.

## 📞 Support

- Open an issue on GitHub
- Join the TalkOps community on [Slack](https://talkops.ai/slack/)
- See each server's README for documentation and guides
