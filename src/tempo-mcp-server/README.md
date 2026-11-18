<p align="center">
  <img src="https://raw.githubusercontent.com/grafana/tempo/main/cmd/tempo/app/static/tempo-icon.png" alt="Grafana Tempo logo" height="100"/>
</p>

<h1 align="center">Grafana Tempo MCP Server &amp; Agent Plugin</h1>

<p align="center">
  An <strong>Agent Plugins v1.0.0</strong> package combining <strong>6 Progressive-Disclosure Agent Skills</strong> (<code>skills/</code>) with an <strong>18-Tool / 10-Resource FastMCP Execution Server</strong> for <strong>Grafana Tempo 2.x/3.x</strong> and the <strong>Tempo Operator (<code>tempo.grafana.com/v1alpha1</code>)</strong>.
</p>

<p align="center">
  <a href="https://pypi.org/project/talkops-tempo-mcp-server/"><img src="https://img.shields.io/pypi/v/talkops-tempo-mcp-server.svg?style=flat-square&logo=pypi&logoColor=white&label=PyPI" alt="PyPI"/></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/Python-3.12%2B-3776AB.svg?style=flat-square&logo=python&logoColor=white" alt="Python 3.12+"/></a>
  <a href="https://github.com/talkops-ai/talkops-mcp/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-Apache%202.0-blue.svg?style=flat-square" alt="License"/></a>
  <a href="https://modelcontextprotocol.io/"><img src="https://img.shields.io/badge/MCP-Model%20Context%20Protocol-4A90D9.svg?style=flat-square" alt="MCP"/></a>
  <a href="https://grafana.com/oss/tempo/"><img src="https://img.shields.io/badge/Grafana%20Tempo-2.x%20%2F%203.x-F46800.svg?style=flat-square&logo=grafana&logoColor=white" alt="Grafana Tempo 2.x / 3.x"/></a>
</p>

---

Let your AI assistant explore distributed traces in Grafana Tempo: search with TraceQL, find slow or failing spans, compare traces, map service dependencies, and jump from a log line or metric to the trace behind it.

## What you get

- **18 MCP tools** (16 read-only) that work against your live Grafana Tempo setup
- **10 resources** your assistant can read for context, under `tempo://`
- **6 Agent Skills**: step-by-step playbooks that teach your assistant how to use the tools well
- **Safe by default**: only read-only tools are loaded until you turn on writes, and changes are previewed or confirmed before they happen

## Quick start

**You'll need:**

