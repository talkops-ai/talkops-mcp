<p align="center">
  <img src="https://raw.githubusercontent.com/cncf/artwork/main/projects/opentelemetry/icon/color/opentelemetry-icon-color.svg" alt="OpenTelemetry logo" height="100"/>
</p>

<h1 align="center">OpenTelemetry MCP Server &amp; Agent Plugin</h1>

<p align="center">
  Production-grade OpenTelemetry on Kubernetes with strict <strong>Knowledge Layer (Agent Skills)</strong> and <strong>Execution Layer (MCP Server)</strong> separation — intent-driven collector provisioning, multi-language auto-instrumentation, single-call N→1 pipeline diagnostics, OTTL cardinality & PII governance, and security posture auditing.
</p>

<p align="center">
  <a href="https://pypi.org/project/talkops-opentelemetry-mcp-server/"><img src="https://img.shields.io/pypi/v/talkops-opentelemetry-mcp-server.svg?style=flat-square&logo=pypi&logoColor=white&label=PyPI" alt="PyPI"/></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/Python-3.12%2B-3776AB.svg?style=flat-square&logo=python&logoColor=white" alt="Python 3.12+"/></a>
  <a href="https://github.com/talkops-ai/talkops-mcp/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-Apache%202.0-blue.svg?style=flat-square" alt="License"/></a>
  <a href="https://modelcontextprotocol.io/"><img src="https://img.shields.io/badge/MCP-Model%20Context%20Protocol-4A90D9.svg?style=flat-square" alt="MCP"/></a>
  <a href="https://opentelemetry.io/"><img src="https://img.shields.io/badge/OpenTelemetry-Collector%20v0.152%2B-4B5EFF.svg?style=flat-square&logo=opentelemetry&logoColor=white" alt="OpenTelemetry"/></a>
</p>

---

Let your AI assistant run OpenTelemetry on Kubernetes: set up collectors, auto-instrument workloads, configure sampling and processing, and debug pipelines that drop data. It checks every change before applying it.

## What you get

- **17 MCP tools** (7 read-only) that work against your live OpenTelemetry setup
- **14 resources** your assistant can read for context, under `otel://`
- **7 Agent Skills**: step-by-step playbooks that teach your assistant how to use the tools well
- **Safe by default**: only read-only tools are loaded until you turn on writes, and changes are previewed or confirmed before they happen

## Quick start

**You'll need:**

