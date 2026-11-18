# Grafana Loki MCP Server

Let your AI assistant explore and analyze logs in Grafana Loki: discover labels and structured metadata, write bounded LogQL queries, summarize service errors, compare log patterns across releases, correlate trace IDs, and spot high-volume log streams.

## Quick Reference

- **Maintained by:** [TalkOps](https://talkops.ai) ([GitHub repository](https://github.com/talkops-ai/talkops-mcp/tree/main/src/loki-mcp-server))
- **Supported tags:** `latest`, `0.2.1`
- **Architectures:** `linux/amd64`, `linux/arm64`
- **Documentation:** [https://talkops.ai/docs/integrations/loki-mcp-server/overview](https://talkops.ai/docs/integrations/loki-mcp-server/overview)
- **PyPI alternative:** [`talkops-loki-mcp-server`](https://pypi.org/project/talkops-loki-mcp-server/)
- **License:** [Apache License 2.0](https://github.com/talkops-ai/talkops-mcp/blob/main/LICENSE)

## What You Get

- **18 MCP tools** (14 read-only) built for AI agents and MCP clients
- **9 MCP resources** under `loki://` for structured context discovery
- **6 Agent Skills** bundled in `/app/skills` ([browse on GitHub](https://github.com/talkops-ai/talkops-mcp/tree/main/src/loki-mcp-server/skills))
- **Container ready:** Runs as a minimal non-root image (`linux/amd64`, `linux/arm64`) with built-in query byte and time-window guardrails.
- **Safe by default:** starts in read-only mode until you explicitly set `MCP_ALLOW_WRITE=true`.

---

## Quick Start (MCP Client over `stdio`)

Use this configuration in **Claude Desktop**, **Cursor**, **Windsurf**, or **VS Code** (`mcp.json` / `claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "loki": {
      "command": "docker",
      "args": [
        "run",
        "-i",
        "--rm",
        "-e",
        "MCP_TRANSPORT=stdio",
        "-e",
        "LOKI_URL",
        "talkopsai/loki-mcp-server:latest"
      ],
      "env": {
        "LOKI_URL": "http://host.docker.internal:3100"
      }
    }
  }
}
```

Using **Claude Code**? Register it in one command:

```bash
claude mcp add loki -e LOKI_URL=http://host.docker.internal:3100 -- docker run -i --rm -e MCP_TRANSPORT=stdio -e LOKI_URL talkopsai/loki-mcp-server:latest
```

Restart your MCP client and try asking:

- *"What errors is the `checkout` service logging in the last 30 minutes?"*
- *"Did the error rate go up after yesterday's release?"*
- *"Find all logs for trace ID `4bf92f3577b34da6a3ce929d0e0e4736`."*

---

## Running Standalone (Streamable HTTP)

By default (`MCP_TRANSPORT=http`), the container starts an MCP Streamable HTTP server on port `8770` so multiple clients can share a single instance:

```bash
docker run --rm -p 8770:8770 \
  -e LOKI_URL=http://host.docker.internal:3100 \
  talkopsai/loki-mcp-server:latest
```

Point your MCP client at `http://localhost:8770/mcp`:

```json
{
  "mcpServers": {
    "loki": {
      "url": "http://localhost:8770/mcp"
    }
  }
}
```

---

## Allowing Changes (Write Mode)

Out of the box, the container runs in **read-only mode** (`MCP_ALLOW_WRITE=false`). To allow mutations (updating Ruler rule groups, submitting log deletion requests, and applying Loki Operator CRDs), pass `-e MCP_ALLOW_WRITE=true` to `docker run`. Even with writes enabled, changes support dry-run previews and destructive operations require explicit confirmation.

---

## Environment Variables

| Variable | Container Default | Description |
| :--- | :--- | :--- |
| `LOKI_URL` | `http://localhost:3100` | Loki base URL (use `http://host.docker.internal:3100` for a host instance) |
| `LOKI_ORG_ID` | none | Tenant ID (`X-Scope-OrgID`) for multi-tenant Loki |
| `LOKI_AUTH_TOKEN` | none | Bearer token for Loki authentication |
| `MCP_ALLOW_WRITE` | `false` | Set to `true` to enable rule mutations, log deletion, and Operator writes |
| `MCP_TOOLSETS` | `all` | Filter tools: `discovery`, `query`, `analysis`, `diagnostics`, `rules`, `governance`, `operator`, `readonly` |
| `K8S_ENABLED` | `false` | Set to `true` (with mounted `/app/.kube/config`) for Loki Operator tools |
| `MCP_TRANSPORT` | `http` | `http` (standalone server) or `stdio` (MCP client subprocess) |
| `MCP_PORT` | `8770` | HTTP listen port inside the container |

---

## Available Tools (18)

| Tool | Access | Description |
| :--- | :--- | :--- |
| `loki_analyze_volume` | Read | Attribute ingested log bytes and stream counts by label for FinOps optimization. |
| `loki_apply_operator_cr` | Write | Validate, preview (`dry_run=True`), or Server-Side Apply a Loki Operator CR. |
| `loki_compare_periods` | Read | Compare log volume, error counts, and error signatures across two windows or versions. |
| `loki_correlate_trace_logs` | Read | Find and chronologically order all logs matching a trace_id or request_id. |
| `loki_delete_rule_group` | Write (destructive) | Preview (`dry_run=True`) or delete a Loki Ruler rule group after confirmation. |
| `loki_get_detected_fields` | Read | Discover structured metadata, JSON keys, and logfmt fields with types and cardinalities in Loki 3.x streams. |
| `loki_get_diagnostics` | Read | Diagnose Loki backend readiness, build version, and discarded log sample reasons. |
| `loki_get_label_values` | Read | Retrieve values for a specific indexed label in Grafana Loki, optionally scoped by stream selector. |
| `loki_get_labels` | Read | List all indexed label names in Grafana Loki over an optional time window. |
| `loki_get_log_patterns` | Read | Retrieve recurring structural `<_>` log patterns and line counts from Loki's pattern ingester. |
| `loki_get_query_stats` | Read | Estimate streams, chunks, entries, and uncompressed bytes touched by a LogQL selector before execution. |
| `loki_get_series` | Read | Return active Loki log stream label sets and per-label cardinality for a stream selector. |
| `loki_manage_delete_requests` | Write (destructive) | List, preview (`dry_run=True`), create, or cancel a Loki Compactor log deletion request. |
| `loki_query_a2ui` | Read | Execute a LogQL range query and flatten results into an interactive A2UI log table payload. |
| `loki_query_instant` | Read | Evaluate a LogQL metric or stream query at a single point in time. |
| `loki_query_range` | Read | Execute a LogQL range query returning log streams or metric time-series matrices with cost guardrails. |
| `loki_summarize_service_logs` | Read | Compute a high-signal service log health & error summary in one call. |
| `loki_upsert_rule_group` | Write | Validate, preview (`dry_run=True`), or upsert a Loki Ruler alerting/recording rule group. |

---

## Bundled Agent Skills (6)

This image also ships step-by-step operational playbooks (`SKILL.md`) under `/app/skills`:

- [`authoring-logql-and-analyzing-logs`](https://github.com/talkops-ai/talkops-mcp/blob/main/src/loki-mcp-server/skills/authoring-logql-and-analyzing-logs/SKILL.md)
- [`authoring-loki-alerting-and-recording-rules`](https://github.com/talkops-ai/talkops-mcp/blob/main/src/loki-mcp-server/skills/authoring-loki-alerting-and-recording-rules/SKILL.md)
- [`discovering-loki-schema-and-log-structure`](https://github.com/talkops-ai/talkops-mcp/blob/main/src/loki-mcp-server/skills/discovering-loki-schema-and-log-structure/SKILL.md)
- [`operating-loki-deployments-and-ingestion`](https://github.com/talkops-ai/talkops-mcp/blob/main/src/loki-mcp-server/skills/operating-loki-deployments-and-ingestion/SKILL.md)
- [`optimizing-loki-cardinality-and-finops`](https://github.com/talkops-ai/talkops-mcp/blob/main/src/loki-mcp-server/skills/optimizing-loki-cardinality-and-finops/SKILL.md)
- [`triaging-loki-incidents-and-errors`](https://github.com/talkops-ai/talkops-mcp/blob/main/src/loki-mcp-server/skills/triaging-loki-incidents-and-errors/SKILL.md)

To copy the skills onto your workstation for Claude Code or Cursor:

```bash
docker run --rm --entrypoint tar talkopsai/loki-mcp-server:latest -C /app/skills -cf - . | tar -xf - -C ~/.claude/skills/
```

---

## Support & Community

- **Source & full docs:** [github.com/talkops-ai/talkops-mcp/tree/main/src/loki-mcp-server](https://github.com/talkops-ai/talkops-mcp/tree/main/src/loki-mcp-server)
- **Issues & feature requests:** [GitHub Issues](https://github.com/talkops-ai/talkops-mcp/issues/new?labels=loki-mcp-server)
- **Community Slack:** [talkops.ai/slack](https://talkops.ai/slack/)