- Python 3.12+ and [uv](https://docs.astral.sh/uv/getting-started/installation/), **or** [Docker](https://docs.docker.com/get-docker/)
- A Tempo URL
- Optional: Prometheus (for service graphs) and Kubernetes access (for the Tempo Operator)

**1. Add the server to your MCP client.** For Claude Desktop, Cursor, Windsurf, and most other clients, add this to your MCP config file:

```json
{
  "mcpServers": {
    "tempo": {
      "command": "uvx",
      "args": [
        "--from",
        "talkops-tempo-mcp-server",
        "tempo-mcp-server"
      ],
      "env": {
        "TEMPO_URL": "http://localhost:3200"
      }
    }
  }
}
```

Using Claude Code? Run this instead:

```bash
claude mcp add tempo -e TEMPO_URL=http://localhost:3200 -- uvx --from talkops-tempo-mcp-server tempo-mcp-server
```

`uvx` downloads [`talkops-tempo-mcp-server`](https://pypi.org/project/talkops-tempo-mcp-server/) from PyPI and runs it, so there's nothing else to install. Prefer a normal install? Run `pip install talkops-tempo-mcp-server` and use `tempo-mcp-server` as the command.

**Prefer Docker?** Pull [`talkopsai/tempo-mcp-server`](https://hub.docker.com/r/talkopsai/tempo-mcp-server) from Docker Hub—no Python setup needed:

```json
{
  "mcpServers": {
    "tempo": {
      "command": "docker",
      "args": [
        "run",
        "-i",
        "--rm",
        "-e",
        "MCP_TRANSPORT=stdio",
        "-e",
        "TEMPO_BASE_URL",
        "talkopsai/tempo-mcp-server:latest"
      ],
      "env": {
        "TEMPO_BASE_URL": "http://host.docker.internal:3200"
      }
    }
  }
}
```

**2. Restart your client and try asking:**

- *"Show me the slowest traces for `checkout` in the last hour."*
- *"Why did p99 latency for `payments` jump today?"*
- *"Which services does `frontend` call, and which one is failing?"*

## Allowing changes

Out of the box the server is read-only. To let your assistant make changes (changing per-tenant overrides and applying Tempo Operator resources), add `"--allow-write"` to `args` (or pass `-e MCP_ALLOW_WRITE=true` to `docker run`). Even then, changes are previewed first and destructive actions ask for confirmation.

## Configuration

Set these as environment variables (the `env` block in your client config, or `-e` with `docker run`) or pass the matching flag.

| Variable | Flag | Default | What it does |
| :--- | :--- | :--- | :--- |
| `TEMPO_URL` / `TEMPO_BASE_URL` | `--tempo-url` | `http://localhost:3200` | Your Tempo URL |
| `TEMPO_DEFAULT_TENANT` | `--tenant` | none | Tenant (`X-Scope-OrgID`) for multi-tenant Tempo |
| `TEMPO_AUTH_HEADER` | — | none | Authorization header, e.g. `Bearer <token>` |
| `PROMETHEUS_URL` | — | none | Prometheus for service-graph metrics (optional) |
| `MCP_ALLOW_WRITE` | `--allow-write` | `false` | Enable tools that change Tempo |
| `MCP_TOOLSETS` | `--toolsets` | `all` | Limit tools: `search`, `metrics`, `diagnostics`, `overrides`, `operator`, `readonly` |
| `K8S_ENABLED` | `--k8s-enabled` | `false` | Turn on Tempo Operator (Kubernetes) features |
| `MCP_TRANSPORT` | `--transport` | `stdio` | `stdio` or `http` |
| `MCP_PORT` | — | `8768` | Port when using HTTP |

Run `uvx --from talkops-tempo-mcp-server tempo-mcp-server --help` to see every option.

### Running over HTTP

To share one server between several clients or run it remotely, start it in HTTP mode with Docker or `uvx`:

```bash
# With Docker (starts in HTTP mode by default)
docker run --rm -p 8768:8768 \
  -e TEMPO_BASE_URL=http://host.docker.internal:3200 \
  talkopsai/tempo-mcp-server:latest

# Or with uvx
MCP_TRANSPORT=http MCP_PORT=8768 uvx --from talkops-tempo-mcp-server tempo-mcp-server
```

Then point your client at `http://localhost:8768/mcp`:

```json
{
  "mcpServers": {
    "tempo": {
      "url": "http://localhost:8768/mcp"
    }
  }
}
```

## Agent Skills

Skills live in [`skills/`](skills/). Each one is a `SKILL.md` playbook (plus optional `references/` and offline `scripts/`) that teaches your AI assistant *how* to do a job safely, while the MCP server does the actual work. Tools are the hands, skills are the know-how.

To use them, copy the folders into your assistant's skills directory, for example:

```bash
git clone https://github.com/talkops-ai/talkops-mcp.git
cp -r talkops-mcp/src/tempo-mcp-server/skills/* ~/.claude/skills/
```

This folder is also a portable [Agent Plugin](https://agent-plugins.org) (`plugin.json` + `mcp.json` + `skills/`), so plugin-aware clients can load the server and skills together.

| Skill | Use it to |
| :--- | :--- |
| [`authoring-traceql-and-metrics-queries`](skills/authoring-traceql-and-metrics-queries/SKILL.md) | Write correct TraceQL searches and TraceQL metrics queries. |
| [`triaging-tempo-service-errors`](skills/triaging-tempo-service-errors/SKILL.md) | Triage failing services and jump between metrics, logs, and traces. |
| [`investigating-tempo-latency-regressions`](skills/investigating-tempo-latency-regressions/SKILL.md) | Find the spans behind a latency regression. |
| [`diagnosing-tempo-ingestion-and-health`](skills/diagnosing-tempo-ingestion-and-health/SKILL.md) | Find out why traces are missing and check Tempo's health. |
| [`mapping-tempo-topology-and-alerts`](skills/mapping-tempo-topology-and-alerts/SKILL.md) | Map service dependencies and generate span-metrics alerts. |
| [`operating-tempo-deployments-and-tenants`](skills/operating-tempo-deployments-and-tenants/SKILL.md) | Manage tenant overrides and Tempo Operator resources. |

## Reference

<details>
<summary><strong>All 18 tools</strong></summary>

| Tool | Access | What it does |
| :--- | :--- | :--- |
| `tempo_analyze_service_red` | Read | Compute factual Rate, Error rate, and P50/P95/P99 latency metrics, optional baseline deltas, and exemplar IDs. |
| `tempo_apply_operator_cr` | Write (destructive) | Validate and apply a TempoStack or TempoMonolithic custom resource manifest. |
| `tempo_compare_span_cohorts` | Read | Execute a TraceQL compare() instant query to rank attribute values differentiating selection vs baseline spans. |
| `tempo_compare_traces` | Read | Compute a 5-axis structural, span-count, timing, error, and attribute diff between two traces. |
| `tempo_find_related_traces` | Read | Find traces correlated with a seed trace by error origin, endpoint, time, or cascade. |
| `tempo_get_attribute_names` | Read | Discover trace attribute names grouped by scope from a Tempo backend. |
| `tempo_get_attribute_values` | Read | Retrieve distinct values for a trace attribute on a Tempo backend. |
| `tempo_get_diagnostics` | Read | Collect factual health, version (2.x/3.x), ring, discarded-span, config, and Operator CR observations. |
| `tempo_get_exemplar_traces` | Read | Extract exemplar trace IDs from a TraceQL metrics range query. |
| `tempo_get_service_dependencies` | Read | Discover service nodes and client->server call edges via Prometheus service-graphs, TraceQL metrics, or trace DAG sampling. |
| `tempo_get_trace` | Read | Retrieve a trace by ID with optional span-count slicing and time bounds. |
| `tempo_get_trace_from_log` | Read | Extract a trace ID (W3C traceparent, JSON, logfmt, or hex32) from text and summarize the trace. |
| `tempo_patch_tenant_overrides` | Write (destructive) | Preview or apply an RFC 7386 JSON merge patch to Tempo's /api/overrides endpoint for a tenant. |
| `tempo_query_a2ui` | Read | Retrieve a trace structured and DAG-pruned for A2UI trace timeline rendering. |
| `tempo_summarize_trace` | Read | Extract factual summary of a trace: critical path, self-time hotspots, errors, and K8s context. |
| `tempo_traceql_metrics_instant` | Read | Execute a point-in-time TraceQL metrics instant query (vector format). |
| `tempo_traceql_metrics_range` | Read | Execute a TraceQL metrics range query returning time-series points and per-series stats. |
| `tempo_traceql_search` | Read | Search traces using raw TraceQL and/or structured SearchFilters. |

</details>

<details>
<summary><strong>All 10 resources</strong></summary>

| Resource | What it returns |
| :--- | :--- |
| `tempo://deployment/overview` | Deployment topology: configured backends and Kubernetes-discovered Tempo installs |
| `tempo://server/capabilities` | Server capabilities, write gate status, active toolsets, query guardrails, and detected backend features |
| `tempo://system/backends` | All configured Tempo backends with live health status |
| `tempo://operator/crd-schema/{kind}` | Installed CRD OpenAPI v3 spec schema for TempoStack or TempoMonolithic |
| `tempo://operator/crs/{namespace}` | Inventory of TempoStack and TempoMonolithic CRs in a namespace (use '_all' for cluster-wide) |
| `tempo://operator/manifests/{kind}/{namespace}/{name}` | Sanitized and secret-redacted TempoStack or TempoMonolithic manifest |
| `tempo://overrides/{backend_id}/{tenant}` | Merged user-configurable overrides and current ETag for a Tempo tenant |
| `tempo://schema/{backend_id}/attributes` | Live trace attribute presence and detected OTel Semantic Conventions for a backend |
| `tempo://system/backends/{backend_id}` | Detailed live profile for a specific Tempo backend |
| `tempo://traces/{backend_id}/{trace_id}` | Compact trace summary and bounded spans for a trace ID |

</details>

## Development

```bash
git clone https://github.com/talkops-ai/talkops-mcp.git
cd talkops-mcp/src/tempo-mcp-server
uv sync --dev
uv run pytest
uv run tempo-mcp-server --help
```

## Get help

- [Documentation](https://talkops.ai/docs/integrations/tempo-mcp-server/overview)
- [Report a bug or request a feature](https://github.com/talkops-ai/talkops-mcp/issues/new?labels=tempo-mcp-server)
- [Join the TalkOps community on Slack](https://talkops.ai/slack/)

## License

Apache 2.0. See [LICENSE](../../LICENSE).
