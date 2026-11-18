<p align="center">
  <img src="https://raw.githubusercontent.com/grafana/loki/main/docs/sources/logo.png" alt="Grafana Loki logo" height="100"/>
</p>

<h1 align="center">Grafana Loki MCP Server &amp; Agent Plugin</h1>

<p align="center">
  Production-ready <strong>Agent Plugin (v1.0.0)</strong> and <strong>FastMCP Execution Server</strong> for <strong>Grafana Loki 3.x</strong> and the <strong>Kubernetes Loki Operator</strong> (<code>loki.grafana.com/v1</code>).
</p>

<p align="center">
  <a href="https://pypi.org/project/talkops-loki-mcp-server/"><img src="https://img.shields.io/pypi/v/talkops-loki-mcp-server.svg?style=flat-square&logo=pypi&logoColor=white&label=PyPI" alt="PyPI"/></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/Python-3.12%2B-3776AB.svg?style=flat-square&logo=python&logoColor=white" alt="Python 3.12+"/></a>
  <a href="https://github.com/talkops-ai/talkops-mcp/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-Apache%202.0-blue.svg?style=flat-square" alt="License"/></a>
  <a href="https://modelcontextprotocol.io/"><img src="https://img.shields.io/badge/MCP-Model%20Context%20Protocol-4A90D9.svg?style=flat-square" alt="MCP"/></a>
  <a href="https://grafana.com/oss/loki/"><img src="https://img.shields.io/badge/Grafana%20Loki-3.x-F46800.svg?style=flat-square&logo=grafana&logoColor=white" alt="Grafana Loki 3.x"/></a>
</p>

Following the TalkOps **Skill & Execution Layer Separation** architecture:
- **Procedural Intelligence (`skills/`)**: 6 modular Agent Skills containing progressive-disclosure SOPs (`SKILL.md` $\le 250$ lines), deep domain references (`references/*.md`), and deterministic local Python CLI helpers (`scripts/*.py`).
- **Execution Plane (`loki_mcp_server/`)**: 18 bounded, type-annotated MCP tools across 7 selectable toolsets + 9 live `loki://` state resources, with read-only defaults (`MCP_ALLOW_WRITE=false`), mandatory `dry_run=True` previews, and interactive `ctx.elicit()` / `confirm=True` mutation gates.

---

Let your AI assistant search and understand your logs in Grafana Loki: discover what's in your logs, write LogQL, summarize errors for a service, compare before and after a release, and follow a request across services.

## What you get

- **18 MCP tools** (14 read-only) that work against your live Grafana Loki setup
- **9 resources** your assistant can read for context, under `loki://`
- **6 Agent Skills**: step-by-step playbooks that teach your assistant how to use the tools well
- **Safe by default**: only read-only tools are loaded until you turn on writes, and changes are previewed or confirmed before they happen

## Quick start

**You'll need:**

