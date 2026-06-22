"""Query workflow prompts for Tempo."""

from mcp.types import PromptMessage, TextContent
from tempo_mcp_server.prompts.base import BasePrompt


class QueryPrompts(BasePrompt):
    """Query construction and metrics-first triage prompts."""

    def register(self, mcp_instance) -> None:  # type: ignore[no-untyped-def]

        @mcp_instance.prompt(
            name="tempo-traceql-builder",
            description="Interactive TraceQL query construction from natural language intent.",
        )
        def tempo_traceql_builder(
            backend_id: str,
            intent: str,
        ) -> list[PromptMessage]:
            prompt_text = f"""# 🔧 TraceQL Builder

## User Intent
"{intent}"

## Workflow

1. **Understand** — Parse the user's intent into:
   - Target service(s)
   - Desired conditions (errors, latency, specific endpoints)
   - Time range

2. **Discover** — Check available attributes:
   ```
   Tool: tempo_get_attribute_names(backend_id="{backend_id}", scope="span", since="1h")
   ```

3. **Construct** — Build the TraceQL query using:
   ```
   Resource: tempo://reference/traceql
   ```

4. **Execute** — Run the query:
   ```
   Tool: tempo_traceql_search(backend_id="{backend_id}", query="<constructed_query>", since="1h")
   ```

5. **Refine** — If results are empty or too broad, adjust filters.

## Helpful References
- `tempo://examples/common-queries` — Common query patterns
- `tempo://reference/k8s-attributes` — K8s attribute names
"""
            return [
                PromptMessage(role="user", content=TextContent(type="text", text=prompt_text))
            ]

        @mcp_instance.prompt(
            name="tempo-metrics-first-triage",
            description="RED metrics → search → summarize triage workflow.",
        )
        def tempo_metrics_first_triage(
            backend_id: str,
            service: str,
        ) -> list[PromptMessage]:
            prompt_text = f"""# 📊 Metrics-First Triage

## RED (Rate, Errors, Duration) Analysis for {service}

### Step 1: Rate
```
Tool: tempo_traceql_metrics_range(
    backend_id="{backend_id}",
    query='{{ resource.service.name = "{service}" }} | rate()',
    since="6h"
)
```

### Step 2: Errors
```
Tool: tempo_traceql_metrics_range(
    backend_id="{backend_id}",
    query='{{ resource.service.name = "{service}" && status = error }} | rate()',
    since="6h"
)
```

### Step 3: Duration (P99)
```
Tool: tempo_traceql_metrics_range(
    backend_id="{backend_id}",
    query='{{ resource.service.name = "{service}" }} | quantile_over_time(duration, 0.99)',
    since="6h"
)
```

### Step 4: Investigate Anomalies
Based on which metric shows anomalies:
- **High error rate** → `tempo_traceql_search(service="{service}", status="error")`
- **High latency** → `tempo_traceql_search(service="{service}", min_duration_ms=<threshold>)`
- **Rate drop** → Check backend diagnostics and ingestion pipeline

### Step 5: Deep Dive
```
Tool: tempo_summarize_trace(backend_id="{backend_id}", trace_id="<from_search>")
```
"""
            return [
                PromptMessage(role="user", content=TextContent(type="text", text=prompt_text))
            ]