- Python 3.12+ and [uv](https://docs.astral.sh/uv/getting-started/installation/), **or** [Docker](https://docs.docker.com/get-docker/)
- Access to a Kubernetes cluster with the OpenTelemetry Operator installed (through a kubeconfig file)

**1. Add the server to your MCP client.** For Claude Desktop, Cursor, Windsurf, and most other clients, add this to your MCP config file:

```json
{
  "mcpServers": {
    "opentelemetry": {
      "command": "uvx",
      "args": [
        "--from",
        "talkops-opentelemetry-mcp-server",
        "opentelemetry-mcp-server"
      ],
      "env": {
        "KUBECONFIG": "/path/to/your/kubeconfig"
      }
    }
  }
}
```

Using Claude Code? Run this instead:

```bash
claude mcp add opentelemetry -e KUBECONFIG=/path/to/your/kubeconfig -- uvx --from talkops-opentelemetry-mcp-server opentelemetry-mcp-server
```

`uvx` downloads [`talkops-opentelemetry-mcp-server`](https://pypi.org/project/talkops-opentelemetry-mcp-server/) from PyPI and runs it, so there's nothing else to install. Prefer a normal install? Run `pip install talkops-opentelemetry-mcp-server` and use `opentelemetry-mcp-server` as the command.

**Prefer Docker?** Pull [`talkopsai/opentelemetry-mcp-server`](https://hub.docker.com/r/talkopsai/opentelemetry-mcp-server) from Docker Hub—no Python setup needed:

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

**2. Restart your client and try asking:**

- *"Give me an overview of OpenTelemetry in my cluster."*
- *"Which workloads in `shop` aren't instrumented yet?"*
- *"My collector is dropping spans. What's wrong?"*

## Allowing changes

Out of the box the server is read-only. To let your assistant make changes (creating and changing collectors, instrumentation, and pipeline settings), add `"--allow-write"` to `args` (or pass `-e MCP_ALLOW_WRITE=true` to `docker run`). Even then, changes are previewed first and destructive actions ask for confirmation.

## Configuration

Set these as environment variables (the `env` block in your client config, or `-e` with `docker run`) or pass the matching flag.

| Variable | Flag | Default | What it does |
| :--- | :--- | :--- | :--- |
| `K8S_KUBECONFIG` / `KUBECONFIG` | `--kubeconfig` | `~/.kube/config` | Kubeconfig file to use |
| `K8S_CONTEXT` | `--context` | current context | Kubernetes context to use |
| `MCP_ALLOW_WRITE` | `--allow-write` | `false` | Enable tools that change your cluster |
| `MCP_TOOLSETS` | `--toolsets` | `all` | Limit tools: `discovery`, `collector`, `instrumentation`, `pipeline`, `diagnostics`, `governance`, `readonly` |
| `OTEL_COLLECTOR_VERSION_DEFAULT` | `--collector-version-default` | `0.152.1` | Collector version used for new collectors |
| `MCP_TRANSPORT` | `--transport` | `stdio` | `stdio` or `http` |
| `MCP_PORT` | `--port` | `8768` (`8771` in Docker) | Port when using HTTP |

Run `uvx --from talkops-opentelemetry-mcp-server opentelemetry-mcp-server --help` to see every option.

### Running over HTTP

To share one server between several clients or run it remotely, start it in HTTP mode with Docker or `uvx`:

```bash
# With Docker (starts in HTTP mode by default)
docker run --rm -p 8771:8771 \
  -v ~/.kube/config:/app/.kube/config:ro \
  talkopsai/opentelemetry-mcp-server:latest

# Or with uvx
MCP_TRANSPORT=http MCP_PORT=8771 uvx --from talkops-opentelemetry-mcp-server opentelemetry-mcp-server
```

Then point your client at `http://localhost:8771/mcp`:

```json
{
  "mcpServers": {
    "opentelemetry": {
      "url": "http://localhost:8771/mcp"
    }
  }
}
```

## Agent Skills

Skills live in [`skills/`](skills/). Each one is a `SKILL.md` playbook (plus optional `references/` and offline `scripts/`) that teaches your AI assistant *how* to do a job safely, while the MCP server does the actual work. Tools are the hands, skills are the know-how.

To use them, copy the folders into your assistant's skills directory, for example:

```bash
git clone https://github.com/talkops-ai/talkops-mcp.git
cp -r talkops-mcp/src/opentelemetry-mcp-server/skills/* ~/.claude/skills/
```

This folder is also a portable [Agent Plugin](https://agent-plugins.org) (`plugin.json` + `mcp.json` + `skills/`), so plugin-aware clients can load the server and skills together.

| Skill | Use it to |
| :--- | :--- |
| [`provisioning-opentelemetry-collectors`](skills/provisioning-opentelemetry-collectors/SKILL.md) | Pick a collector layout and set it up with the right size and permissions. |
| [`instrumenting-kubernetes-workloads`](skills/instrumenting-kubernetes-workloads/SKILL.md) | Auto-instrument apps in any language, or use eBPF where you can't. |
| [`troubleshooting-telemetry-pipelines`](skills/troubleshooting-telemetry-pipelines/SKILL.md) | Find out why telemetry is missing or the collector is crashing. |
| [`tuning-sampling-and-trace-derived-metrics`](skills/tuning-sampling-and-trace-derived-metrics/SKILL.md) | Set up head and tail sampling and span metrics. |
| [`controlling-telemetry-cardinality-and-noise`](skills/controlling-telemetry-cardinality-and-noise/SKILL.md) | Drop noisy attributes and redact sensitive data. |
| [`auditing-observability-security-posture`](skills/auditing-observability-security-posture/SKILL.md) | Check for leaked secrets, missing TLS, and over-broad permissions. |
| [`upgrading-opentelemetry-components`](skills/upgrading-opentelemetry-components/SKILL.md) | Upgrade collectors and the Operator without breaking configs. |

## Reference

<details>
<summary><strong>All 17 tools</strong></summary>

| Tool | Access | What it does |
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

</details>

<details>
<summary><strong>All 14 resources</strong></summary>

| Resource | What it returns |
| :--- | :--- |
| `otel://cluster/contexts` | Available Kubernetes contexts from kubeconfig and which context this MCP server instance is bound to. |
| `otel://operator/status` | OpenTelemetry Operator pod health, mutating webhook diagnostics, recent redacted error logs, and per-namespace Instrumentation CR counts. |
| `otel://server/capabilities` | Server execution mode (write_enabled, read_only, toolsets), bound kubeconfig context, Kubernetes API connectivity, and default Collector version. |
| `otel://collector/{namespace}/{name}` | Configuration summary, pipeline topology, deployment mode, GitOps ownership, and runtime status of an OpenTelemetryCollector CRD. |
| `otel://collector/{namespace}/{name}/config` | Redacted YAML configuration of an OpenTelemetryCollector CRD (inline secrets masked with ***REDACTED***). |
| `otel://collector/{namespace}/{name}/history` | Metadata and redacted preview of the pre-mutation config snapshot stored in otel.mcp/last-known-good. |
| `otel://collectors/{namespace}` | Summary list of OpenTelemetryCollector CRDs in a namespace (use namespace='all' for cluster-wide listing). |
| `otel://instrumentation/{namespace}/{name}` | Redacted Instrumentation CRD details: exporter endpoint, propagators, sampler config, per-language specs, and resource attributes. |
| `otel://instrumentations/{namespace}` | Summary list of Instrumentation CRDs in a namespace (use namespace='all' for cluster-wide listing). |
| `otel://k8s-enrichment/{namespace}/{collector}` | k8sattributes processor profile showing extracted metadata, labels, annotations, node filtering, pod association, and pipeline positions. |
| `otel://logs-profile/{namespace}/{collector}` | Filelog receiver configuration, checkpoint storage, self-exclusion, and pipeline wiring for log collection. |
| `otel://sampling/{namespace}/{collector}` | Combined head sampling (Instrumentation CRD) and tail sampling (collector tail_sampling processor) configuration and conflict warnings. |
| `otel://spanmetrics/{namespace}/{collector}` | SpanMetrics connector configuration showing dimensions, histogram config, pipeline wiring, and cardinality estimates. |
| `otel://target-allocator/{namespace}/{name}` | Target Allocator configuration and state: allocation strategy, ServiceMonitor/PodMonitor selectors, CRD API version, and Prometheus CR status. |

</details>

## Development

```bash
git clone https://github.com/talkops-ai/talkops-mcp.git
cd talkops-mcp/src/opentelemetry-mcp-server
uv sync --dev
uv run pytest
uv run opentelemetry-mcp-server --help
```

## Get help

- [Documentation](https://talkops.ai/docs/integrations/opentelemetry-mcp-server/overview)
- [Report a bug or request a feature](https://github.com/talkops-ai/talkops-mcp/issues/new?labels=opentelemetry-mcp-server)
- [Join the TalkOps community on Slack](https://talkops.ai/slack/)

## License

Apache 2.0. See [LICENSE](../../LICENSE).
