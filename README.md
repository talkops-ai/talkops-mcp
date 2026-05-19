# TalkOps MCP Servers

A suite of Model Context Protocol (MCP) servers for DevOps tools and technologies, enabling AI assistants and automation to interact with modern infrastructure and deployment technologies.

This repository serves as the **central hub and MCP registry** for all MCP servers built to support a wide range of DevOps tools and workflows. Each MCP server provides a standardized interface for AI agents and automation platforms to interact with specific tools, services, or platforms, making it easier to integrate, automate, and extend DevOps operations across diverse environments.

- **Kubernetes Package Management:** For managing Kubernetes workloads, the Helm MCP Server enables AI-driven Helm chart operations and best practices.
- **CI/CD, Build & Release:** Dedicated MCP servers (e.g., ArgoCD MCP Server, Argo Rollout MCP Server, Jenkins MCP Server) provide automation and orchestration for continuous integration, delivery, and deployment pipelines.
- **Cloud Orchestration:** Dedicated MCP Servers like Terraform MCP Server provide comprehensive infrastructure as code management with secure command execution, semantic document search, and intelligent document ingestion for AWS, Azure, Google Cloud, and more.
- **Integration & Traffic:** Dedicated MCP Servers like Traefik MCP Server enables AI-driven edge routing, weighted canary traffic, traffic mirroring, NGINX-to-Traefik migration, and instant middleware protections (rate limit, circuit breaker).
- **Observability & Monitoring:** For monitoring and observability, specialized MCP servers will be available for Prometheus, the TICK stack (Telegraf, InfluxDB, Chronograf, Kapacitor), and other monitoring solutions.

The vision for TalkOps MCP Servers is to offer a **modular, extensible, and unified platform** where each DevOps domain—whether infrastructure as code, CI/CD, cloud orchestration, or observability—can be managed through a dedicated MCP server. This approach empowers AI agents and automation tools to deliver intelligent, context-aware DevOps workflows, regardless of the underlying technology stack.

## Table of Contents

