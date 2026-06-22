"""Troubleshooting workflow prompts for Tempo."""

from mcp.types import PromptMessage, TextContent
from tempo_mcp_server.prompts.base import BasePrompt


class TroubleshootingPrompts(BasePrompt):
    """Troubleshooting workflow prompts."""

    def register(self, mcp_instance) -> None:  # type: ignore[no-untyped-def]

        @mcp_instance.prompt(
            name="tempo-error-triage",
            description="Guided workflow for triaging errors using Tempo traces. Metrics-first approach.",
        )
        def tempo_error_triage(
            backend_id: str,
            service: str,
            namespace: str = "default",
        ) -> list[PromptMessage]:
            prompt_text = f"""# 🔍 Tempo Error Triage

## Context
- **Backend**: {backend_id}
- **Service**: {service}
- **Namespace**: {namespace}

---

## Phase 1: Quantify Impact

1. **Error rate** — Check error rate for the service:
   ```
   Tool: tempo_traceql_metrics_range(
       backend_id="{backend_id}",
       query='{{ resource.service.name = "{service}" && status = error }} | rate()',
       since="1h"
   )
   ```

2. **Compare with baseline** — Check overall request rate:
   ```
   Tool: tempo_traceql_metrics_range(
       backend_id="{backend_id}",
       query='{{ resource.service.name = "{service}" }} | rate()',
       since="1h"
   )
   ```

---

## Phase 2: Find Error Traces

1. **Search for errors**:
   ```
   Tool: tempo_traceql_search(
       backend_id="{backend_id}",
       service="{service}",
       namespace="{namespace}",
       status="error",
       since="30m"
   )
   ```

---

## Phase 3: Analyze Root Cause

1. **Summarize the first error trace**:
   ```
   Tool: tempo_summarize_trace(backend_id="{backend_id}", trace_id="<from_step_2>")
   ```

2. **Find related errors**:
   ```
   Tool: tempo_find_related_traces(
       backend_id="{backend_id}",
       trace_id="<from_step_2>",
       strategy="same_service_errors"
   )
   ```

---

## Phase 4: Contextualize

1. **Check backend health**: `tempo_get_diagnostics(backend_id="{backend_id}")`
2. **Review K8s context** in the trace summary
3. **Check if this is a new pattern** or recurring
"""
            return [
                PromptMessage(role="user", content=TextContent(type="text", text=prompt_text))
            ]

        @mcp_instance.prompt(
            name="tempo-latency-investigation",
            description="Guided workflow for investigating latency spikes using Tempo traces.",
        )
        def tempo_latency_investigation(
            backend_id: str,
            service: str,
            threshold_ms: str = "500",
        ) -> list[PromptMessage]:
            prompt_text = f"""# ⏱ Tempo Latency Investigation

## Context
- **Backend**: {backend_id}
- **Service**: {service}
- **Threshold**: {threshold_ms}ms

---

## Phase 1: Confirm the Spike

1. **P99 latency trend**:
   ```
   Tool: tempo_traceql_metrics_range(
       backend_id="{backend_id}",
       query='{{ resource.service.name = "{service}" }} | quantile_over_time(duration, 0.99)',
       since="6h"
   )
   ```

---

## Phase 2: Find Slow Traces

1. **Search for traces above threshold**:
   ```
   Tool: tempo_traceql_search(
       backend_id="{backend_id}",
       service="{service}",
       min_duration_ms={threshold_ms},
       since="1h"
   )
   ```

---

## Phase 3: Critical Path Analysis

1. **Summarize the slowest trace**:
   ```
   Tool: tempo_summarize_trace(backend_id="{backend_id}", trace_id="<from_step_2>")
   ```

2. **Review critical path** — identify which service/operation contributes most to latency

---

## Phase 4: Compare with Normal Traces

1. **Find normal traces**:
   ```
   Tool: tempo_traceql_search(
       backend_id="{backend_id}",
       service="{service}",
       max_duration_ms={int(int(threshold_ms) / 2)},
       since="1h",
       limit=3
   )
   ```

2. Compare critical paths between slow and normal traces.
"""
            return [
                PromptMessage(role="user", content=TextContent(type="text", text=prompt_text))
            ]

        @mcp_instance.prompt(
            name="tempo-missing-traces",
            description="Diagnostic workflow for 'no traces found' scenarios.",
        )
        def tempo_missing_traces(
            backend_id: str,
            service: str = "",
        ) -> list[PromptMessage]:
            service_context = f'for service "{service}"' if service else ""
            prompt_text = f"""# ❓ Missing Traces Investigation

## Context
- **Backend**: {backend_id}
- **Issue**: No traces found {service_context}

---

## Phase 1: Verify Backend

1. **Run diagnostics**:
   ```
   Tool: tempo_get_diagnostics(backend_id="{backend_id}")
   ```

## Phase 2: Verify Data Exists

1. **Check available attributes** (proves data is being ingested):
   ```
   Tool: tempo_get_attribute_names(backend_id="{backend_id}", since="1h")
   ```

2. **Broadest possible search**:
   ```
   Tool: tempo_traceql_search(backend_id="{backend_id}", since="24h", limit=5)
   ```

## Phase 3: Check Scope

1. **For multi-tenant**: Verify tenant ID is correct
2. **For K8s**: Check namespace and service exist in attributes:
   ```
   Tool: tempo_get_attribute_values(backend_id="{backend_id}", attribute="service.name", since="1h")
   ```

## Phase 4: Consult Runbook
   ```
   Resource: tempo://runbooks/no-traces-found
   ```
"""
            return [
                PromptMessage(role="user", content=TextContent(type="text", text=prompt_text))
            ]
