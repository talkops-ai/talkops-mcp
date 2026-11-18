<p align="center">
  <img src="https://raw.githubusercontent.com/cncf/artwork/main/projects/prometheus/icon/color/prometheus-icon-color.svg" alt="Prometheus logo" height="100"/>
</p>

<h1 align="center">Prometheus MCP Server &amp; Agent Plugin</h1>

<p align="center">
  An Agent Plugins v1.0.0 compliant Prometheus observability suite combining <strong>6 Progressive-Disclosure Agent Skills</strong> (methodology, runbooks, and zero-network local CLI generators) with a focused <strong>19-Tool / 11-Resource MCP Execution Server</strong> for Prometheus 3.0+, Thanos, Mimir, Cortex, and VictoriaMetrics.
</p>

<p align="center">
  <a href="https://pypi.org/project/talkops-prometheus-mcp-server/"><img src="https://img.shields.io/pypi/v/talkops-prometheus-mcp-server.svg?style=flat-square&logo=pypi&logoColor=white&label=PyPI" alt="PyPI"/></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/Python-3.12%2B-3776AB.svg?style=flat-square&logo=python&logoColor=white" alt="Python 3.12+"/></a>
  <a href="https://github.com/talkops-ai/talkops-mcp/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-Apache%202.0-blue.svg?style=flat-square" alt="License"/></a>
  <a href="https://modelcontextprotocol.io/"><img src="https://img.shields.io/badge/MCP-Model%20Context%20Protocol-4A90D9.svg?style=flat-square" alt="MCP"/></a>
  <a href="https://prometheus.io/"><img src="https://img.shields.io/badge/Prometheus-3.0%2B-E6522C.svg?style=flat-square&logo=prometheus&logoColor=white" alt="Prometheus 3.0+"/></a>
</p>

---

Let your AI assistant work with Prometheus: write and run PromQL, check service health and SLOs, test alert rules, find expensive metrics, and set up scraping and exporters. Works with Prometheus, Thanos, Mimir, Cortex, and VictoriaMetrics.

## What you get

- **19 MCP tools** (13 read-only) that work against your live Prometheus setup
- **11 resources** your assistant can read for context, under `prom://`
- **6 Agent Skills**: step-by-step playbooks that teach your assistant how to use the tools well
- **Safe by default**: write tools are on unless you pass `--read-only` (the examples below do), and destructive actions still ask for confirmation

## Quick start

**You'll need:**