- [TalkOps MCP Servers](#talkops-mcp-servers)
  - [Table of Contents](#table-of-contents)
  - [Available MCP Servers](#available-mcp-servers)
    - [📦 Kubernetes Package Management](#kubernetes-package-management)
    - [🚀 CI/CD & GitOps](#cicd--gitops)
    - [📡 Integration & Traffic](#integration--traffic)
    - [🏗️ Cloud Orchestration & Infrastructure](#cloud-orchestration--infrastructure)
    - [🔗 Agent Discovery & Registry](#agent-discovery--registry)
  - [Contributing](#contributing)
  - [License](#license)
  - [Support](#-support)

---

## Installation

Every TalkOps MCP server can be installed in **three ways**:

| Method | Command | Best for |
|--------|---------|----------|
| **pip** | `pip install talkops-<server-name>` | Quick local setup |
| **uv** | `uv pip install talkops-<server-name>` | Fast, modern Python |
| **uvx** | `uvx talkops-<server-name>` | Run without installing |
| **Docker** | `docker run talkopsai/<server-name>:latest` | Production / HTTP mode |

After installation, each server provides a CLI command (e.g., `prometheus-mcp-server`) that runs in **stdio mode** by default or **HTTP mode** with `MCP_TRANSPORT=http`.

---

## Available MCP Servers

Each table lists MCP servers by DevOps domain. Use **Quick Install** for the recommended setup (Docker preferred; CLI if no Docker), **README** for full documentation, and **Config** for MCP client configuration in that server's README.

<a id="kubernetes-package-management"></a>
### 📦 Kubernetes Package Management

| Server Name | Description | Quick Install | README | Config | Video |
|-------------|-------------|---------------|--------|--------|-------|
| [Helm MCP Server](src/helm-mcp-server) | Search charts, install/upgrade/rollback releases, validate manifests, monitor deployments. Full Helm lifecycle with dry-run and multi-cluster support. | `pip install talkops-helm-mcp-server`<br>or<br>`docker run -p 8765:8765 -v ~/.kube/config:/app/.kube/config:ro talkopsai/helm-mcp-server:latest` | [README](src/helm-mcp-server/README.md) | [Config](src/helm-mcp-server/README.md#quick-start-with-docker-recommended) | [▶ Watch](https://youtu.be/efU7TatQCqI?si=YYZC9BvBqmeq93_x) |

<a id="cicd--gitops"></a>
### 🚀 CI/CD & GitOps

| Server Name | Description | Quick Install | README | Config | Video |
|-------------|-------------|---------------|--------|--------|-------|
| [ArgoCD MCP Server](src/argocd-mcp-server) | Manage ArgoCD applications, sync deployments, onboard repositories, create projects, debug with guided workflows. GitOps with credential isolation. | `pip install talkops-argocd-mcp-server`<br>or<br>`docker run -p 8770:8770 -e ARGOCD_SERVER_URL=... -e ARGOCD_AUTH_TOKEN=... -e MCP_ALLOW_WRITE=true talkopsai/argocd-mcp-server:latest` | [README](src/argocd-mcp-server/README.md) | [Config](src/argocd-mcp-server/README.md#configuration) | [▶ Overview](https://youtu.be/5V0wo4jkUtQ)<br>[▶ Demo](https://youtu.be/gfMLUK9YcGc) |
| [Argo Rollout MCP Server](src/argo-rollout-mcp-server) | Convert K8s Deployments to Argo Rollouts, orchestrate canary/blue-green deployments, promote/pause/abort, integrate AnalysisTemplates. Zero-YAML onboarding with built-in playbooks. | `pip install talkops-argo-rollout-mcp-server`<br>or<br>`docker run -p 8768:8768 -v ~/.kube:/app/.kube:ro -e K8S_KUBECONFIG=/app/.kube/config talkopsai/argo-rollout-mcp-server:latest` | [README](src/argo-rollout-mcp-server/README.md) | [Config](src/argo-rollout-mcp-server/README.md#quick-start-with-docker-recommended) | [▶ Quick Walk](https://youtu.be/tPd6i7F8_e4?si=4jJjZzLyb6DD6lDL)<br>[▶ Migration](https://youtu.be/Kb0VNf6uGAs?si=bOGqnETYwDYHLapN)<br>[▶ Canary](https://youtu.be/E7riLSKC8Tg?si=VmD0pecfA19ryE9E)<br>[▶ Blue-Green](https://youtu.be/mb_gUr6KmYE?si=swU-irIyR3UyOZZn)<br>[▶ A/B Testing](https://youtu.be/yEXinOu2718?si=s2FWRNjFcG3W7Myp) |
| [Kargo MCP Server](src/kargo-mcp-server) | Continuous promotion orchestration for Kubernetes with Kargo. Manage stages, promotions, freight, and warehouses. | `pip install talkops-kargo-mcp-server`<br>or<br>`docker run talkopsai/kargo-mcp-server:latest` | [README](src/kargo-mcp-server/README.md) | [Config](src/kargo-mcp-server/README.md#configuration) | — |

<a id="observability--monitoring"></a>
### 📊 Observability & Monitoring

| Server Name | Description | Quick Install | README | Config | Video |
|-------------|-------------|---------------|--------|--------|-------|
| [Prometheus MCP Server](src/prometheus-mcp-server) | AI-native Prometheus observability — query metrics, manage alerting rules, analyze cardinality, deploy exporters, configure ServiceMonitors and Probes. | `pip install talkops-prometheus-mcp-server`<br>or<br>`docker run -p 8767:8767 talkopsai/prometheus-mcp-server:latest` | [README](src/prometheus-mcp-server/README.md) | [Config](src/prometheus-mcp-server/README.md#configuration) | — |
| [Alertmanager MCP Server](src/alertmanager-mcp-server) | AI-native alert management — list/silence/route alerts, audit routing, manage silences with safety guardrails. | `pip install talkops-alertmanager-mcp-server`<br>or<br>`docker run -p 8769:8769 talkopsai/alertmanager-mcp-server:latest` | [README](src/alertmanager-mcp-server/README.md) | [Config](src/alertmanager-mcp-server/README.md#configuration) | — |

<a id="integration--traffic"></a>
### 📡 Integration & Traffic

| Server Name | Description | Quick Install | README | Config | Video |
|-------------|-------------|---------------|--------|--------|-------|
| [Traefik MCP Server](src/traefik-mcp-server) | Manage K8s traffic via Traefik: weighted canary routing, traffic mirroring, NGINX-to-Traefik migration, rate limit and circuit breaker middlewares. Works with Argo Rollouts for progressive delivery. | `pip install talkops-traefik-mcp-server`<br>or<br>`docker run -p 8769:8769 -v ~/.kube/config:/app/.kube/config:ro talkopsai/traefik-mcp-server:latest` | [README](src/traefik-mcp-server/README.md) | [Config](src/traefik-mcp-server/README.md#quick-start-with-docker-recommended) | — |

<a id="cloud-orchestration--infrastructure"></a>
### 🏗️ Cloud Orchestration & Infrastructure

| Server Name | Description | Quick Install | README | Config | Video |
|-------------|-------------|---------------|--------|--------|-------|
| [Terraform MCP Server](src/terraform-mcp-server) | Execute Terraform commands, semantic doc search via Neo4j, document ingestion. Multi-provider AI (OpenAI, Anthropic, Ollama). | `cd src/terraform-mcp-server && uv pip install -e . && uv run agents-mcp-server` | [README](src/terraform-mcp-server/README.md) | [Config](src/terraform-mcp-server/README.md#configuration) | — |

<a id="agent-discovery--registry"></a>
### 🔗 Agent Discovery & Registry

| Server Name | Description | Quick Install | README | Config | Video |
|-------------|-------------|---------------|--------|--------|-------|
| [Agents Central Registry](src/agents-mcp-server) | Discovery hub for Google A2A agents and MCP servers. Natural language queries, capability matching, real-time registry updates. | `cd src/agents-mcp-server && uv pip install -e . && uv run -m agents_mcp_server` | [README](src/agents-mcp-server/README.md) | [Config](src/agents-mcp-server/README.md#mcp-client-configuration) | — |


---

## Contributing

Contributions are welcome! Please open an issue or pull request on the project repository.

## License

This project is licensed under the Apache-2.0 License.

## 📞 Support

- Open an issue on GitHub
- Join our [Discord server](https://discord.gg/tSN2Qn9uM8)
- See each server's README for documentation and guides
