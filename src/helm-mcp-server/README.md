# TalkOps Helm MCP Server & Agent Plugin (`v0.5.0`)

[![PyPI](https://img.shields.io/pypi/v/talkops-helm-mcp-server)](https://pypi.org/project/talkops-helm-mcp-server/)
[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![FastMCP](https://img.shields.io/badge/FastMCP-2.13+-green.svg)](https://github.com/jlowin/fastmcp)

A production-grade Model Context Protocol (MCP) execution server and portable Agent Plugin for managing Kubernetes workloads with Helm.

Built on the **Two-Layer Separation Principle**:
- **Skill Layer (`skills/` + `plugin.json`):** Procedural runbooks, values-authoring standards, error-recovery decision trees, security review checklists, and zero-network local Python validation scripts (`SKILL.md` progressive disclosure).
- **Execution Layer (`helm_mcp_server/`):** Deterministic, context-isolated, secret-redacted Helm CLI and Kubernetes API execution primitives (13 Tools, 10 URI-addressed Resources, 0 Prompts).

---

## Architecture Overview

```text
src/helm-mcp-server/
├── plugin.json                                     # Agent Plugin v1.0.0 manifest
├── mcp.json                                        # Portable MCP server launch configuration
├── skills/                                         # Copy-pasteable Agent Skills (Progressive Disclosure)
│   ├── deploying-helm-charts/
│   │   ├── SKILL.md
│   │   ├── references/
│   │   │   ├── known-repositories.md
│   │   │   └── values-authoring.md
│   │   └── scripts/
│   │       ├── validate_values.py
│   │       └── validate_manifests.py
│   ├── upgrading-and-rolling-back-helm-releases/
│   │   ├── SKILL.md
│   │   └── references/
│   │       ├── upgrade-checklist.md
│   │       └── rollback-sop.md
│   ├── troubleshooting-helm-releases/
│   │   ├── SKILL.md
│   │   └── references/
│   │       └── error-catalog.md
│   └── reviewing-helm-release-security/
│       ├── SKILL.md
│       ├── references/
│       │   └── security-checklist.md
│       └── scripts/
│           └── scan_manifest_security.py
└── helm_mcp_server/                                # FastMCP Execution Server
    ├── config.py                                   # Read-only default, toolsets, env/CLI overrides
    ├── main.py                                     # CLI entrypoint (--transport, --allow-write, --toolsets)
    ├── server/                                     # FastMCP core, middleware, bootstrap
    ├── services/                                   # HelmService & KubernetesService (session context isolated)
    ├── tools/                                      # 13 focused MCP tools (Read, Mutate, Session tiers)
    ├── resources/                                  # 10 URI-addressed MCP resources
    └── utils/                                      # Secret redaction, semver comparison, manifest diffing
```

---

## Bundled Agent Skills (`skills/`)

The `skills/` directory is self-contained and can be installed directly via the root `plugin.json` or copied into any agent skill directory (e.g., `.claude/skills/`, `.gemini/skills/`, `.cursor/skills/`):

| Skill Name | Purpose | Local Scripts & References |
|---|---|---|
| `deploying-helm-charts` | End-to-end discovery, values authoring, pre-flight planning, and chart installation | `scripts/validate_values.py`, `scripts/validate_manifests.py`, `references/known-repositories.md`, `references/values-authoring.md` |
| `upgrading-and-rolling-back-helm-releases` | Safe live diffing (`helm_plan_release`), values-merge strategy selection, upgrades, and rollbacks | `references/upgrade-checklist.md`, `references/rollback-sop.md` |
| `troubleshooting-helm-releases` | Root-cause diagnosis and remediation for `CrashLoopBackOff`, `ImagePullBackOff`, `OOMKilledRecurring`, `ProgressDeadlineExceeded`, and CRD conflicts | `references/error-catalog.md` |
| `reviewing-helm-release-security` | Pre-deployment Kubernetes manifest security auditing (privileged containers, host namespaces, RBAC wildcards, mutable tags) | `scripts/scan_manifest_security.py`, `references/security-checklist.md` |

---

## MCP Execution Surface

### 1. Tools (13 Total — All $\le 8$ Parameters)

Mutating tools (`mutate` tag) are **hidden by default** when `MCP_ALLOW_WRITE=false` (the default). Enable them with `MCP_ALLOW_WRITE=true` or `--allow-write`.

| Tier / Tag | Tool Name | Description |
|---|---|---|
| `read` | `helm_search_charts` | Search configured Helm chart repositories by keyword (`query`, `repository`, `versions`, `limit`) |
| `read` | `helm_list_releases` | List Helm releases across or within namespaces with status filter and pagination (`limit`, `offset`) |
| `read` | `helm_get_release_status` | Single-call release status summary with resource counts and links to `/history`, `/values`, and `/manifest` resources |
| `read` | `helm_render_manifests` | Render Kubernetes manifests (`helm template`) with automatic `Secret` and sensitive `env` redaction |
| `read` | `helm_plan_release` | **N-to-1 release planner**: computes install preview for new releases or live manifest diff (added/removed/modified resources, image & replica changes) for existing releases |
| `read` | `helm_monitor_deployment` | Multi-layer rollout health monitor checking Helm status, `Deployment`/`StatefulSet` rollout conditions, and container failure states |
| `read` | `kubernetes_check_prerequisites` | Verify cluster semantic version and API resource/CRD availability via Kubernetes Discovery APIs |
| `session` | `kubernetes_set_context` | Switch active Kubernetes context for the current MCP session (propagates `--kube-context` to all Helm CLI and Kubernetes API calls) |
| `mutate` | `helm_ensure_repository` | Register and index a Helm chart repository (`helm repo add` + `helm repo update`) |
| `mutate` | `helm_install_chart` | Install a new Helm release with explicit typed parameters (`chart_ref`, `release_name`, `namespace`, `values`, `version`, `create_namespace`, `skip_crds`, `wait_timeout`) |
| `mutate` | `helm_upgrade_release` | Upgrade an existing Helm release (`release_name`, `chart_ref`, `namespace`, `values`, `version`, `values_strategy`, `wait_timeout`, `atomic`) |
| `mutate` | `helm_rollback_release` | Roll back a release to a previous revision (`release_name`, `namespace`, `revision`, `wait_timeout`, `dry_run`) |
| `mutate` | `helm_uninstall_release` | Uninstall a Helm release (`release_name`, `namespace`, `keep_history`) |

### 2. URI-Addressed Resources (10 Total)

| Resource URI | MIME Type | Description |
|---|---|---|
| `helm://repositories` | `application/json` | Configured Helm chart repositories (`helm repo list`) |
| `helm://charts/{repository}/{chart_name}` | `application/json` | Chart metadata, `kubeVersion` constraint, and dependencies (`Chart.yaml`) |
| `helm://charts/{repository}/{chart_name}/values` | `application/x-yaml` | Default `values.yaml` for a chart |
| `helm://charts/{repository}/{chart_name}/readme` | `text/markdown` | Chart `README.md` documentation |
| `helm://releases/{namespace}/{release_name}/history` | `application/json` | Revision history for a deployed release |
| `helm://releases/{namespace}/{release_name}/values` | `application/json` | Redacted user-supplied values for a deployed release |
| `helm://releases/{namespace}/{release_name}/manifest` | `application/x-yaml` | Secret-redacted Kubernetes YAML manifest for a deployed release |
| `kubernetes://cluster-info` | `application/json` | Active cluster version, node summary, and namespace summary |
| `kubernetes://namespaces` | `application/json` | List of Kubernetes namespaces in the active cluster |
| `kubernetes://contexts` | `application/json` | Available kubeconfig contexts and active session context |

---

## Configuration & Running

### Environment Variables

| Variable | Default | Description |
|---|---|---|
| `MCP_TRANSPORT` | `stdio` | Transport mode: `stdio` or `http` (Streamable HTTP) |
| `MCP_ALLOW_WRITE` | `false` | Enable mutating tools (`helm_install_chart`, `helm_upgrade_release`, etc.) |
| `MCP_TOOLSETS` | `all` | Comma-separated toolsets to expose: `all`, `read`, `mutate` |
| `MCP_READ_ONLY` | `false` | Force read-only mode (`allow_write=False`, `toolsets=["read"]`) |
| `KUBECONFIG` | `~/.kube/config` | Path to Kubernetes configuration file |
| `HELM_TIMEOUT` | `300` | Timeout in seconds for Helm CLI subprocesses |
| `MCP_HOST` / `MCP_PORT` | `0.0.0.0` / `8765` | Bind host and port when `MCP_TRANSPORT=http` |

### CLI Usage

```bash
# Default: Read-only mode over stdio
uv run helm-mcp-server

# Write-enabled mode over stdio
uv run helm-mcp-server --allow-write

# Streamable HTTP mode on port 8765 with write enabled
uv run helm-mcp-server --transport http --port 8765 --allow-write
```

---

## Development & Testing

```bash
# Install dependencies including dev test suite
uv sync --dev

# Run unit and in-memory FastMCP integration tests
uv run pytest tests/ -v --tb=short

# Run static type checking
uv run pyright .

# Build wheel and sdist
uv build
```
