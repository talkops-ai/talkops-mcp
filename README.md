# CloudBrain MCP Servers

A suite of Model Context Protocol (MCP) servers for DevOps tools and technologies, enabling AI assistants and automation to interact with modern infrastructure and deployment technologies.

This repository serves as the **central hub for all MCP servers** built to support a wide range of DevOps tools and workflows. Each MCP server provides a standardized interface for AI agents and automation platforms to interact with specific tools, services, or platforms, making it easier to integrate, automate, and extend DevOps operations across diverse environments.

- **Kubernetes Package Management:** For managing Kubernetes workloads, the Helm MCP Server enables AI-driven Helm chart operations and best practices.
- **CI/CD, Build & Release:** Dedicated MCP servers (e.g., ArgoCD MCP Server, Jenkins MCP Server) will provide automation and orchestration for continuous integration, delivery, and deployment pipelines.
- **Cloud Orchestration:** Dedicated MCP Servers like Terraform MCP Server will provides comprehensive infrastructure as code management with secure command execution, semantic document search, and intelligent document ingestion for AWS, Azure, Google Cloud, and more.
- **Observability & Monitoring:** For monitoring and observability, specialized MCP servers will be available for Prometheus, the TICK stack (Telegraf, InfluxDB, Chronograf, Kapacitor), and other monitoring solutions.

The vision for CloudBrain MCP Servers is to offer a **modular, extensible, and unified platform** where each DevOps domain—whether infrastructure as code, CI/CD, cloud orchestration, or observability—can be managed through a dedicated MCP server. This approach empowers AI agents and automation tools to deliver intelligent, context-aware DevOps workflows, regardless of the underlying technology stack.

## Table of Contents

