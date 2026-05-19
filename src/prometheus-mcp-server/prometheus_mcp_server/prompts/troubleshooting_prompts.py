"""Troubleshooting guided workflow prompts."""

from mcp.types import PromptMessage, TextContent
from prometheus_mcp_server.prompts.base import BasePrompt


class TroubleshootingPrompts(BasePrompt):
    """Troubleshooting workflow prompts."""

    def register(self, mcp_instance) -> None:  # type: ignore[no-untyped-def]

        @mcp_instance.prompt(
            name="prom-troubleshoot-guided",
            description="Guided workflow for diagnosing failed scrape targets and metric issues",
        )
        def prom_troubleshoot_guided(
            backend_id: str,
            job: str,
            namespace: str = "default",
        ) -> list[PromptMessage]:
            prompt_text = f"""# 🛠 Prometheus Troubleshooting Guide

## Context
- **Backend**: {backend_id}
- **Job**: {job}
- **Namespace**: {namespace}

---

## Phase 1: Check Failed Targets

1. **Get failed targets**:
   ```
   Resource: prom://topology/failed_targets
   ```
   Look for targets matching job="{job}".

---

## Phase 2: Inspect Target Health

1. **Check up status**:
   ```
   Tool: prom_query_instant(backend_id="{backend_id}", query="up{{job='{job}'}}")
   ```

2. **Check scrape duration**:
   ```
   Tool: prom_query_instant(backend_id="{backend_id}", query="scrape_duration_seconds{{job='{job}'}}")
   ```

---

## Phase 3: Validate Endpoint

1. **Test the metrics endpoint directly**:
   ```
   Tool: prom_test_endpoint(endpoint_url="http://<service>.{namespace}:<port>/metrics")
   ```

---

## Common Scenarios

### Scenario A: "Connection Refused"
**Cause**: The target Pod/VM is not running or the port is wrong.
**Fix**: Verify the Deployment is healthy, check port configuration in ServiceMonitor.

### Scenario B: "Context Deadline Exceeded"
**Cause**: Scrape timeout exceeded; endpoint is too slow.
**Fix**: Increase scrape_timeout or optimize the metrics endpoint.

### Scenario C: "401 Unauthorized"
**Cause**: Endpoint requires authentication.
**Fix**: Configure bearer token or basic auth in the ServiceMonitor/scrape config.

---

## Phase 4: Check Cardinality

High cardinality can cause performance issues:
```
Resource: prom://tsdb/cardinality
```
"""
            return [
                PromptMessage(role="user", content=TextContent(type="text", text=prompt_text))
            ]