- Python 3.12+ and [uv](https://docs.astral.sh/uv/getting-started/installation/), **or** [Docker](https://docs.docker.com/get-docker/)
- A Prometheus-compatible URL
- Optional: Kubernetes access for scrape configs and exporters

**1. Add the server to your MCP client.** For Claude Desktop, Cursor, Windsurf, and most other clients, add this to your MCP config file:

```json
{
  "mcpServers": {
    "prometheus": {
      "command": "uvx",
      "args": [
        "--from",
        "talkops-prometheus-mcp-server",
        "prometheus-mcp-server",
        "--read-only"
      ],
      "env": {
        "PROMETHEUS_BASE_URL": "http://localhost:9090"
      }
    }
  }
}
```

Using Claude Code? Run this instead:

```bash
claude mcp add prometheus -e PROMETHEUS_BASE_URL=http://localhost:9090 -- uvx --from talkops-prometheus-mcp-server prometheus-mcp-server --read-only
```

`uvx` downloads [`talkops-prometheus-mcp-server`](https://pypi.org/project/talkops-prometheus-mcp-server/) from PyPI and runs it, so there's nothing else to install. Prefer a normal install? Run `pip install talkops-prometheus-mcp-server` and use `prometheus-mcp-server` as the command.

**Prefer Docker?** Pull [`talkopsai/prometheus-mcp-server`](https://hub.docker.com/r/talkopsai/prometheus-mcp-server) from Docker Hub—no Python setup needed:

```json
{
  "mcpServers": {
    "prometheus": {
      "command": "docker",
      "args": [
        "run",
        "-i",
        "--rm",
        "-e",
        "MCP_TRANSPORT=stdio",
        "-e",
        "PROMETHEUS_BASE_URL",
        "talkopsai/prometheus-mcp-server:latest",
        "--read-only"
      ],
      "env": {
        "PROMETHEUS_BASE_URL": "http://host.docker.internal:9090"
      }
    }
  }
}
```

**2. Restart your client and try asking:**

- *"What's the error rate and p99 latency for the `checkout` service over the last hour?"*
- *"Are we burning our SLO error budget for `payments`?"*
- *"Which metrics have the highest cardinality, and how do I reduce them?"*

## Allowing changes

Unlike the other TalkOps servers, Prometheus starts **with write tools enabled** (creating and deleting rule groups, scrape configs, and exporters). That's why the examples above pass `--read-only`. Remove it, or set `MCP_ALLOW_WRITE=true`, when you want your assistant to make changes.

## Configuration

Set these as environment variables (the `env` block in your client config, or `-e` with `docker run`) or pass the matching flag.

| Variable | Flag | Default | What it does |
| :--- | :--- | :--- | :--- |
| `PROMETHEUS_BASE_URL` | `--prometheus-url` | `http://localhost:9090` | Your Prometheus URL |
| `PROMETHEUS_AUTH_HEADER` | — | none | Authorization header, e.g. `Bearer <token>` |
| `PROMETHEUS_TENANT_ID` | `--tenant-id` | none | Tenant (`X-Scope-OrgID`) for Mimir, Cortex, or Thanos |
| `PROMETHEUS_BACKENDS` | — | none | JSON list of several backends (replaces the single URL) |
| `MCP_ALLOW_WRITE` | `--allow-write` | `true` | Enable tools that change rules, scrape configs, and exporters |
| `MCP_READ_ONLY` | `--read-only` | `false` | Force read-only mode |
| `PROMETHEUS_TOOLSETS` | `--toolsets` | `all` | Limit tools: `diagnostics`, `query`, `rules`, `scrape`, `exporter`, `readonly` |
| `MCP_TRANSPORT` | `--transport` | `stdio` | `stdio` or `http` |
| `MCP_PORT` | `--port` | `8767` | Port when using HTTP |

Run `uvx --from talkops-prometheus-mcp-server prometheus-mcp-server --help` to see every option.

### Running over HTTP

To share one server between several clients or run it remotely, start it in HTTP mode with Docker or `uvx`:

```bash
# With Docker (starts in HTTP mode by default)
docker run --rm -p 8767:8767 \
  -e PROMETHEUS_BASE_URL=http://host.docker.internal:9090 \
  -e MCP_READ_ONLY=true \
  talkopsai/prometheus-mcp-server:latest

# Or with uvx
MCP_TRANSPORT=http MCP_PORT=8767 uvx --from talkops-prometheus-mcp-server prometheus-mcp-server
```

Then point your client at `http://localhost:8767/mcp`:

```json
{
  "mcpServers": {
    "prometheus": {
      "url": "http://localhost:8767/mcp"
    }
  }
}
```

## Agent Skills

Skills live in [`skills/`](skills/). Each one is a `SKILL.md` playbook (plus optional `references/` and offline `scripts/`) that teaches your AI assistant *how* to do a job safely, while the MCP server does the actual work. Tools are the hands, skills are the know-how.

To use them, copy the folders into your assistant's skills directory, for example:

```bash
git clone https://github.com/talkops-ai/talkops-mcp.git
cp -r talkops-mcp/src/prometheus-mcp-server/skills/* ~/.claude/skills/
```

This folder is also a portable [Agent Plugin](https://agent-plugins.org) (`plugin.json` + `mcp.json` + `skills/`), so plugin-aware clients can load the server and skills together.

| Skill | Use it to |
| :--- | :--- |
| [`triaging-prometheus-incidents-and-slos`](skills/triaging-prometheus-incidents-and-slos/SKILL.md) | Triage incidents with RED/USE checks and SLO burn rates. |
| [`authoring-promql-and-analyzing-metrics`](skills/authoring-promql-and-analyzing-metrics/SKILL.md) | Find the right metrics and write correct PromQL. |
| [`authoring-and-testing-prometheus-rules`](skills/authoring-and-testing-prometheus-rules/SKILL.md) | Write, test, and safely deploy alerting and recording rules. |
| [`optimizing-tsdb-cardinality-and-finops`](skills/optimizing-tsdb-cardinality-and-finops/SKILL.md) | Find costly, high-cardinality metrics and cut them down. |
| [`configuring-prometheus-scraping-and-discovery`](skills/configuring-prometheus-scraping-and-discovery/SKILL.md) | Set up and fix ServiceMonitors, PodMonitors, Probes, and scrape configs. |
| [`onboarding-exporters-and-instrumentation`](skills/onboarding-exporters-and-instrumentation/SKILL.md) | Pick, deploy, and verify exporters, and instrument your apps. |

## Reference

<details>
<summary><strong>All 19 tools</strong></summary>

| Tool | Access | What it does |
| :--- | :--- | :--- |
| `prom_analyze_cardinality` | Read | Analyze TSDB series cardinality, label value fan-out, and rule usage shares. |
| `prom_analyze_service_red` | Read | Compute RED golden signals (Request Rate, Error Ratio, p50/p95/p99 Duration) supporting classic and Prometheus 3.0 Native Histograms plus trace exemplars. |
| `prom_apply_scrape_config` | Write | Create or update a `ServiceMonitor`, `PodMonitor`, `Probe`, `ScrapeConfig` CRD, or `file_sd` target group. |
| `prom_compare_periods` | Read | Compare a PromQL expression between a current window and a time-shifted baseline window. |
| `prom_delete_rule_group` | Write (destructive) | Delete a rule group from its owning `PrometheusRule` CRD, local YAML file, or HTTP Ruler namespace without clobbering sibling rule groups. |
| `prom_delete_scrape_config` | Write (destructive) | Delete a Kubernetes scrape CRD (`ServiceMonitor`, `PodMonitor`, `Probe`, `ScrapeConfig`) or `file_sd` file. |
| `prom_evaluate_slo_burn` | Read | Evaluate Google SRE multi-window multi-burn-rate error budget consumption (1h/5m, 6h/30m, 24h/2h, 72h/6h) in one call. |
| `prom_explore_metrics` | Read | Discover metric names, types, HELP text, per-job target metrics, label values, or matching series selectors. |
| `prom_get_diagnostics` | Read | Collect unified backend health, runtime info, WAL replay, TSDB stats, and target health. |
| `prom_get_firing_alerts` | Read | Inspect Prometheus's native rule evaluation state (`/api/v1/alerts`) and `ALERTS_FOR_STATE` flapping history. |
| `prom_install_exporter` | Write | Deploy a Prometheus exporter (`Deployment`/`DaemonSet`, `Service`, and `ServiceMonitor`) to Kubernetes. |
| `prom_query_exemplars` | Read | Fetch OpenTelemetry/Tempo trace exemplars (`trace_id`, `span_id`) attached to metric samples. |
| `prom_query_instant` | Read | Execute a point-in-time PromQL instant query (or `validate_only=True` preflight check) with semantic counter guardrails. |
| `prom_query_range` | Read | Execute a PromQL range query with auto-step sizing, per-series stats, and optional A2UI chart. |
| `prom_simulate_rule_firing` | Read | Simulate whether an alerting rule would fire (`pending` -> `firing` over `for`) on historical or synthetic data. |
| `prom_uninstall_exporter` | Write (destructive) | Remove a deployed Prometheus exporter (`Deployment`/`DaemonSet`, `Service`, and `ServiceMonitor`) from Kubernetes. |
| `prom_upsert_rule_group` | Write | Create or update a Prometheus rule group via `k8s_crd`, `http_ruler`, `local_file`, or `yaml_only` with non-destructive multi-group merge. |
| `prom_validate_rules` | Read | Validate a rule group via `promtool check rules`, structural hygiene checks, and optional `promtool test rules`. |
| `prom_verify_metrics_endpoint` | Read | Verify a `/metrics` HTTP endpoint and/or poll Prometheus until `up{job=...} == 1.0`. |

</details>

<details>
<summary><strong>All 11 resources</strong></summary>

| Resource | What it returns |
| :--- | :--- |
| `prom://audit/recent` | Recent MCP write and dry-run operations with outcomes and timestamps |
| `prom://config/runtime` | Sanitized runtime configuration: global settings, remote-write targets, and TSDB stats |
| `prom://kubernetes/scrape-crds` | Inventory of deployed Prometheus Operator CRDs across the cluster: ServiceMonitor, PodMonitor, Probe, ScrapeConfig, and PrometheusRule |
| `prom://metadata/catalog` | Catalog of metric names with type and HELP text, used to prevent metric name hallucination |
| `prom://rules/groups` | Snapshot of all alerting and recording rule groups across backends |
| `prom://system/backends` | List all known Prometheus-compatible backends and their health status |
| `prom://topology/targets` | Scrape target health summary grouped by job/service plus failing target endpoints |
| `prom://tsdb/cardinality` | TSDB cardinality overview and top-N high-cardinality metrics for FinOps |
| `prom://kubernetes/manifests/{kind}/{namespace}/{name}` | Live redacted Kubernetes CRD manifest for a specific ServiceMonitor, PodMonitor, Probe, ScrapeConfig, or PrometheusRule |
| `prom://rules/{backend_id}/groups/{group_name}` | Full definition and evaluation health of a specific rule group by backend_id and group_name |
| `prom://system/backends/{backend_id}` | Get detailed backend capabilities, runtime info, and health |

</details>

## Development

```bash
git clone https://github.com/talkops-ai/talkops-mcp.git
cd talkops-mcp/src/prometheus-mcp-server
uv sync --dev
uv run pytest
uv run prometheus-mcp-server --help
```

## Get help

- [Documentation](https://talkops.ai/docs/integrations/prometheus-mcp-server/overview)
- [Report a bug or request a feature](https://github.com/talkops-ai/talkops-mcp/issues/new?labels=prometheus-mcp-server)
- [Join the TalkOps community on Slack](https://talkops.ai/slack/)

## License

Apache 2.0. See [LICENSE](../../LICENSE).
