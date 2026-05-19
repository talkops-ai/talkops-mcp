"""Onboarding and pipeline validation prompts."""
from mcp.types import PromptMessage, TextContent
from alertmanager_mcp_server.prompts import BasePrompt


class OnboardingPrompts(BasePrompt):
    def register(self, mcp_instance) -> None:
        @mcp_instance.prompt(name="am-integration-test-guided",
                             description="Guided workflow for testing notification integrations (Slack, PagerDuty)")
        def am_integration_test(backend_id: str, team: str = "sre", receiver: str = "slack-sre") -> list[PromptMessage]:
            return [PromptMessage(role="user", content=TextContent(type="text", text=f"""# 🧪 Integration Test Guide

## Context
- **Backend**: {backend_id}
- **Team**: {team}
- **Target Receiver**: {receiver}

## Phase 1: Check Receivers
```
Resource: am://system/receivers
```
Verify that receiver '{receiver}' is configured.

## Phase 2: Simulate Routing
```
Tool: am_alert_mgmt(action="simulate_routing", backend_id="{backend_id}", alert_labels={{"alertname": "MCPIntegrationTest", "team": "{team}", "env": "staging"}})
```

## Phase 3: Push Test Alert
```
Tool: am_alert_mgmt(action="push_test", backend_id="{backend_id}", alert_labels={{"alertname": "MCPIntegrationTest", "team": "{team}", "env": "staging", "severity": "warning"}}, annotations={{"summary": "Test alert from Alertmanager MCP"}})
```

## Phase 4: Verify Receipt
Ask the user to confirm the test alert arrived in {receiver}.
If not received, check routing config:
```
Resource: am://system/config
```
"""))]
