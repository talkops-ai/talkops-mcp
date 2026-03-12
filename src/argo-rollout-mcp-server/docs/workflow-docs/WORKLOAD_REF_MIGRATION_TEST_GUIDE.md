# workloadRef Migration Test Guide — Deployment → Rollout with Argo Rollout MCP Server

**Target application**: `hello-world` in `default` namespace  
**Prerequisite**: Existing Deployment (see [ONBOARDING_TEST_GUIDE.md](ONBOARDING_TEST_GUIDE.md) for validation)  
**Related**: [WORKFLOW_JOURNEYS.md](WORKFLOW_JOURNEYS.md) § Workflow 5a, [PROMPT_REFERENCE.md](PROMPT_REFERENCE.md)

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Environment Setup](#2-environment-setup)
3. [Key Difference: Direct vs workloadRef](#3-key-difference-direct-vs-workloadref)
4. [Test Scenarios](#4-test-scenarios)
5. [Natural Language Prompts](#5-natural-language-prompts)
6. [Quick Reference: Tool → Prompt Mapping](#6-quick-reference-tool--prompt-mapping)
7. [Troubleshooting](#7-troubleshooting)

---

## 1. Prerequisites

| Component | Status |
|-----------|--------|
| Kubernetes cluster | Accessible via `kubectl` |
| Argo Rollouts | Installed (`kubectl get rollouts -A`) |
| Argo Rollout MCP Server | Running (Docker recommended: `talkopsai/argo-rollout-mcp-server:latest`) |
| hello-world Deployment | Exists in `default` namespace |
| Argo CD (optional) | If Deployment is Argo CD–managed, use GitOps path for scale-down |

---

## 2. Environment Setup

### Verify hello-world Deployment

```bash
kubectl get deployment hello-world -n default
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

---

## 3. Key Difference: Direct vs workloadRef

| Aspect | Direct Conversion (Workflow 1) | workloadRef (This Workflow) |
|--------|-------------------------------|-----------------------------|
| Deployment | Scaled down, then replaced by Rollout | Kept; Rollout references it |
| Downtime | Brief gap during swap | None — Rollout and Deployment run in parallel |
| Scale-down | Manual or automatic | Automatic: `never`, `onsuccess`, or `progressively` |
| Use case | Simple swap | Argo CD / Helm-managed, cautious migration |

---

## 4. Test Scenarios

### Scenario A: Convert with workloadRef, scale_down=never (Co-Existence)

| Step | Action | Prompt / Tool |
|------|--------|----------------|
| 1 | Validate | "Check if hello-world deployment in default is ready to migrate to Argo Rollouts." |
| 2 | Convert | "Convert the hello-world deployment in default to an Argo Rollout using workloadRef mode — keep the existing Deployment running and scale it down only on success. Apply to cluster." |
| 3 | Or use tool | `convert_deployment_to_rollout(deployment_name="hello-world", namespace="default", strategy="canary", migration_mode="workload_ref", scale_down="never", apply=True)` |
| 4 | Verify | "Show me the status of the hello-world rollout in default namespace." |

---

### Scenario B: ArgoCD ignoreDifferences with include_deployment_replicas

| Step | Action | Prompt / Tool |
|------|--------|----------------|
| 1 | Generate | "Generate ArgoCD ignoreDifferences for hello-world in default with include_deployment_replicas for workloadRef." |
| 2 | Or use tool | `generate_argocd_ignore_differences(include_deployment_replicas=True, deployment_name="hello-world")` |
| 3 | Add to Application | Paste output into `Application.spec.ignoreDifferences` |

---

### Scenario C: Trigger New Version, Verify Scale-Down Behavior

| Step | Action | Prompt / Tool |
|------|--------|----------------|
| 1 | Deploy new image | "Deploy hello-world:v2 to the hello-world rollout in default." |
| 2 | Promote | "Promote the hello-world rollout in default to the next step." (repeat until 100%) |
| 3 | Verify | With `scale_down="onsuccess"`, Deployment scales to 0 when Rollout is Healthy |
| 4 | Check Deployment | `kubectl get deployment hello-world -n default` (replicas should be 0 after promotion) |

---

### Scenario D: Update scaleDown (never → onsuccess/progressively)

| Step | Action | Prompt / Tool |
|------|--------|----------------|
| 1 | Update scaleDown | "Change the workloadRef scaleDown on hello-world rollout in default to progressively scale down the Deployment." |
| 2 | Or use tool | `argo_update_rollout(update_type='workload_ref', name="hello-world", namespace="default", scale_down="progressively")` |
| 3 | Verify | "Show me the status of the hello-world rollout in default namespace." |

---

### Scenario E: Scale Down Deployment — GitOps Path

When Deployment is managed by Argo CD, cluster-direct scale is reverted. Use Git commit.

| Step | Action | Prompt / Tool |
|------|--------|----------------|
| 1 | Generate manifest | "Generate a scale-down manifest for the hello-world deployment in default — I'll commit it to Git for Argo CD to apply." |
| 2 | Or use tool | `argo_manage_legacy_deployment(action='generate_scale_down_manifest', name="hello-world", namespace="default")` |
| 3 | Commit to Git | Add the returned Deployment YAML (with `replicas: 0`) to your repo |
| 4 | Sync | Argo CD applies the change |

---

### Scenario F: Scale Down Deployment — Non-GitOps Path

When Deployment is **not** managed by Argo CD.

| Step | Action | Prompt / Tool |
|------|--------|----------------|
| 1 | Scale to 0 | Use tool: `argo_manage_legacy_deployment(action='scale_cluster', name="hello-world", namespace="default", replicas=0)` |
| 2 | Verify | `kubectl get deployment hello-world -n default` |

---

### Scenario G: Delete Deployment (Non-GitOps Only)

| Step | Action | Prompt / Tool |
|------|--------|----------------|
| 1 | Delete | Use tool: `argo_manage_legacy_deployment(action='delete_cluster', name="hello-world", namespace="default")` |
| 2 | **Warning** | Only when Deployment is **not** managed by Argo CD. Argo CD will recreate if still in Git. |

---

## 5. Natural Language Prompts

Copy-paste these prompts into your MCP client (Cursor, Claude, etc.).

### Convert with workloadRef

```
Convert the hello-world deployment in default to an Argo Rollout using workloadRef mode — keep the existing Deployment running and scale it down only on success. Apply to cluster.
```

```
Convert deployment hello-world in default to a canary rollout using workload_ref migration mode with progressive scale-down. Apply directly.
```

### Update scaleDown

```
Change the workloadRef scaleDown on hello-world rollout in default to progressively scale down the Deployment.
```

```
Update hello-world rollout in default — set workloadRef scaleDown to onsuccess so the Deployment scales down when the Rollout is healthy.
```

### Manage Legacy Deployment

```
Generate a scale-down manifest for the hello-world deployment in default — I'll commit it to Git for Argo CD to apply.
```

```
Generate YAML to scale hello-world deployment in default to 0 replicas for GitOps.
```

```
Scale the hello-world deployment in default to 0 replicas. (Only if NOT managed by Argo CD.)
```

```
Delete the hello-world deployment in default — we've fully migrated to the Rollout. (Only if NOT managed by Argo CD.)
```

---

## 6. Quick Reference: Tool → Prompt Mapping

| Tool | Example Prompt |
|------|----------------|
| `validate_deployment_ready` | "Check if hello-world deployment in default is ready to migrate." |
| `convert_deployment_to_rollout` (workload_ref) | "Convert hello-world to canary rollout using workloadRef mode, apply to cluster." |
| `argo_update_rollout` (workload_ref) | "Change workloadRef scaleDown on hello-world rollout to progressively." |
| `generate_argocd_ignore_differences` | "Generate ignoreDifferences for hello-world with include_deployment_replicas." |
| `argo_manage_legacy_deployment` (generate_scale_down_manifest) | "Generate scale-down manifest for hello-world deployment for GitOps." |
| `argo_manage_legacy_deployment` (scale_cluster) | Use tool with `action='scale_cluster', replicas=0` (non-GitOps only) |
| `argo_manage_legacy_deployment` (delete_cluster) | Use tool with `action='delete_cluster'` (non-GitOps only) |

---

## 7. Troubleshooting

| Issue | Check |
|-------|-------|
| Argo CD reverts Deployment scale-down | Add `generate_argocd_ignore_differences(include_deployment_replicas=True, deployment_name="hello-world")` to Application. Use Git path: `generate_scale_down_manifest` → commit. |
| Rollout has no workloadRef | Ensure `migration_mode="workload_ref"` was used in `convert_deployment_to_rollout`. |
| scale_down invalid | Must be `never`, `onsuccess`, or `progressively`. |
| Deployment still running after promotion | Check `scale_down` — if `never`, update to `onsuccess` or `progressively` via `argo_update_rollout(update_type='workload_ref')`. |
| generate_scale_down_manifest returns empty | Provide `name` or `deployment_yaml`. For live Deployment, use `name="hello-world"`. |
