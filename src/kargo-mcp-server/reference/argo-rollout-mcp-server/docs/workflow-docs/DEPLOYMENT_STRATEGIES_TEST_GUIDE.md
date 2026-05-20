# Deployment Strategies Test Guide — hello-world with Argo Rollout MCP Server

**Target application**: `hello-world` in `default` namespace  
**Prerequisite**: Onboarded rollout (see [ONBOARDING_TEST_GUIDE.md](ONBOARDING_TEST_GUIDE.md))  
**Strategies**: Rolling Update, Canary, Blue-Green  
**Related**: [WORKFLOW_JOURNEYS.md](WORKFLOW_JOURNEYS.md) § Workflow 2, [PROMPT_REFERENCE.md](PROMPT_REFERENCE.md)

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Environment Setup](#2-environment-setup)
3. [Test Scenarios](#3-test-scenarios)
4. [Natural Language Prompts](#4-natural-language-prompts)
5. [Quick Reference: Tool → Prompt Mapping](#5-quick-reference-tool--prompt-mapping)
6. [Troubleshooting](#6-troubleshooting)

---

## 1. Prerequisites

| Component | Status |
|-----------|--------|
| Kubernetes cluster | Accessible via `kubectl` |
| Argo Rollouts | Installed (`kubectl get rollouts -A`) |
| Argo Rollout MCP Server | Running (Docker recommended: `talkopsai/argo-rollout-mcp-server:latest`) |
| hello-world Rollout | Already onboarded (canary or blue-green) in `default` namespace |
| Prometheus | Optional; required for analysis-backed canary/blue-green |
| Traefik | Optional; required for canary traffic routing |

---

## 2. Environment Setup

### Verify hello-world Rollout

```bash
kubectl get rollout hello-world -n default
kubectl get svc -n default | grep hello-world
```

### Start MCP Server (Docker — recommended)

```bash
docker run --rm -it \
  -p 8768:8768 \
  -v ~/.kube:/app/.kube:ro \
  -e K8S_KUBECONFIG=/app/.kube/config \
  talkopsai/argo-rollout-mcp-server:latest
```

### Resources for Monitoring

| Resource | Purpose |
|----------|---------|
| `argorollout://rollouts/default/hello-world/detail` | Rollout phase, replicas, canary weights |
| `argorollout://health/summary` | Cluster health score |
| `argorollout://health/default/hello-world/details` | Per-app health |
| `argorollout://cluster/health` | Cluster capacity, pre-flight |

---

## 3. Test Scenarios

### Scenario A: Rolling Update

Pre-flight → update image → monitor → verify. Uses standard K8s rolling update mechanics.

| Step | Action | Prompt / Tool |
|------|--------|----------------|
| 1 | Pre-flight | "Check if hello-world deployment in default is ready." + fetch `argorollout://cluster/health` |
| 2 | Update image | "Deploy hello-world:v2 to the hello-world rollout in default." |
| 3 | Monitor (poll every 30s) | "Show me the status of the hello-world rollout in default namespace." |
| 4 | Verify | Phase=Healthy, updatedReplicas=replicas, health score >90 |
| 5 | Rollback (if needed) | "Abort the hello-world rollout in default." |

**Guided prompt**: `rolling_update_guided(app_name="hello-world", new_image="hello-world:v2", namespace="default")`

---

### Scenario B: Canary Deployment (Step-by-Step Promotion)

Deploy new image → promote through steps (5%→10%→25%→50%→100%) with health checks.

| Step | Action | Prompt / Tool |
|------|--------|----------------|
| 1 | Pre-flight | "Check if hello-world deployment in default is ready." + `argorollout://cluster/health` |
| 2 | Deploy canary | "Deploy hello-world:v2 to the hello-world rollout in default." |
| 3 | Monitor | "Show me the status of the hello-world rollout in default namespace." |
| 4 | Promote (5%→10%) | "Promote the hello-world rollout in default to the next step." (wait 60s, check health) |
| 5 | Promote (10%→25%) | "Promote the hello-world rollout in default to the next step." (wait 120s) |
| 6 | Promote (25%→50%) | "Promote the hello-world rollout in default to the next step." (wait 300s) |
| 7 | Promote (50%→100%) | "Fully promote the hello-world rollout in default." |
| 8 | Verify | Phase=Healthy, health score >90 |

**Guided prompt**: `canary_deployment_guided(app_name="hello-world", new_image="hello-world:v2", namespace="default")`

---

### Scenario C: Blue-Green Deployment

Deploy preview → pre-promotion analysis → promote → post-promotion analysis.

| Step | Action | Prompt / Tool |
|------|--------|----------------|
| 1 | Pre-flight | `argorollout://cluster/health` (confirm 2x capacity) |
| 2 | Deploy preview | "Deploy hello-world:v2 to the hello-world rollout in default." |
| 3 | Wait for preview ready | "Show me the status of the hello-world rollout in default namespace." |
| 4 | Pre-promotion analysis | Automatic via `pre_promotion_analysis` if configured |
| 5 | Switch traffic | "Promote the hello-world rollout in default." |
| 6 | Post-promotion analysis | Automatic via `post_promotion_analysis` if configured |
| 7 | Verify | Phase=Healthy |

**Guided prompt**: `blue_green_deployment_guided(app_name="hello-world", new_image="hello-world:v2", namespace="default", auto_switch=True)`

---

### Scenario D: Pause and Resume Canary

| Step | Action | Prompt / Tool |
|------|--------|----------------|
| 1 | Deploy canary | "Deploy hello-world:v2 to the hello-world rollout in default." |
| 2 | Pause | "Pause the hello-world rollout in default." |
| 3 | Verify paused | "Show me the status of the hello-world rollout in default namespace." |
| 4 | Resume | "Resume the paused hello-world rollout in default." |
| 5 | Promote | "Promote the hello-world rollout in default to the next step." |

---

### Scenario E: Abort (Rollback)

| Step | Action | Prompt / Tool |
|------|--------|----------------|
| 1 | Abort | "Abort the hello-world rollout in default." |
| 2 | Verify | "Show me the status of the hello-world rollout in default namespace." (Phase=Healthy, stable version) |

---

### Scenario F: Update Canary Strategy (Steps, canaryService)

| Step | Action | Prompt / Tool |
|------|--------|----------------|
| 1 | Update strategy | "Update the hello-world rollout in default to use canary steps: 20% → pause → 40% → pause 10s → 60% → pause 10s → 80% → pause 10s." |
| 2 | Or use tool | `argo_update_rollout(update_type='strategy', name="hello-world", namespace="default", canary_steps=[{"setWeight": 20}, {"pause": {}}, {"setWeight": 40}, {"pause": {"duration": "10s"}}, {"setWeight": 60}, {"pause": {"duration": "10s"}}, {"setWeight": 80}, {"pause": {"duration": "10s"}}, {"setWeight": 100}])` |
| 3 | Verify | "Show me the status of the hello-world rollout in default namespace." |

---

## 4. Natural Language Prompts

Copy-paste these prompts into your MCP client (Cursor, Claude, etc.).

### Rolling Update

```
Do a rolling update of hello-world in default to image hello-world:v2.
```

```
Deploy hello-world:v2 to the hello-world rollout in default.
```

```
What's the current status of the hello-world rollout in default?
```

### Canary

```
Guide me through a canary deployment of hello-world:v2 in default.
```

```
Deploy hello-world:v2 to the hello-world rollout in default.
```

```
Promote the hello-world rollout in default to the next step.
```

```
Fully promote the hello-world rollout in default.
```

### Blue-Green

```
Set up a blue-green deployment for hello-world in default with image hello-world:v2.
```

```
Promote the hello-world rollout in default.
```

### Lifecycle

```
Pause the hello-world rollout in default.
```

```
Resume the paused hello-world rollout in default.
```

```
Abort the hello-world rollout in default.
```

### Verification

```
Show me the status of the hello-world rollout in default namespace.
```

```
Give me a health summary of the cluster.
```

```
Show health details for hello-world in default.
```

---

## 5. Quick Reference: Tool → Prompt Mapping

| Tool | Example Prompt |
|------|----------------|
| `validate_deployment_ready` | "Check if hello-world deployment in default is ready." |
| `argo_update_rollout` (image) | "Deploy hello-world:v2 to the hello-world rollout in default." |
| `argo_update_rollout` (strategy) | "Update hello-world rollout canary steps to 20% → pause → 40% → 100%." |
| `argo_manage_rollout_lifecycle` (promote) | "Promote the hello-world rollout in default." |
| `argo_manage_rollout_lifecycle` (promote_full) | "Fully promote the hello-world rollout in default." |
| `argo_manage_rollout_lifecycle` (pause) | "Pause the hello-world rollout in default." |
| `argo_manage_rollout_lifecycle` (resume) | "Resume the paused hello-world rollout in default." |
| `argo_manage_rollout_lifecycle` (abort) | "Abort the hello-world rollout in default." |
| `argorollout://rollouts/default/hello-world/detail` | "Show me the status of the hello-world rollout in default." |
| `argorollout://health/summary` | "Give me a health summary of the cluster." |
| `argorollout://cluster/health` | "What is the overall health and capacity of my cluster?" |

---

## 6. Troubleshooting

| Issue | Check |
|-------|-------|
| Rollout stuck in Progressing | Check `argorollout://rollouts/default/hello-world/detail`. Promote manually or abort. |
| Canary weights not shifting | Ensure traffic routing is linked (`argo_update_rollout` update_type='traffic_routing') and TraefikService/IngressRoute exists. |
| Blue-green not switching | Verify `activeService` and `previewService` are configured. Check rollout spec. |
| Analysis blocking promotion | If Prometheus is down, use `argo_manage_rollout_lifecycle(action='skip_analysis')` for emergency promotion. |
| CrashLoopBackOff during deploy | Abort immediately: "Abort the hello-world rollout in default." |
| Health score low | Check `argorollout://health/default/hello-world/details` for error rate and latency. |
