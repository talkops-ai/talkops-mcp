# Prometheus Rule Management Test Guide

## Scenario
You need to create a new alerting rule, validate its syntax, test it synthetically, and simulate its historical firing behavior before finally applying it to the cluster.

## Setup Instructions

1. Ensure the Prometheus MCP server is running (`uv run prometheus-mcp-server`).
2. Set the client configuration to connect to your local MCP server.
3. Have a valid backend ID ready (you can use `prom://system/backends` to find it).

## Step-by-Step Test Execution

### Step 1: Draft an Alert Rule
**User Prompt:**
"Draft an alert rule that fires when 5xx errors exceed 5%."

**Expected Tool Invocation:**
`prom_draft_alert_rule(intent="alert when 5xx errors exceed 5%")`

**Verification:**
The AI should return a valid PromQL expression and a YAML rule definition block.

### Step 2: Validate the Rule Syntax
**User Prompt:**
"Check the syntax of the generated YAML and PromQL expression to make sure it is valid."

**Expected Tool Invocation:**
`prom_check_rule_group(rules_yaml="...")`

**Verification:**
The AI should confirm the rule syntax is valid, returning `valid: true`.

### Step 3: Run Synthetic Tests
> [!WARNING]
> Synthetic testing using `promtool test rules` for `rate()` functions over mock counters is notoriously tricky due to Prometheus's rate extrapolation math (especially starting at zero). Expect to spend time tuning the `input_series` or opt for Live Verification (Step 7) instead.

**User Prompt:**
"Run synthetic unit tests for this rule. Assume we have 5xx error rates spiking to 10% at minute 5."

**Expected Tool Invocation:**
`prom_run_rule_tests(rules_yaml="...", test_yaml="...")`

**Verification:**
The AI should run the test using promtool and report that the tests passed.

### Step 4: Simulate Historical Firing
**User Prompt:**
"Simulate this rule over the last 24 hours to see if it would have fired."

**Expected Tool Invocation:**
`prom_simulate_firing_historical(backend_id="<backend_id>", expr="...", for_duration="5m")`

**Verification:**
The AI should query the historical metrics data and explain if the rule would have fired based on actual past data.

### Step 5: Apply the Rule Group
**User Prompt:**
"Apply the new rule group 'api_errors' to the cluster."

**Expected Tool Invocation:**
`prom_upsert_rule_group(backend_id="<backend_id>", group_name="api_errors", rules=[...])`

**Verification:**
The AI should successfully create the CustomResource (or configure via HTTP Ruler depending on storage mode) and confirm the rule is active.

### Step 5.5: Discover CRD Metadata Before k8s_crd Upsert
> [!IMPORTANT]
> This step is **mandatory** when using `storage_mode: k8s_crd`. Without the exact CRD `name` and `namespace`, the upsert will silently create a duplicate CRD instead of patching the existing rule.

**User Prompt:**
"Before patching the rule in Kubernetes, find the exact PrometheusRule CRD name and namespace."

**Expected Resource Access:**
`prom://kubernetes/prometheusrules`

**Verification:**
The AI should return a JSON list of all PrometheusRule CRDs with `name`, `namespace`, and `labels`. The agent picks the correct CRD entry and uses its `namespace` in the `prom_upsert_rule_group` call:

```
prom_upsert_rule_group(
  backend_id="<backend_id>",
  group_name="api_errors",
  rules=[...],
  storage_mode="k8s_crd",
  namespace="monitoring"  # ← from prom://kubernetes/prometheusrules
)
```

### Step 6: Fault Injection & Live Simulation (NEW)
**User Prompt:**
"Let's simulate an outage to trigger this alert. I will run a load generator. Please patch the backend service port to an invalid port (e.g., 81) to force 502 Bad Gateway errors."

**Expected Tool Invocation:**
`run_command(CommandLine="kubectl patch svc <service_name> -n <namespace> --type='json' -p='[{\"op\": \"replace\", \"path\": \"/spec/ports/0/targetPort\", \"value\": 81}]'")`

**Verification:**
The AI successfully patches the service, causing the live 5xx error rate to spike above the threshold.

### Step 7: Live Verification & State Machine (NEW)
**User Prompt:**
"Check if the alert is firing now."

**Expected Tool Invocation:**
`prom_query_instant(query="ALERTS{alertname='<your_alert_name>'}")`

**Verification:**
The AI should explain the Prometheus Alert State Machine:
1. **Pending**: The error rate condition is met, but the `for: <duration>` countdown is still running.
2. **Firing**: The `for` duration has elapsed, and the alert is actively routing to the Alertmanager.

---

## Advanced Scenario: Escalating Alerts (P1/P2)
Instead of a single alert, instruct the AI to create an escalating rule group.
**User Prompt:**
"Create two rules: a Warning (P2) if the error rate > 5% for 1m, and a Critical (P1) if it stays > 5% for 3m."

**Verification:**
Apply the rules, trigger an outage (Step 6), and query the `ALERTS` metric (Step 7) over 3 minutes. The AI should demonstrate the P2 alert entering the `firing` state while the P1 alert remains in the `pending` state until minute 3.

---

## Troubleshooting

- **promtool not available:** If you get an error that promtool is not in PATH, download the Prometheus release binary and add `promtool` to your system PATH.
- **k8s_crd mode fails:** If applying the rule fails in Kubernetes, verify that the Prometheus Operator is installed and your kubeconfig has the correct permissions.
