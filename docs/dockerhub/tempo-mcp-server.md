# Grafana Tempo MCP Server

Let your AI assistant investigate distributed traces in Grafana Tempo: run TraceQL searches and metrics queries, pinpoint slow or failing spans, compare baseline vs. regression traces, map service dependencies, and correlate traces with logs and metrics.

## Quick Reference

- **Maintained by:** [TalkOps](https://talkops.ai) ([GitHub repository](https://github.com/talkops-ai/talkops-mcp/tree/main/src/tempo-mcp-server))
- **Supported tags:** `latest`, `0.2.1`
- **Architectures:** `linux/amd64`, `linux/arm64`
- **Documentation:** [https://talkops.ai/docs/integrations/tempo-mcp-server/overview](https://talkops.ai/docs/integrations/tempo-mcp-server/overview)
- **PyPI alternative:** [`talkops-tempo-mcp-server`](https://pypi.org/project/talkops-tempo-mcp-server/)
- **License:** [Apache License 2.0](https://github.com/talkops-ai/talkops-mcp/blob/main/LICENSE)

## What You Get

- **18 MCP tools** (16 read-only) built for AI agents and MCP clients
- **10 MCP resources** under `tempo://` for structured context discovery
- **6 Agent Skills** bundled in `/app/skills` ([browse on GitHub](https://github.com/talkops-ai/talkops-mcp/tree/main/src/tempo-mcp-server/skills))
- **Container ready:** Runs as a minimal non-root image (`linux/amd64`, `linux/arm64`) talking directly to the Tempo HTTP API.
- **Safe by default:** starts in read-only mode until you explicitly set `MCP_ALLOW_WRITE=true`.

---

## Quick Start (MCP Client over `stdio`)

Use this configuration in **Claude Desktop**, **Cursor**, **Windsurf**, or **VS Code** (`mcp.json` / `claude_desktop_config.json`):

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

Using **Claude Code**? Register it in one command:

```bash
claude mcp add tempo -e TEMPO_BASE_URL=http://host.docker.internal:3200 -- docker run -i --rm -e MCP_TRANSPORT=stdio -e TEMPO_BASE_URL talkopsai/tempo-mcp-server:latest
```

Restart your MCP client and try asking:

- *"Show me the slowest traces for `checkout` in the last hour."*
- *"Why did p99 latency for `payments` jump today?"*
- *"Which services does `frontend` call, and which one is failing?"*

---

## Running Standalone (Streamable HTTP)

By default (`MCP_TRANSPORT=http`), the container starts an MCP Streamable HTTP server on port `8768` so multiple clients can share a single instance:

```bash
docker run --rm -p 8768:8768 \
  -e TEMPO_BASE_URL=http://host.docker.internal:3200 \
  talkopsai/tempo-mcp-server:latest
```

Point your MCP client at `http://localhost:8768/mcp`:

```json
{
  "mcpServers": {
    "tempo": {
      "url": "http://localhost:8768/mcp"
    }
  }
}
```

---

## Allowing Changes (Write Mode)

Out of the box, the container runs in **read-only mode** (`MCP_ALLOW_WRITE=false`). To allow mutations (updating per-tenant runtime overrides and applying Tempo Operator CRDs), pass `-e MCP_ALLOW_WRITE=true` to `docker run`. Even with writes enabled, changes support dry-run previews and destructive operations require explicit confirmation.

---

## Environment Variables

| Variable | Container Default | Description |
| :--- | :--- | :--- |
| `TEMPO_BASE_URL` | `http://localhost:3200` | Tempo URL (use `http://host.docker.internal:3200` for a host instance) |
| `TEMPO_DEFAULT_TENANT` | none | Tenant ID (`X-Scope-OrgID`) for multi-tenant Tempo |
| `TEMPO_AUTH_HEADER` | none | Optional `Authorization` header, e.g. `Bearer <token>` |
| `PROMETHEUS_URL` | none | Optional Prometheus URL for service-graph metrics fallback |
| `MCP_ALLOW_WRITE` | `false` | Set to `true` to enable tenant overrides and Tempo Operator writes |
| `MCP_TOOLSETS` | `all` | Filter tools: `search`, `metrics`, `diagnostics`, `overrides`, `operator`, `readonly` |
| `K8S_ENABLED` | `false` | Set to `true` (with mounted `/app/.kube/config`) for Tempo Operator tools |
| `MCP_TRANSPORT` | `http` | `http` (standalone server) or `stdio` (MCP client subprocess) |
| `MCP_PORT` | `8768` | HTTP listen port inside the container |

---

## Available Tools (18)

| Tool | Access | Description |
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

---

## Bundled Agent Skills (6)

This image also ships step-by-step operational playbooks (`SKILL.md`) under `/app/skills`:

- [`authoring-traceql-and-metrics-queries`](https://github.com/talkops-ai/talkops-mcp/blob/main/src/tempo-mcp-server/skills/authoring-traceql-and-metrics-queries/SKILL.md)
- [`diagnosing-tempo-ingestion-and-health`](https://github.com/talkops-ai/talkops-mcp/blob/main/src/tempo-mcp-server/skills/diagnosing-tempo-ingestion-and-health/SKILL.md)
- [`investigating-tempo-latency-regressions`](https://github.com/talkops-ai/talkops-mcp/blob/main/src/tempo-mcp-server/skills/investigating-tempo-latency-regressions/SKILL.md)
- [`mapping-tempo-topology-and-alerts`](https://github.com/talkops-ai/talkops-mcp/blob/main/src/tempo-mcp-server/skills/mapping-tempo-topology-and-alerts/SKILL.md)
- [`operating-tempo-deployments-and-tenants`](https://github.com/talkops-ai/talkops-mcp/blob/main/src/tempo-mcp-server/skills/operating-tempo-deployments-and-tenants/SKILL.md)
- [`triaging-tempo-service-errors`](https://github.com/talkops-ai/talkops-mcp/blob/main/src/tempo-mcp-server/skills/triaging-tempo-service-errors/SKILL.md)

To copy the skills onto your workstation for Claude Code or Cursor:

```bash
docker run --rm --entrypoint tar talkopsai/tempo-mcp-server:latest -C /app/skills -cf - . | tar -xf - -C ~/.claude/skills/
```

---

## Support & Community

- **Source & full docs:** [github.com/talkops-ai/talkops-mcp/tree/main/src/tempo-mcp-server](https://github.com/talkops-ai/talkops-mcp/tree/main/src/tempo-mcp-server)
- **Issues & feature requests:** [GitHub Issues](https://github.com/talkops-ai/talkops-mcp/issues/new?labels=tempo-mcp-server)
- **Community Slack:** [talkops.ai/slack](https://talkops.ai/slack/)
