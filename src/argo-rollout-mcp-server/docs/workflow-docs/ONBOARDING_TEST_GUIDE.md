# Onboarding Test Guide — hello-world with Argo Rollout MCP Server

**Target application**: `hello-world` in `default` namespace  
**Ingress**: Traefik  
**Prometheus**: `prometheus-server` in `monitoring` namespace  
**Strategies**: Canary, Blue-Green, Rolling Update  
**Analysis**: Optional (with or without Prometheus-backed analysis)

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Environment Setup](#2-environment-setup)
3. [Prometheus Queries for Traefik](#3-prometheus-queries-for-traefik)
4. [Test Scenarios](#4-test-scenarios)
5. [Natural Language Prompts](#5-natural-language-prompts)
6. [ArgoCD and Cleanup Scenarios](#6-argocd-and-cleanup-scenarios)

---

## 1. Prerequisites

| Component | Status |
|-----------|--------|
| Kubernetes cluster | Accessible via `kubectl` |
| Argo Rollouts | Installed (`kubectl get rollouts -A`) |
| Argo Rollout MCP Server | Running (Docker recommended: `talkopsai/argo-rollout-mcp-server:latest`) |
| hello-world Deployment | Exists in `default` namespace (ArgoCD-managed or manual) |
| Prometheus | `prometheus-server` in `monitoring` namespace (port 80) |
| Traefik | Installed (optional for canary traffic routing) |

**Set Prometheus URL** (used by analysis template tool):

```bash
export PROMETHEUS_URL="http://prometheus-server.monitoring.svc.cluster.local:80"
```

---

## 2. Environment Setup

### Verify hello-world Deployment

```bash
kubectl get deployment hello-world -n default
kubectl get svc -n default | grep hello-world
```

### Verify Prometheus

```bash
kubectl get svc -n monitoring prometheus-server
```

### Start MCP Server (Docker — recommended)

```bash
docker run --rm -it \
  -p 8768:8768 \
  -v ~/.kube:/app/.kube:ro \
  -e K8S_KUBECONFIG=/app/.kube/config \
  -e PROMETHEUS_URL="http://prometheus-server.monitoring.svc.cluster.local:80" \
  talkopsai/argo-rollout-mcp-server:latest
```

> **Tip:** If Prometheus is in a different namespace or URL, adjust `PROMETHEUS_URL`. For host networking (e.g. Prometheus on host), use `--network host` or the appropriate host URL.

---

## 3. Prometheus Queries for Traefik

The default analysis template uses `http_requests_total` and `http_request_duration_seconds_bucket` with a `job` label. **Traefik uses different metric names.** Use custom metrics when configuring analysis for Traefik-backed apps.

### Traefik Service Metrics (Prometheus)

| Metric | Labels | Purpose |
|--------|--------|---------|
| `traefik_service_requests_total` | `code`, `method`, `protocol`, `service` | Request count and error rate |
| `traefik_service_request_duration_seconds_bucket` | `code`, `method`, `protocol`, `service`, `le` | Latency histogram |

### Traefik Service Name Format

In Kubernetes, Traefik service names typically look like:
- `hello-world-stable-default@kubernetescrd`
- `hello-world-canary-default@kubernetescrd`

Use a regex to match both: `service=~"hello-world-(stable|canary).*"` or `service=~"hello-world.*"`.

### Custom Metrics for `argo_configure_analysis_template`

When calling the tool with `metrics=[...]`, use these Traefik-specific queries:

**Error rate** (< 5%):

```promql
sum(rate(traefik_service_requests_total{service=~"hello-world.*", code=~"5.."}[5m])) 
/ sum(rate(traefik_service_requests_total{service=~"hello-world.*"}[5m]))
```

**P99 latency** (< 2 seconds):

```promql
histogram_quantile(0.99, 
  sum(rate(traefik_service_request_duration_seconds_bucket{service=~"hello-world.*"}[5m])) by (le)
)
```

**P95 latency** (< 1 second):

```promql
histogram_quantile(0.95, 
  sum(rate(traefik_service_request_duration_seconds_bucket{service=~"hello-world.*"}[5m])) by (le)
)
```

### Verify Queries in Prometheus

```bash
# Port-forward Prometheus (if needed)
kubectl port-forward svc/prometheus-server -n monitoring 9090:80

# Open http://localhost:9090 and run the queries above
# Or use curl:
curl -s 'http://localhost:9090/api/v1/query?query=sum(rate(traefik_service_requests_total{service=~"hello-world.*"}[5m]))'
```

### Full Custom Metrics JSON for Tool

```json
[
  {
    "name": "error-rate",
    "interval": "60s",
    "initialDelay": "60s",
    "failureLimit": 2,
    "successCondition": "result[0] < 0.05",
    "provider": {
      "prometheus": {
        "address": "http://prometheus-server.monitoring.svc.cluster.local:80",
        "query": "sum(rate(traefik_service_requests_total{service=~\"hello-world.*\", code=~\"5..\"}[5m])) / sum(rate(traefik_service_requests_total{service=~\"hello-world.*\"}[5m]))"
      }
    }
  },
  {
    "name": "latency-p99",
    "interval": "60s",
    "initialDelay": "60s",
    "failureLimit": 2,
    "successCondition": "result[0] < 2.0",
    "provider": {
      "prometheus": {
        "address": "http://prometheus-server.monitoring.svc.cluster.local:80",
        "query": "histogram_quantile(0.99, sum(rate(traefik_service_request_duration_seconds_bucket{service=~\"hello-world.*\"}[5m])) by (le))"
      }
    }
  },
  {
    "name": "latency-p95",
    "interval": "60s",
    "initialDelay": "60s",
    "failureLimit": 2,
    "successCondition": "result[0] < 1.0",
    "provider": {
      "prometheus": {
        "address": "http://prometheus-server.monitoring.svc.cluster.local:80",
        "query": "histogram_quantile(0.95, sum(rate(traefik_service_request_duration_seconds_bucket{service=~\"hello-world.*\"}[5m])) by (le))"
      }
    }
  }
]
```

### If Traefik Uses Different Service Names

List Traefik metrics to discover your service names:

```promql
# In Prometheus UI, run:
traefik_service_requests_total
```

Inspect the `service` label values and adjust the regex in the queries above (e.g. `service=~"hello-world-stable.*"` or `service="hello-world-stable-default@kubernetescrd"`).

---

## 4. Test Scenarios

### Scenario A: Onboarding — Canary (no analysis)

| Step | Action | Prompt / Tool |
|------|--------|----------------|
| 1 | Validate | "Check if hello-world deployment in default namespace is ready to migrate to Argo Rollouts." |
| 2 | Convert | "Convert hello-world to a canary Argo Rollout and apply it to the cluster." |
| 3 | Verify | "Show me the status of the hello-world rollout in default namespace." |

**Skip**: Analysis, traffic routing.

---

### Scenario B: Onboarding — Canary with Analysis (default metrics)

**Note**: Default metrics use `http_requests_total` and `job="hello-world"`. If your Prometheus scrape config does not expose these (e.g. Traefik-only), use custom Traefik metrics (Scenario C).

| Step | Action | Prompt / Tool |
|------|--------|----------------|
| 1 | Validate | "Check if hello-world deployment in default namespace is ready to migrate to Argo Rollouts." |
| 2 | Convert | "Convert hello-world to a canary Argo Rollout and apply it to the cluster." |
| 3 | Configure analysis | "Set up automated Prometheus analysis for the hello-world rollout in default." |
| 4 | Verify | "Show me the status of the hello-world rollout in default namespace." |

---

### Scenario C: Onboarding — Canary with Analysis (Traefik metrics)

| Step | Action | Prompt / Tool |
|------|--------|----------------|
| 1 | Validate | "Check if hello-world deployment in default namespace is ready to migrate to Argo Rollouts." |
| 2 | Convert | "Convert hello-world to a canary Argo Rollout and apply it to the cluster." |
| 3 | Configure analysis (custom) | Use tool `argo_configure_analysis_template` with `metrics` = the Traefik JSON from [Full Custom Metrics JSON](#full-custom-metrics-json-for-tool) above. |
| 4 | Verify | "Show me the status of the hello-world rollout in default namespace." |

---

### Scenario D: Onboarding — Blue-Green (no analysis)

| Step | Action | Prompt / Tool |
|------|--------|----------------|
| 1 | Validate | "Check if hello-world deployment in default namespace is ready to migrate to Argo Rollouts." |
| 2 | Convert | "Convert hello-world to a blue-green Argo Rollout and apply it to the cluster." |
| 3 | Verify | "Show me the status of the hello-world rollout in default namespace." |

---

### Scenario E: Onboarding — Blue-Green with Analysis

| Step | Action | Prompt / Tool |
|------|--------|----------------|
| 1 | Validate | "Check if hello-world deployment in default namespace is ready to migrate to Argo Rollouts." |
| 2 | Convert | "Convert hello-world to a blue-green Argo Rollout and apply it to the cluster." |
| 3 | Configure analysis | "Set up automated Prometheus analysis for the hello-world rollout in default." |
| 4 | Verify | "Show me the status of the hello-world rollout in default namespace." |

---

### Scenario F: Onboarding — Rolling Update (Single-Step Canary)

`convert_deployment_to_rollout` supports canary and blue-green only. For a rolling-update–style experience (no staged traffic):

1. Convert to canary with steps `[{"setWeight": 100}]` (single step = full cutover).
2. Or convert to canary, then update strategy to `canary_steps: [{"setWeight": 100}]` for instant promotion.

| Step | Action | Prompt / Tool |
|------|--------|----------------|
| 1 | Validate | "Check if hello-world deployment in default namespace is ready to migrate to Argo Rollouts." |
| 2 | Convert | "Convert hello-world to a canary Argo Rollout and apply it." |
| 3 | Update strategy (optional) | Use `argo_update_rollout(update_type='strategy', canary_steps=[{"setWeight": 100}])` to make it instant (no pauses). |
| 4 | Verify | "Show me the status of the hello-world rollout in default namespace." |

**Note**: Analysis is not typically used with single-step canary; it behaves like a rolling update.

---

### Scenario G: Deploy New Image (Canary with analysis)

After onboarding with analysis:

| Step | Action | Prompt / Tool |
|------|--------|----------------|
| 1 | Deploy new image | "Deploy hello-world:v2 to the hello-world rollout in default." |
| 2 | Promote (if paused) | "Promote the hello-world rollout in default to the next step." |
| 3 | Monitor | "Show me the status of the hello-world rollout in default namespace." |
| 4 | Full promotion | "Fully promote the hello-world rollout in default." |

---

### Scenario H: Rollback (Abort)

| Step | Action | Prompt / Tool |
|------|--------|----------------|
| 1 | Abort | "Abort the hello-world rollout in default." |

---

## 5. Natural Language Prompts

Copy-paste these prompts into your MCP client (Cursor, Claude, etc.) to drive the Argo Rollout MCP Server.

### Onboarding

```
Check if my hello-world deployment in the default namespace is ready to migrate to Argo Rollouts.
```

```
Convert the hello-world deployment in default to a canary Argo Rollout and apply it to the cluster.
```

```
Convert the hello-world deployment in default to a blue-green Argo Rollout and apply it.
```

```
Set up automated Prometheus analysis for the hello-world rollout in default.
```

**With Traefik custom metrics** (when default metrics don't apply):

```
Configure analysis for hello-world rollout in default using custom Traefik metrics: error rate from traefik_service_requests_total, latency from traefik_service_request_duration_seconds_bucket, service label matching hello-world.
```

(Or call `argo_configure_analysis_template` with the `metrics` parameter set to the Traefik JSON from the [Full Custom Metrics JSON](#full-custom-metrics-json-for-tool) section.)

```
Link the hello-world rollout in default to TraefikService "hello-world-route-wrr".
```

### Deployment & Lifecycle

```
Deploy hello-world:v2 to the hello-world rollout in default.
```

```
What's the current status of the hello-world rollout in default?
```

```
Promote the hello-world rollout in default to the next step.
```

```
Fully promote the hello-world rollout in default.
```

```
Abort the hello-world rollout in default.
```

### Verification

```
Show me the status of the hello-world rollout in default namespace.
```

```
List all rollouts in the default namespace.
```

```
Show me the cluster health summary.
```

### Reverse Migration & Cleanup

```
Convert the hello-world rollout back to a standard Deployment and give me the YAML.
```

```
Delete the hello-world rollout from the default namespace.
```

---

## 6. ArgoCD and Cleanup Scenarios

### ArgoCD-Managed hello-world

If `hello-world` is managed by ArgoCD:

1. **Before onboarding**: ArgoCD syncs the Deployment. The MCP tools will create a Rollout and Services. ArgoCD may still track the Deployment.
2. **Update ArgoCD Application**: Point the Application to the Rollout manifest (or a Helm chart that renders the Rollout) instead of the Deployment.
3. **ignoreDifferences**: Run `generate_argocd_ignore_differences` and add the output to your ArgoCD Application spec to avoid OutOfSync from Rollout status and TraefikService weights. Use `include_rollout_traffic_routing=True` if you link a TraefikService via `argo_update_rollout(update_type='traffic_routing')` and the Rollout is managed by ArgoCD/Helm — otherwise the trafficRouting patch may be reverted on sync.

**Prompt**:

```
Generate ArgoCD ignoreDifferences for hello-world in default, including rollout status, analysis runs, and Traefik service.
```

### Deleting the Onboarded Rollout (ArgoCD case)

If you onboarded via MCP and the Rollout is **not** in Git/ArgoCD:

| Step | Action | Tool / Prompt |
|------|--------|----------------|
| 1 | Delete Rollout | "Delete the hello-world rollout from the default namespace." |
| 2 | (Optional) Recreate Deployment | Re-apply the original Deployment YAML or let ArgoCD recreate it if it was in Git. |

If the Rollout **is** in Git/ArgoCD:

- Remove the Rollout from your Git repo (or Helm values).
- ArgoCD will delete it on sync.
- Or use `argo_delete_rollout` to delete from cluster; ArgoCD may recreate if still in Git.

### workloadRef and ArgoCD

For workloadRef mode (Rollout references existing Deployment):

```
Generate ArgoCD ignoreDifferences for hello-world in default, including deployment replicas for workloadRef, rollout status, and analysis runs.
```

Use `include_deployment_replicas=True` and `deployment_name="hello-world"` so ArgoCD does not revert the Rollout's scale-down of the Deployment.

---

## Quick Reference: Tool → Prompt Mapping

| Tool | Example Prompt |
|------|----------------|
| `validate_deployment_ready` | "Check if hello-world deployment in default is ready to migrate to Argo Rollouts." |
| `convert_deployment_to_rollout` | "Convert hello-world to a canary Argo Rollout and apply it." |
| `argo_configure_analysis_template` | "Set up Prometheus analysis for hello-world rollout in default." |
| `argo_update_rollout` (image) | "Deploy hello-world:v2 to the hello-world rollout in default." |
| `argo_manage_rollout_lifecycle` (promote) | "Promote the hello-world rollout in default." |
| `argo_manage_rollout_lifecycle` (abort) | "Abort the hello-world rollout in default." |
| `argo_delete_rollout` | "Delete the hello-world rollout from default." |
| `argorollout://rollouts/default/hello-world/detail` | "Show me the status of the hello-world rollout in default." |

---

## Troubleshooting

| Issue | Check |
|-------|-------|
| Analysis always "Inconclusive" | Verify `successCondition` (not `successCriteria`) in AnalysisTemplate. Run `kubectl get analysistemplate hello-world-analysis -n default -o yaml`. |
| Prometheus queries return no data | Confirm Traefik metrics are scraped. Run queries in Prometheus UI. Adjust `service` regex in custom metrics. |
| Rollout stuck in Progressing | Check `argorollout://rollouts/default/hello-world/detail`. Promote manually or abort. |
| ArgoCD OutOfSync | Add `generate_argocd_ignore_differences` output to Application spec. |
| trafficRouting not in spec after patch | (1) **Blue-green**: Argo Rollouts CRD does not support trafficRouting for blue-green — only canary. Convert to canary if you need Traefik. (2) **ArgoCD/Helm**: Sync reverts the patch. Add trafficRouting to Helm chart/ArgoCD source, or use `generate_argocd_ignore_differences(include_rollout_traffic_routing=True)`. |
| "Pod does not have a named port 'http'" | Services use `targetPort: http` but the image update patch was replacing the container spec and losing the named port. Fixed: `argo_update_rollout(update_type='image')` now preserves the full container spec (ports, probes, etc.) and only updates the image. |
