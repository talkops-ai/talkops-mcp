"""Query workflow guided prompts."""

from mcp.types import PromptMessage, TextContent
from prometheus_mcp_server.prompts.base import BasePrompt


class QueryPrompts(BasePrompt):
    """Query workflow prompts for non-experts."""

    def register(self, mcp_instance) -> None:  # type: ignore[no-untyped-def]

        @mcp_instance.prompt(
            name="prom-query-guided",
            description="Guided workflow for safely querying Prometheus metrics",
        )
        def prom_query_guided(
            backend_id: str,
            metric_name: str = "http_requests_total",
        ) -> list[PromptMessage]:
            prompt_text = f"""# 📊 Prometheus Query Guide

## Context
- **Backend**: {backend_id}
- **Target Metric**: {metric_name}

---

## Step 1: Verify the Service is Emitting Metrics

Before searching for specific metrics, verify that the service is actually up and being scraped by Prometheus.
Read the `prom://topology/services` resource to see a full catalog of active scrape targets and their health status (`targets_up`). If your service isn't listed here or is down, you won't find any metrics for it!

---

## Step 2: Discover & Identify the Correct Metric

Once you confirm the service is emitting metrics, identify the exact metric to use:
1. **Per-Service Metrics**: Read the `prom://topology/services/{{job_name}}/metrics` resource to see only the metrics emitted by that specific service (e.g., `prom://topology/services/traefik-metrics/metrics`). This returns each metric's name, type, and description.
2. **Global Catalog**: If you don't know which service to look at, read the `prom://metadata/catalog` resource for the full list of all metrics across all services.
3. **Ask for Suggestions**: Use the `prom_suggest_promql` tool with a natural language intent (e.g., "error rate for apiserver") to get metric and syntax suggestions.

---

## Step 3: Explore Metric Labels

Once you have identified the exact metric name, verify what dimensions (labels) it supports:
```
Tool: prom_explore_labels(backend_id="{backend_id}", metric_name="{metric_name}")
```
This tool will return all available label names and their top values, so you know exactly how to filter or group your query.

---

## Step 4: Check Metric Type & Validate Syntax

Before querying, ensure you handle the metric type correctly (found via the catalog):
- **Counters** (usually end in `_total`): MUST be wrapped in `rate()` or `increase()`.
- **Gauges**: Can be queried directly.

To check if your PromQL query is structurally correct before executing it:
```
Tool: prom_validate_promql(backend_id="{backend_id}", query="rate({metric_name}[5m])")
```

---

## Step 5: Run a Safe Query

### Instant Query (Current State)
For current values or point-in-time checks, use the instant query tool:
```
Tool: prom_query_instant(backend_id="{backend_id}", query="rate({metric_name}[5m])")
```

### Range Query (Historical Trends)
To analyze trends over time, use the range query tool:
```
Tool: prom_query_range(backend_id="{backend_id}", query="rate({metric_name}[5m])", start=<unix_start>, end=<unix_end>)
```
*Note: The server automatically downsamples range queries to ~200 points per series to keep data manageable.*

---

## Tips for Beginners
- **Filtering**: Use `{{label="value"}}` to filter (e.g., `rate({metric_name}{{status="500"}}[5m])`).
- **Aggregation**: Use `sum()`, `avg()`, `max()` to combine series (e.g., `sum(rate({metric_name}[5m]))`).
- **Grouping**: Add `by (label)` to aggregation functions to group results (e.g., `sum by (status) (rate({metric_name}[5m]))`).
- **Latency (Histograms)**: To calculate average request duration, divide the rate of the `_sum` by the rate of the `_count`. Example: `sum by (service) (rate(duration_seconds_sum[5m])) / sum by (service) (rate(duration_seconds_count[5m]))`.
"""
            return [
                PromptMessage(role="user", content=TextContent(type="text", text=prompt_text))
            ]
