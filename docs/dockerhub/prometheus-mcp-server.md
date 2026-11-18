# Prometheus MCP Server

Let your AI assistant query and operate Prometheus-compatible monitoring stacks (Prometheus, Thanos, Mimir, Cortex, VictoriaMetrics): run safe PromQL queries, check RED metrics and SLO burn rates, validate rules with `promtool`, cut high-cardinality metrics, and manage scrape configs.

## Quick Reference

- **Maintained by:** [TalkOps](https://talkops.ai) ([GitHub repository](https://github.com/talkops-ai/talkops-mcp/tree/main/src/prometheus-mcp-server))
- **Supported tags:** `latest`, `0.2.1`
- **Architectures:** `linux/amd64`, `linux/arm64`
- **Documentation:** [https://talkops.ai/docs/integrations/prometheus-mcp-server/overview](https://talkops.ai/docs/integrations/prometheus-mcp-server/overview)
- **PyPI alternative:** [`talkops-prometheus-mcp-server`](https://pypi.org/project/talkops-prometheus-mcp-server/)
- **License:** [Apache License 2.0](https://github.com/talkops-ai/talkops-mcp/blob/main/LICENSE)

## What You Get

- **19 MCP tools** (13 read-only) built for AI agents and MCP clients
- **11 MCP resources** under `prom://` for structured context discovery
- **6 Agent Skills** bundled in `/app/skills` ([browse on GitHub](https://github.com/talkops-ai/talkops-mcp/tree/main/src/prometheus-mcp-server/skills))
- **Container ready:** Includes `promtool` inside a minimal non-root image (`linux/amd64`, `linux/arm64`).
- **Safe by default:** examples below start in `--read-only` mode, and destructive actions still require confirmation.

---

## Quick Start (MCP Client over `stdio`)

Use this configuration in **Claude Desktop**, **Cursor**, **Windsurf**, or **VS Code** (`mcp.json` / `claude_desktop_config.json`):

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

Using **Claude Code**? Register it in one command:

```bash
claude mcp add prometheus -e PROMETHEUS_BASE_URL=http://host.docker.internal:9090 -- docker run -i --rm -e MCP_TRANSPORT=stdio -e PROMETHEUS_BASE_URL talkopsai/prometheus-mcp-server:latest --read-only
```

Restart your MCP client and try asking:

- *"What's the error rate and p99 latency for the `checkout` service over the last hour?"*
- *"Are we burning our SLO error budget for `payments`?"*
- *"Which metrics have the highest cardinality, and how do I reduce them?"*

---

## Running Standalone (Streamable HTTP)

By default (`MCP_TRANSPORT=http`), the container starts an MCP Streamable HTTP server on port `8767` so multiple clients can share a single instance:

```bash
docker run --rm -p 8767:8767 \
  -e PROMETHEUS_BASE_URL=http://host.docker.internal:9090 \
  -e MCP_READ_ONLY=true \
  talkopsai/prometheus-mcp-server:latest
```

Point your MCP client at `http://localhost:8767/mcp`:

```json
{
  "mcpServers": {
    "prometheus": {
      "url": "http://localhost:8767/mcp"
    }
  }
}
```

---

## Allowing Changes (Write Mode)

Unlike the other TalkOps MCP servers, Prometheus enables write tools (creating or deleting rule groups, scrape configs, and Kubernetes exporters) unless read-only mode is set. The examples above pass `--read-only` / `MCP_READ_ONLY=true` for safety. Remove that flag when you want your assistant to apply changes.

---

## Environment Variables

| Variable | Container Default | Description |
| :--- | :--- | :--- |
| `PROMETHEUS_BASE_URL` | `http://localhost:9090` | Prometheus URL (use `http://host.docker.internal:9090` for a host instance) |
| `PROMETHEUS_AUTH_HEADER` | none | Optional `Authorization` header, e.g. `Bearer <token>` |
| `PROMETHEUS_TENANT_ID` | none | Tenant ID (`X-Scope-OrgID`) for Mimir, Cortex, or Thanos |
| `PROMETHEUS_BACKENDS` | none | JSON list of multiple backends (overrides single URL) |
| `MCP_READ_ONLY` | `false` | Set to `true` (or pass `--read-only`) to disable all write tools |
| `MCP_ALLOW_WRITE` | `true` | Controls rule, scrape-config, and exporter mutation tools |
| `PROMETHEUS_TOOLSETS` | `all` | Filter tools: `diagnostics`, `query`, `rules`, `scrape`, `exporter`, `readonly` |
| `MCP_TRANSPORT` | `http` | `http` (standalone server) or `stdio` (MCP client subprocess) |
| `MCP_PORT` | `8767` | HTTP listen port inside the container |

---

## Available Tools (19)

| Tool | Access | Description |
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

---

## Bundled Agent Skills (6)

This image also ships step-by-step operational playbooks (`SKILL.md`) under `/app/skills`:

- [`authoring-and-testing-prometheus-rules`](https://github.com/talkops-ai/talkops-mcp/blob/main/src/prometheus-mcp-server/skills/authoring-and-testing-prometheus-rules/SKILL.md)
- [`authoring-promql-and-analyzing-metrics`](https://github.com/talkops-ai/talkops-mcp/blob/main/src/prometheus-mcp-server/skills/authoring-promql-and-analyzing-metrics/SKILL.md)
- [`configuring-prometheus-scraping-and-discovery`](https://github.com/talkops-ai/talkops-mcp/blob/main/src/prometheus-mcp-server/skills/configuring-prometheus-scraping-and-discovery/SKILL.md)
- [`onboarding-exporters-and-instrumentation`](https://github.com/talkops-ai/talkops-mcp/blob/main/src/prometheus-mcp-server/skills/onboarding-exporters-and-instrumentation/SKILL.md)
- [`optimizing-tsdb-cardinality-and-finops`](https://github.com/talkops-ai/talkops-mcp/blob/main/src/prometheus-mcp-server/skills/optimizing-tsdb-cardinality-and-finops/SKILL.md)
- [`triaging-prometheus-incidents-and-slos`](https://github.com/talkops-ai/talkops-mcp/blob/main/src/prometheus-mcp-server/skills/triaging-prometheus-incidents-and-slos/SKILL.md)

To copy the skills onto your workstation for Claude Code or Cursor:

```bash
docker run --rm --entrypoint tar talkopsai/prometheus-mcp-server:latest -C /app/skills -cf - . | tar -xf - -C ~/.claude/skills/
```

---

## Support & Community

- **Source & full docs:** [github.com/talkops-ai/talkops-mcp/tree/main/src/prometheus-mcp-server](https://github.com/talkops-ai/talkops-mcp/tree/main/src/prometheus-mcp-server)
- **Issues & feature requests:** [GitHub Issues](https://github.com/talkops-ai/talkops-mcp/issues/new?labels=prometheus-mcp-server)
- **Community Slack:** [talkops.ai/slack](https://talkops.ai/slack/)
