"""Alert triage guided workflow prompts."""
from mcp.types import PromptMessage, TextContent
from alertmanager_mcp_server.prompts import BasePrompt


class TriagePrompts(BasePrompt):
    def register(self, mcp_instance) -> None:
        @mcp_instance.prompt(name="am-alert-triage-guided",
                             description="Guided workflow for triaging active alerts")
        def am_alert_triage(backend_id: str, service: str = "checkout", env: str = "prod") -> list[PromptMessage]:
            return [PromptMessage(role="user", content=TextContent(type="text", text=f"""# 🚨 Alert Triage Guide

## Context
- **Backend**: {backend_id}
- **Service**: {service}
- **Environment**: {env}

## Phase 1: See What's Firing
```
Tool: am_alert_mgmt(action="list", backend_id="{backend_id}", label_filters={{"service": "{service}", "env": "{env}"}})
```

## Phase 2: Group Related Alerts
```
Tool: am_alert_mgmt(action="list_groups", backend_id="{backend_id}")
```

## Phase 3: Check Routing
```
Tool: am_alert_mgmt(action="simulate_routing", backend_id="{backend_id}", alert_labels={{"alertname": "<from step 1>", "service": "{service}", "env": "{env}"}})
```

## Phase 4: Investigate with Prometheus MCP
Use the Prometheus MCP server for metric-level diagnostics:
```
prom_query_mgmt(action="instant", query="up{{service='{service}'}}")
```
"""))]
