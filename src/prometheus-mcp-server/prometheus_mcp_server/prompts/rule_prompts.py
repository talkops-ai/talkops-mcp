"""Rule management workflow guided prompts."""

from mcp.types import PromptMessage, TextContent
from prometheus_mcp_server.prompts.base import BasePrompt


class RulePrompts(BasePrompt):
    """Rule management workflow prompts for non-experts."""

    def register(self, mcp_instance) -> None:  # type: ignore[no-untyped-def]

        @mcp_instance.prompt(
            name="prom-rule-management-guided",
            description="Guided workflow for drafting, simulating, and applying Prometheus rules",
        )
        def prom_rule_management_guided(
            backend_id: str,
        ) -> list[PromptMessage]:
            prompt_text = f"""# 📝 Prometheus Rule Management Guide

## Context
- **Backend**: {backend_id}

---

## Step 1: Draft the Rule

Start by drafting an alerting or recording rule from natural language intent:
```
Tool: prom_draft_alert_rule(intent="alert when 5xx errors exceed 5%")
```
This returns the generated PromQL expression and YAML rule definition.

---

## Step 2: Validate the Rule Syntax

Before proceeding, ensure the generated YAML and PromQL are syntactically correct:
```
Tool: prom_check_rule_group(rules_yaml="<paste_yaml_from_step_1>")
```

---

## Step 3: Run Synthetic Unit Tests (Optional)

If you have test data, run synthetic tests against the rule:
```
Tool: prom_run_rule_tests(rules_yaml="<paste_yaml>", test_yaml="<paste_test_yaml>")
```

---

## Step 4: Simulate Historical Firing

Check if the drafted rule would have fired on real historical data over the last 24 hours:
```
Tool: prom_simulate_firing_historical(backend_id="{backend_id}", expr="<promql_expression>", for_duration="5m")
```

---

## Step 5: Apply the Rule to the Cluster

Once validated and tested, apply the rule group to the Prometheus cluster:
```
Tool: prom_upsert_rule_group(backend_id="{backend_id}", group_name="my_new_alerts", rules=[...])
```
"""
            return [
                PromptMessage(role="user", content=TextContent(type="text", text=prompt_text))
            ]
