# OpenTelemetry MCP Server

Let your AI assistant manage OpenTelemetry on Kubernetes: provision OpenTelemetry Collector topologies, roll out zero-code auto-instrumentation, tune head/tail sampling and cardinality processors, audit pipeline security, and diagnose dropped telemetry.

## Quick Reference

- **Maintained by:** [TalkOps](https://talkops.ai) ([GitHub repository](https://github.com/talkops-ai/talkops-mcp/tree/main/src/opentelemetry-mcp-server))
- **Supported tags:** `latest`, `0.2.1`
- **Architectures:** `linux/amd64`, `linux/arm64`
- **Documentation:** [https://talkops.ai/docs/integrations/opentelemetry-mcp-server/overview](https://talkops.ai/docs/integrations/opentelemetry-mcp-server/overview)
- **PyPI alternative:** [`talkops-opentelemetry-mcp-server`](https://pypi.org/project/talkops-opentelemetry-mcp-server/)
- **License:** [Apache License 2.0](https://github.com/talkops-ai/talkops-mcp/blob/main/LICENSE)

## What You Get

- **17 MCP tools** (7 read-only) built for AI agents and MCP clients
- **14 MCP resources** under `otel://` for structured context discovery
- **7 Agent Skills** bundled in `/app/skills` ([browse on GitHub](https://github.com/talkops-ai/talkops-mcp/tree/main/src/opentelemetry-mcp-server/skills))
- **Container ready:** Runs as a minimal non-root image (`linux/amd64`, `linux/arm64`) with offline OTTL/YAML validation and Kubernetes API integration.
- **Safe by default:** starts in read-only mode until you explicitly set `MCP_ALLOW_WRITE=true`.

---

## Quick Start (MCP Client over `stdio`)

Use this configuration in **Claude Desktop**, **Cursor**, **Windsurf**, or **VS Code** (`mcp.json` / `claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "opentelemetry": {
      "command": "docker",
      "args": [
        "run",
        "-i",
        "--rm",
        "-e",
        "MCP_TRANSPORT=stdio",
        "-v",
        "/path/to/your/kubeconfig:/app/.kube/config:ro",
        "talkopsai/opentelemetry-mcp-server:latest"
      ]
    }
  }
}
```

Using **Claude Code**? Register it in one command:

```bash
claude mcp add opentelemetry -- docker run -i --rm -e MCP_TRANSPORT=stdio -v ~/.kube/config:/app/.kube/config:ro talkopsai/opentelemetry-mcp-server:latest
```

> **Tip:** If your kubeconfig references external client certificate files (for example with `minikube` or `kind`), mount the full `~/.kube` directory (`-v /path/to/.kube:/app/.kube:ro`) so those files are reachable inside the container.

Restart your MCP client and try asking:

- *"Give me an overview of OpenTelemetry in my cluster."*
- *"Which workloads in `shop` aren't instrumented yet?"*
- *"My collector is dropping spans. What's wrong?"*

---

## Running Standalone (Streamable HTTP)

By default (`MCP_TRANSPORT=http`), the container starts an MCP Streamable HTTP server on port `8771` so multiple clients can share a single instance:

```bash
docker run --rm -p 8771:8771 \
  -v ~/.kube/config:/app/.kube/config:ro \
  talkopsai/opentelemetry-mcp-server:latest
```

Point your MCP client at `http://localhost:8771/mcp`:

```json
{
  "mcpServers": {
    "opentelemetry": {
      "url": "http://localhost:8771/mcp"
    }
  }
}
```

---

## Allowing Changes (Write Mode)

Out of the box, the container runs in **read-only mode** (`MCP_ALLOW_WRITE=false`). To allow mutations (creating or modifying OpenTelemetryCollectors, Instrumentations, and collector pipeline configs), pass `-e MCP_ALLOW_WRITE=true` to `docker run`. Even with writes enabled, changes support dry-run previews and destructive operations require explicit confirmation.

---

## Environment Variables

| Variable | Container Default | Description |
| :--- | :--- | :--- |
| `K8S_KUBECONFIG` | `/app/.kube/config` | Path to mounted kubeconfig inside the container |
| `K8S_CONTEXT` | current context | Kubernetes context name to target |
| `MCP_ALLOW_WRITE` | `false` | Set to `true` to enable cluster mutations |
| `MCP_TOOLSETS` | `all` | Filter tools: `discovery`, `collector`, `instrumentation`, `pipeline`, `diagnostics`, `governance`, `readonly` |
| `OTEL_COLLECTOR_VERSION_DEFAULT` | `0.152.1` | Default Collector version used when provisioning new collectors |
| `MCP_TRANSPORT` | `http` | `http` (standalone server) or `stdio` (MCP client subprocess) |
| `MCP_PORT` | `8771` | HTTP listen port inside the container |

---

## Available Tools (17)

| Tool | Access | Description |
| :--- | :--- | :--- |
| `otel_audit_security_posture` | Read | Audit the security posture of OpenTelemetry collectors, instrumentation, eBPF/OBI agents, and RBAC. |
| `otel_configure_connectors` | Write (destructive) | Configure spanmetrics and/or servicegraph connectors on a collector. |
| `otel_configure_processing` | Write | Configure OTTL transform and filter processors for PII masking, JSON parsing, attribute dropping, and noise reduction. |
| `otel_configure_receivers` | Write (destructive) | Configure Kubernetes infrastructure, log, and Prometheus TA receivers. |
| `otel_configure_sampling` | Write (destructive) | Configure trace sampling strategy across collector and Instrumentation CRs. |
| `otel_delete_resource` | Write (destructive) | Delete an OpenTelemetry Custom Resource after confirmation. |
| `otel_diagnose_collector` | Read | Perform a comprehensive single-call runtime and configuration diagnosis of a collector. |
| `otel_list_workloads` | Read | List Kubernetes workloads and their OpenTelemetry instrumentation state. |
| `otel_manage_workload_instrumentation` | Write (destructive) | Enable, disable, or restart OpenTelemetry auto-instrumentation on a workload. |
| `otel_patch_collector` | Write (destructive) | Create or patch an OpenTelemetryCollector CRD with pre-apply validation. |
| `otel_patch_instrumentation` | Write (destructive) | Create or patch an OpenTelemetry Instrumentation CRD. |
| `otel_provision_collector` | Write (destructive) | Provision an OpenTelemetry Collector CRD and least-privilege RBAC from intent. |
| `otel_query_a2ui` | Read | Retrieve the status of all OpenTelemetry Collectors and their pipelines. |
| `otel_revert_collector_config` | Write (destructive) | Revert a collector to its pre-mutation config snapshot (one-level undo). |
| `otel_survey_cluster` | Read | Survey the cluster's complete OpenTelemetry posture in a single call. |
| `otel_validate_collector_config` | Read | Validate a live OpenTelemetryCollector CR or raw YAML configuration. |
| `otel_verify_instrumentation` | Read | Verify end-to-end auto-instrumentation for a workload in a single call. |

---

## Bundled Agent Skills (7)

This image also ships step-by-step operational playbooks (`SKILL.md`) under `/app/skills`:

- [`auditing-observability-security-posture`](https://github.com/talkops-ai/talkops-mcp/blob/main/src/opentelemetry-mcp-server/skills/auditing-observability-security-posture/SKILL.md)
- [`controlling-telemetry-cardinality-and-noise`](https://github.com/talkops-ai/talkops-mcp/blob/main/src/opentelemetry-mcp-server/skills/controlling-telemetry-cardinality-and-noise/SKILL.md)
- [`instrumenting-kubernetes-workloads`](https://github.com/talkops-ai/talkops-mcp/blob/main/src/opentelemetry-mcp-server/skills/instrumenting-kubernetes-workloads/SKILL.md)
- [`provisioning-opentelemetry-collectors`](https://github.com/talkops-ai/talkops-mcp/blob/main/src/opentelemetry-mcp-server/skills/provisioning-opentelemetry-collectors/SKILL.md)
- [`troubleshooting-telemetry-pipelines`](https://github.com/talkops-ai/talkops-mcp/blob/main/src/opentelemetry-mcp-server/skills/troubleshooting-telemetry-pipelines/SKILL.md)
- [`tuning-sampling-and-trace-derived-metrics`](https://github.com/talkops-ai/talkops-mcp/blob/main/src/opentelemetry-mcp-server/skills/tuning-sampling-and-trace-derived-metrics/SKILL.md)
- [`upgrading-opentelemetry-components`](https://github.com/talkops-ai/talkops-mcp/blob/main/src/opentelemetry-mcp-server/skills/upgrading-opentelemetry-components/SKILL.md)

To copy the skills onto your workstation for Claude Code or Cursor:

```bash
docker run --rm --entrypoint tar talkopsai/opentelemetry-mcp-server:latest -C /app/skills -cf - . | tar -xf - -C ~/.claude/skills/
```

---

## Support & Community

- **Source & full docs:** [github.com/talkops-ai/talkops-mcp/tree/main/src/opentelemetry-mcp-server](https://github.com/talkops-ai/talkops-mcp/tree/main/src/opentelemetry-mcp-server)
- **Issues & feature requests:** [GitHub Issues](https://github.com/talkops-ai/talkops-mcp/issues/new?labels=opentelemetry-mcp-server)
- **Community Slack:** [talkops.ai/slack](https://talkops.ai/slack/)
