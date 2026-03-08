# TalkOps MCP Servers

A suite of Model Context Protocol (MCP) servers for DevOps tools and technologies, enabling AI assistants and automation to interact with modern infrastructure and deployment technologies.

This repository serves as the **central hub and MCP registry** for all MCP servers built to support a wide range of DevOps tools and workflows. Each MCP server provides a standardized interface for AI agents and automation platforms to interact with specific tools, services, or platforms, making it easier to integrate, automate, and extend DevOps operations across diverse environments.

- **Kubernetes Package Management:** For managing Kubernetes workloads, the Helm MCP Server enables AI-driven Helm chart operations and best practices.
- **CI/CD, Build & Release:** Dedicated MCP servers (e.g., ArgoCD MCP Server, Jenkins MCP Server) provide automation and orchestration for continuous integration, delivery, and deployment pipelines.
- **Cloud Orchestration:** Dedicated MCP Servers like Terraform MCP Server provide comprehensive infrastructure as code management with secure command execution, semantic document search, and intelligent document ingestion for AWS, Azure, Google Cloud, and more.
- **Observability & Monitoring:** For monitoring and observability, specialized MCP servers will be available for Prometheus, the TICK stack (Telegraf, InfluxDB, Chronograf, Kapacitor), and other monitoring solutions.

The vision for TalkOps MCP Servers is to offer a **modular, extensible, and unified platform** where each DevOps domain—whether infrastructure as code, CI/CD, cloud orchestration, or observability—can be managed through a dedicated MCP server. This approach empowers AI agents and automation tools to deliver intelligent, context-aware DevOps workflows, regardless of the underlying technology stack.

## Table of Contents

- [TalkOps MCP Servers](#talkops-mcp-servers)
  - [Table of Contents](#table-of-contents)
  - [Available MCP Servers](#available-mcp-servers)
    - [📦 Kubernetes Package Management](#kubernetes-package-management)
    - [🚀 CI/CD & GitOps](#cicd--gitops)
    - [🏗️ Cloud Orchestration & Infrastructure](#cloud-orchestration--infrastructure)
    - [🔗 Agent Discovery & Registry](#agent-discovery--registry)
  - [Contributing](#contributing)
  - [License](#license)
  - [Support](#-support)

---

## Available MCP Servers

Each table lists MCP servers by DevOps domain. Use **Quick Install** for the recommended setup (Docker preferred; CLI if no Docker), **README** for full documentation, and **Config** for MCP client configuration in that server's README.

<a id="kubernetes-package-management"></a>
### 📦 Kubernetes Package Management

| Server Name | Description | Quick Install | README | Config | Video |
|-------------|-------------|---------------|--------|--------|-------|
| [Helm MCP Server](src/helm-mcp-server) | Search charts, install/upgrade/rollback releases, validate manifests, monitor deployments. Full Helm lifecycle with dry-run and multi-cluster support. | `docker run -p 8765:8765 -v ~/.kube/config:/app/.kube/config:ro talkopsai/helm-mcp-server:latest` | [README](src/helm-mcp-server/README.md) | [Config](src/helm-mcp-server/README.md#quick-start-with-docker-recommended) | [▶ Watch](https://youtu.be/efU7TatQCqI?si=YYZC9BvBqmeq93_x) |

<a id="cicd--gitops"></a>
### 🚀 CI/CD & GitOps

| Server Name | Description | Quick Install | README | Config | Video |
|-------------|-------------|---------------|--------|--------|-------|
| [ArgoCD MCP Server](src/argocd-mcp-server) | Manage ArgoCD applications, sync deployments, onboard repositories, create projects, debug with guided workflows. GitOps with credential isolation. | `docker run -p 8770:8770 -e ARGOCD_SERVER_URL=... -e ARGOCD_AUTH_TOKEN=... -e MCP_ALLOW_WRITE=true talkopsai/argocd-mcp-server:latest` | [README](src/argocd-mcp-server/README.md) | [Config](src/argocd-mcp-server/README.md#configuration) | [▶ Overview](https://youtu.be/5V0wo4jkUtQ)<br>[▶ Demo](https://youtu.be/gfMLUK9YcGc) |

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