- [CloudBrain MCP Servers](#cloudbrain-mcp-servers)
  - [Table of Contents](#table-of-contents)
  - [Available Servers](#available-servers)
    - [Terraform MCP Server](#terraform-mcp-server)
    - [Helm MCP Server](#helm-mcp-server)
    - [ArgoCD MCP Server](#argocd-mcp-server)
    - [Agents Central Registry](#agents-central-registry)
  - [Installation and Setup](#installation-and-setup)
  - [Contributing](#contributing)
  - [License](#license)

## Available Servers

### Terraform MCP Server

[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/)
[![Terraform](https://img.shields.io/badge/terraform-supported-brightgreen)](https://www.terraform.io/)
[![Neo4j](https://img.shields.io/badge/neo4j-vector%20search-orange)](https://neo4j.com/)

A comprehensive Model Context Protocol (MCP) server for Terraform operations, featuring secure command execution, semantic document search, and intelligent document ingestion with vector embeddings and Neo4j integration.

- **Secure Terraform Execution**
  - Enterprise-grade security with command whitelisting and validation
  - Directory traversal protection and dangerous pattern detection
  - Configurable timeouts and comprehensive output processing
  - Support for all major Terraform commands (init, plan, validate, apply, destroy)
- **Semantic Document Search**
  - Vector similarity search over Terraform documentation using Neo4j
  - Multi-type search across resources, data sources, and best practices
  - Advanced filtering with similarity thresholds and node type filtering
  - HNSW-based similarity search with 1536-dimensional embeddings
- **Intelligent Document Ingestion**
  - Multi-format support for HTML, Markdown, and PDF documents
  - AI-powered content structuring with LLM integration
  - Incremental processing with skip logic for already ingested documents
  - Structured chunking with metadata preservation
- **Multi-Provider AI Support**
  - OpenAI, Anthropic, Azure OpenAI, HuggingFace, Cohere, Ollama integration
  - Configurable LLM providers for document processing and search
  - Flexible embedding models with customizable dimensions
- **Neo4j Vector Database**
  - Graph database storage with vector indexes for semantic search
  - Comprehensive metadata tracking and relationship modeling
  - High-performance query capabilities with connection reuse

[Learn more](src/terraform-mcp-server/README.md)

### Helm MCP Server

[![Docker](https://img.shields.io/badge/docker-ready-blue)](https://hub.docker.com/)
[![Helm](https://img.shields.io/badge/helm-supported-brightgreen)](https://helm.sh/)

A Model Context Protocol (MCP) server for managing Kubernetes workloads via Helm, inspired by EKS MCP and Terraform MCP architectures.

- **Helm Best Practices**
  - Prescriptive guidance for Helm chart usage and deployment
  - Security and compliance recommendations for Kubernetes workloads
  - Multi-cluster and context-aware operations
- **Helm Operations**
  - Install, upgrade, list, uninstall Helm releases
  - Search public Helm repositories (ArtifactHub, GitHub, etc.)
  - Pass complex/nested values, multiple values files, and extra CLI flags
  - Robust error handling and logging
- **Multi-Cluster Support**
  - Switch between clusters via kubeconfig, context, or EKS cluster name
  - Generic, production-ready Kubernetes authentication
- **Documentation and Resources**
  - Access Helm best practices and workflow guides as MCP resources
  - Rich metadata for Helm charts and repositories

[Learn more](src/helm-mcp-server/README.md)

### ArgoCD MCP Server

[![Docker](https://img.shields.io/badge/docker-ready-blue)](https://hub.docker.com/)
[![ArgoCD](https://img.shields.io/badge/argocd-supported-brightgreen)](https://argoproj.github.io/argo-cd/)

A Model Context Protocol (MCP) server for managing Kubernetes applications and resources via ArgoCD using GitOps principles.

- **GitOps Best Practices**
  - Prescriptive guidance for ArgoCD application management
  - Security and compliance recommendations for Kubernetes workloads
  - Automated sync and self-healing capabilities
  - Comprehensive resource monitoring and management
- **ArgoCD Operations**
  - Create, update, delete, and sync applications
  - Manage application resources and their lifecycle
  - Retrieve logs, events, and resource actions
  - Robust error handling and logging
- **Resource Management**
  - Get resource trees and managed resources
  - Retrieve workload logs and events
  - Execute resource actions
  - Monitor application health and status
- **Documentation and Resources**
  - Access ArgoCD best practices and workflow guides
  - Rich metadata for applications and resources
  - Comprehensive error handling and logging

[Learn more](src/argocd-mcp-server/README.md)

### Agents Central Registry

[![Python 3.10](https://img.shields.io/badge/python-3.10-blue.svg)](https://www.python.org/downloads/)
[![MCP Protocol](https://img.shields.io/badge/MCP-Protocol-green.svg)](https://modelcontextprotocol.io/)

A central registry service that leverages the Model Context Protocol (MCP) to enable dynamic discovery and interaction between Google A2A (Agent-to-Agent) agents and various MCP servers. This system serves as a discovery hub for DevOps agents, facilitating seamless integration and communication across distributed agent architectures.

- **Dynamic Agent Discovery**
  - Enable agentic systems to dynamically find and connect with Google A2A agents
  - Natural language queries to find agents and servers using descriptive capabilities
  - Compatibility validation between agents and MCP servers
- **MCP Server Discovery**
  - Allow individual agents to discover capability-matched MCP servers
  - Intelligent task mapping to the most suitable specialized agents
  - Real-time registry updates as agents and servers come online or offline
- **Standardized Integration**
  - Provide a unified interface for agent communication using MCP protocol
  - Centralized agent management through a single registry
  - Support for complex multi-agent DevOps workflows with automatic task routing
- **Scalable Architecture**
  - Support growing numbers of agents and MCP servers
  - Self-registration capabilities for executor agents
  - Dynamic tool integration as new MCP servers become available

[Learn more](src/agents-mcp-server/README.md)

## Installation and Setup

Each server has specific installation instructions.
See each server's detailed README for specific requirements and configuration options.

## Contributing

Contributions are welcome! Please open an issue or pull request on the project repository.

## License

This project is licensed under the Apache-2.0 License.
