# Prometheus K8s CRD Rule Upsert Test Guide

## Scenario

An AI agent needs to safely discover and patch an existing `PrometheusRule` CRD in a Kubernetes cluster — without any manual `kubectl` fallback. This guide validates the full autonomous workflow enabled by the `prom://kubernetes/prometheusrules` resource.

> **Why this matters:** `prom_upsert_rule_group` with `storage_mode: k8s_crd` requires the exact Kubernetes `namespace` (and optionally `crd_labels`) to patch the correct resource. The `prom://rules/groups` resource fetches from the Prometheus evaluation API and **does not expose** this Kubernetes metadata. `prom://kubernetes/prometheusrules` bridges this gap entirely.

## Prerequisites

1. Prometheus MCP server running with Kubernetes integration enabled (`K8S_ENABLED=true`).
2. A running Kubernetes cluster with Prometheus Operator installed.
3. At least one `PrometheusRule` CRD present in the cluster (any namespace).
4. Your MCP client connected to the server.

---

## Step-by-Step Test Execution

### Step 1: Inventory Rule Groups from Prometheus
**User Prompt:**
"List all alerting and recording rule groups currently loaded in Prometheus."

**Expected Resource Access:**
`prom://rules/groups`

**Verification:**
The AI returns a JSON snapshot of all rule groups per backend with names, alert counts, and recording rule counts. Note one group name you want to modify (e.g., `"alertmanager.rules"`).

---

### Step 2: Discover PrometheusRule CRDs from Kubernetes
**User Prompt:**
"Find all PrometheusRule CRDs in the cluster and tell me which one owns the 'alertmanager.rules' group."

**Expected Resource Access:**
`prom://kubernetes/prometheusrules`

**Verification:**
The AI returns a structured list like:

```json
{
  "prometheus_rules": [
    {
      "name": "kube-prometheus-stack-alertmanager.rules",
      "namespace": "monitoring",
      "labels": { "release": "kube-prometheus-stack" },
      "groups": [
        {
          "name": "alertmanager.rules",
          "alert_rules": 5,
          "recording_rules": 0,
          "total_rules": 5
        }
      ],
      "total_groups": 1,
      "total_alert_rules": 5,
      "total_recording_rules": 0
    }
  ],
  "total_crds": 1
}
```

The AI should identify the owning CRD name (`kube-prometheus-stack-alertmanager.rules`) and its namespace (`monitoring`).

---

### Step 3: Describe the Target Alert Rule
**User Prompt:**
"Describe what the 'AlertmanagerDown' rule in the 'alertmanager.rules' group currently does."

**Expected Tool Invocation:**
`prom_describe_alert_rule(backend_id="<backend_id>", group_name="alertmanager.rules", alert_name="AlertmanagerDown")`

**Verification:**
The AI returns a human-readable explanation covering the PromQL expression, `for` duration, severity label, and what the alert means operationally.

---

### Step 4: Compose an Updated Rule
**User Prompt:**
"Draft an updated version of the AlertmanagerDown rule with a longer 'for' duration of 10 minutes."

**Expected Tool Invocation:**
`prom_draft_alert_rule(intent="alert when Alertmanager is down for 10 minutes", severity="critical")`

**Verification:**
The AI produces a valid YAML rule definition with the updated `for: 10m` clause.

---

### Step 5: Validate the Updated Rule Syntax
**User Prompt:**
"Validate the YAML for the updated rule before applying it."

**Expected Tool Invocation:**
`prom_check_rule_group(rules_yaml="...")`

**Verification:**
The AI confirms `valid: true` with zero syntax errors. If `promtool` is not in PATH, the tool should gracefully note this but still perform basic YAML validation.

---

### Step 6: Apply the Patch to the Correct CRD
**User Prompt:**
"Apply the updated rule group to the 'alertmanager.rules' group in the cluster, using the CRD namespace we found."

**Expected Tool Invocation:**
```
prom_upsert_rule_group(
  backend_id="<backend_id>",
  group_name="alertmanager.rules",
  rules=[...],
  storage_mode="k8s_crd",
  namespace="monitoring"
)
```

**Verification:**
The AI successfully patches the `PrometheusRule` CRD in the `monitoring` namespace and confirms the update. Verify by re-loading `prom://kubernetes/prometheusrules` — the group should show the updated rule count or the AI can describe the rule again via `prom_describe_alert_rule`.

---

### Step 7: Confirm the Change is Live
**User Prompt:**
"Confirm the updated rule is now loaded in Prometheus."

**Expected Resource Access:**
`prom://rules/groups`

**Verification:**
The AI checks `prom://rules/groups` and confirms the group is present with the expected configuration. Optionally also check:

`prom_query_instant(backend_id="<backend_id>", query="ALERTS{alertname='AlertmanagerDown'}", allow_raw_counters=true)`

---

## Edge Cases to Test

### K8s Integration Disabled
**User Prompt:**
"List all PrometheusRule CRDs."

**Setup:** Restart the server with `K8S_ENABLED=false`.

**Expected Behavior:**
The resource returns a JSON error with a hint:

```json
{
  "error": "Kubernetes service not configured",
  "hint": "Set K8S_ENABLED=true in your environment"
}
```

The AI should surface this gracefully and recommend enabling Kubernetes integration.

---

### No PrometheusRules in Cluster
**Setup:** Use a cluster with no `PrometheusRule` CRDs installed.

**Expected Behavior:**
The resource returns:

```json
{
  "prometheus_rules": [],
  "total_crds": 0,
  "total_groups": 0,
  "total_alert_rules": 0,
  "total_recording_rules": 0
}
```

---

### Namespace Mismatch (Negative Test)
**User Prompt:**
"Apply the rule to namespace 'default' instead of 'monitoring'."

**Expected Behavior:**
The `prom_upsert_rule_group` call should create a **new** CRD in `default` (since the original is in `monitoring`). The AI should warn that this is likely not the intended operation, and recommend using the namespace discovered from `prom://kubernetes/prometheusrules`.

---

## Troubleshooting

| Problem | Cause | Fix |
|---------|-------|-----|
| `Kubernetes client initialization failed` | `K8S_ENABLED=true` but no kubeconfig accessible | Verify `~/.kube/config` exists or set `K8S_IN_CLUSTER=true` inside a pod |
| `prom://kubernetes/prometheusrules` returns empty | Prometheus Operator not installed | Install `kube-prometheus-stack` or `prometheus-operator` Helm chart |
| `prom_upsert_rule_group` creates duplicate CRD | Wrong namespace passed | Always read `namespace` from `prom://kubernetes/prometheusrules` first |
| PrometheusRule not picked up by Prometheus | Missing selector labels | Check `labels` in the CRD and match against `prom://config/runtime` `ruleSelector` |

---

## Resource Reference

| Resource | Purpose in This Workflow |
|----------|--------------------------|
| `prom://rules/groups` | Discover active rule group names loaded in Prometheus |
| `prom://kubernetes/prometheusrules` | Get exact CRD `name`, `namespace`, and `labels` required for safe upsert |
| `prom://config/runtime` | Verify `ruleSelector` labels to ensure new CRDs are picked up |