- Python 3.12+ and [uv](https://docs.astral.sh/uv/getting-started/installation/), **or** [Docker](https://docs.docker.com/get-docker/)
- A Loki URL
- Optional: Kubernetes access to manage Loki Operator resources

**1. Add the server to your MCP client.** For Claude Desktop, Cursor, Windsurf, and most other clients, add this to your MCP config file:

```json
{
  "mcpServers": {
    "loki": {
      "command": "uvx",
      "args": [
        "--from",
        "talkops-loki-mcp-server",
        "loki-mcp-server"
      ],
      "env": {
        "LOKI_URL": "http://localhost:3100"
      }
    }
  }
}
```

Using Claude Code? Run this instead:

```bash
claude mcp add loki -e LOKI_URL=http://localhost:3100 -- uvx --from talkops-loki-mcp-server loki-mcp-server
```

`uvx` downloads [`talkops-loki-mcp-server`](https://pypi.org/project/talkops-loki-mcp-server/) from PyPI and runs it, so there's nothing else to install. Prefer a normal install? Run `pip install talkops-loki-mcp-server` and use `loki-mcp-server` as the command.

**Prefer Docker?** Pull [`talkopsai/loki-mcp-server`](https://hub.docker.com/r/talkopsai/loki-mcp-server) from Docker Hub—no Python setup needed:

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

**2. Restart your client and try asking:**

- *"What errors is the `checkout` service logging in the last 30 minutes?"*
- *"Did the error rate go up after yesterday's release?"*
- *"Find all logs for trace ID `4bf92f3577b34da6a3ce929d0e0e4736`."*

## Allowing changes

Out of the box the server is read-only. To let your assistant make changes (changing Ruler rule groups, deleting logs, and applying Loki Operator resources), add `"--allow-write"` to `args` (or pass `-e MCP_ALLOW_WRITE=true` to `docker run`). Even then, changes are previewed first and destructive actions ask for confirmation.

## Configuration

Set these as environment variables (the `env` block in your client config, or `-e` with `docker run`) or pass the matching flag.

| Variable | Flag | Default | What it does |
| :--- | :--- | :--- | :--- |
| `LOKI_URL` | `--loki-url` | `http://loki:3100` | Your Loki URL |
| `LOKI_ORG_ID` | `--org-id` | none | Tenant (`X-Scope-OrgID`) for multi-tenant Loki |
| `LOKI_AUTH_TOKEN` | — | none | Bearer token for Loki |
| `MCP_ALLOW_WRITE` | `--allow-write` | `false` | Enable tools that change Loki |
| `MCP_TOOLSETS` | `--toolsets` | `all` | Limit tools: `discovery`, `query`, `analysis`, `diagnostics`, `rules`, `governance`, `operator`, `readonly` |
| `K8S_ENABLED` | `--k8s-enabled` | `false` | Turn on Loki Operator (Kubernetes) features |
| `MCP_TRANSPORT` | `--transport` | `stdio` | `stdio` or `http` |
| `MCP_PORT` | `--port` | `8769` (`8770` in Docker) | Port when using HTTP |

Run `uvx --from talkops-loki-mcp-server loki-mcp-server --help` to see every option.

### Running over HTTP

To share one server between several clients or run it remotely, start it in HTTP mode with Docker or `uvx`:

```bash
# With Docker (starts in HTTP mode by default)
docker run --rm -p 8770:8770 \
  -e LOKI_URL=http://host.docker.internal:3100 \
  talkopsai/loki-mcp-server:latest

# Or with uvx
MCP_TRANSPORT=http MCP_PORT=8770 uvx --from talkops-loki-mcp-server loki-mcp-server
```

Then point your client at `http://localhost:8770/mcp`:

```json
{
  "mcpServers": {
    "loki": {
      "url": "http://localhost:8770/mcp"
    }
  }
}
```

## Agent Skills

Skills live in [`skills/`](skills/). Each one is a `SKILL.md` playbook (plus optional `references/` and offline `scripts/`) that teaches your AI assistant *how* to do a job safely, while the MCP server does the actual work. Tools are the hands, skills are the know-how.

To use them, copy the folders into your assistant's skills directory, for example:

```bash
git clone https://github.com/talkops-ai/talkops-mcp.git
cp -r talkops-mcp/src/loki-mcp-server/skills/* ~/.claude/skills/
```

This folder is also a portable [Agent Plugin](https://agent-plugins.org) (`plugin.json` + `mcp.json` + `skills/`), so plugin-aware clients can load the server and skills together.

| Skill | Use it to |
| :--- | :--- |
| [`discovering-loki-schema-and-log-structure`](skills/discovering-loki-schema-and-log-structure/SKILL.md) | Find out which labels, fields, and log formats you have. |
| [`authoring-logql-and-analyzing-logs`](skills/authoring-logql-and-analyzing-logs/SKILL.md) | Write efficient LogQL and analyze the results. |
| [`triaging-loki-incidents-and-errors`](skills/triaging-loki-incidents-and-errors/SKILL.md) | Summarize errors, compare time periods, and follow trace IDs. |
| [`optimizing-loki-cardinality-and-finops`](skills/optimizing-loki-cardinality-and-finops/SKILL.md) | Find out what's driving log volume and cost. |
| [`authoring-loki-alerting-and-recording-rules`](skills/authoring-loki-alerting-and-recording-rules/SKILL.md) | Write and test log-based alerts and recording rules. |
| [`operating-loki-deployments-and-ingestion`](skills/operating-loki-deployments-and-ingestion/SKILL.md) | Fix ingestion problems, delete logs safely, and size Loki. |

## Reference

<details>
<summary><strong>All 18 tools</strong></summary>

| Tool | Access | What it does |
| :--- | :--- | :--- |
| `loki_analyze_volume` | Read | Attribute ingested log bytes and stream counts by label for FinOps optimization. |
| `loki_apply_operator_cr` | Write | Validate, preview (`dry_run=True`), or Server-Side Apply a Loki Operator CR. |
| `loki_compare_periods` | Read | Compare log volume, error counts, and error signatures across two windows or versions. |
| `loki_correlate_trace_logs` | Read | Find and chronologically order all logs matching a trace_id or request_id. |
| `loki_delete_rule_group` | Write (destructive) | Preview (`dry_run=True`) or delete a Loki Ruler rule group after confirmation. |
| `loki_get_detected_fields` | Read | Discover structured metadata, JSON keys, and logfmt fields with types and cardinalities in Loki 3.x streams. Read-only. |
| `loki_get_diagnostics` | Read | Diagnose Loki backend readiness, build version, and discarded log sample reasons. |
| `loki_get_label_values` | Read | Retrieve values for a specific indexed label in Grafana Loki, optionally scoped by stream selector. Read-only. |
| `loki_get_labels` | Read | List all indexed label names in Grafana Loki over an optional time window. Read-only. |
| `loki_get_log_patterns` | Read | Retrieve recurring structural `<_>` log patterns and line counts from Loki's pattern ingester. Read-only. |
| `loki_get_query_stats` | Read | Estimate streams, chunks, entries, and uncompressed bytes touched by a LogQL selector before execution. Read-only. |
| `loki_get_series` | Read | Return active Loki log stream label sets and per-label cardinality for a stream selector. Read-only. |
| `loki_manage_delete_requests` | Write (destructive) | List, preview (`dry_run=True`), create, or cancel a Loki Compactor log deletion request. |
| `loki_query_a2ui` | Read | Execute a LogQL range query and flatten results into an interactive A2UI log table payload. Read-only. |
| `loki_query_instant` | Read | Evaluate a LogQL metric or stream query at a single point in time. Read-only. |
| `loki_query_range` | Read | Execute a LogQL range query returning log streams or metric time-series matrices with cost guardrails. Read-only. |
| `loki_summarize_service_logs` | Read | Compute a high-signal service log health & error summary in one call. |
| `loki_upsert_rule_group` | Write | Validate, preview (`dry_run=True`), or upsert a Loki Ruler alerting/recording rule group. |

</details>

<details>
<summary><strong>All 9 resources</strong></summary>

| Resource | What it returns |
| :--- | :--- |
| `loki://compactor/delete-requests` | Active and processed Compactor log deletion requests (/loki/api/v1/delete) |
| `loki://config/backends` | Configured Loki backend connection details (URL, tenant, environment) with redacted secrets |
| `loki://config/guardrails` | Current safety thresholds for query limits, time windows, and cardinality |
| `loki://rules/groups` | Active Loki Ruler alerting and recording rule groups across namespaces |
| `loki://schema/labels` | All available label names in Loki |
| `loki://server/capabilities` | Server version, active toolsets, write gate status, query guardrails, and detected Loki 3.x backend capabilities |
| `loki://system/health` | Loki reachability, readiness status, and label count |
| `loki://operator/crs/{namespace}` | Inventory of Kubernetes LokiStack, RulerConfig, AlertingRule, and RecordingRule CRs in a namespace (use '_all' for cluster-wide) |
| `loki://operator/manifests/{kind}/{namespace}/{name}` | Sanitized and secret-redacted Loki Operator CR manifest (LokiStack, RulerConfig, AlertingRule, RecordingRule) |

</details>

## Development

```bash
git clone https://github.com/talkops-ai/talkops-mcp.git
cd talkops-mcp/src/loki-mcp-server
uv sync --dev
uv run pytest
uv run loki-mcp-server --help
```

## Get help

- [Documentation](https://talkops.ai/docs/integrations/loki-mcp-server/overview)
- [Report a bug or request a feature](https://github.com/talkops-ai/talkops-mcp/issues/new?labels=loki-mcp-server)
- [Join the TalkOps community on Slack](https://talkops.ai/slack/)

## License

Apache 2.0. See [LICENSE](../../LICENSE).
