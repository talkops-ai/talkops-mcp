# Zero-Downtime Migration Test Guide — Argo CD with Argo Rollout MCP Server

**Target application**: `hello-world` in `default` namespace  
**Prerequisite**: Deployment managed by Argo CD  
**Related**: [WORKFLOW_JOURNEYS.md](WORKFLOW_JOURNEYS.md) § Workflow 6, [WORKLOAD_REF_MIGRATION_TEST_GUIDE.md](WORKLOAD_REF_MIGRATION_TEST_GUIDE.md), [Zero-Downtime Migration from Kubernetes Deployment to Argo Rollouts under Argo CD](Zero-Downtime%20Migration%20from%20Kubernetes%20Deployment%20to%20Argo%20Rollouts%20under%20Argo%20CD.md)

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Key Principle](#2-key-principle)
3. [Environment Setup](#3-environment-setup)
4. [Test Scenarios](#4-test-scenarios)
5. [Natural Language Prompts](#5-natural-language-prompts)
6. [Quick Reference: Tool → Migration Step](#6-quick-reference-tool--migration-step)
7. [Troubleshooting](#7-troubleshooting)

---

## 1. Prerequisites

| Component | Status |
|-----------|--------|
| Argo CD | Installed and managing the Deployment |
| Argo Rollouts | Installed in cluster |
| Argo Rollout MCP Server | Running (Docker recommended: `talkopsai/argo-rollout-mcp-server:latest`) |
| hello-world Deployment | Exists in `default` namespace, managed by Argo CD from Git |

---

## 2. Key Principle

> **Argo CD reverts cluster-direct changes.** Scale-down of the Deployment must be done via **Git commits** (or `ignoreDifferences` for `workloadRef`). Use `argo_manage_legacy_deployment(action='generate_scale_down_manifest')` for the GitOps path; `argo_manage_legacy_deployment(action='scale_cluster'|'delete_cluster')` only for non–Argo CD–managed workloads.

---

## 3. Environment Setup

### Verify Argo CD and Deployment

```bash
argocd app get hello-world
kubectl get deployment hello-world -n default
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

## 4. Test Scenarios

### Scenario A: Validate Readiness

| Step | Action | Prompt / Tool |
|------|--------|----------------|
| 1 | Validate | "Run validate_deployment_ready for hello-world in default before zero-downtime migration." |
| 2 | Or use tool | `validate_deployment_ready(deployment_name="hello-world", namespace="default")` |
| 3 | Fix issues | Address any blocking issues (selector, template, pod-template-hash in Service) |

---

### Scenario B: Convert with workloadRef, scale_down=never

| Step | Action | Prompt / Tool |
|------|--------|----------------|
| 1 | Convert | "Convert the hello-world deployment in default to an Argo Rollout using workloadRef mode — keep the existing Deployment running, scale_down=never. Apply to cluster." |
| 2 | Or use tool | `convert_deployment_to_rollout(deployment_name="hello-world", namespace="default", strategy="canary", migration_mode="workload_ref", scale_down="never", apply=True)` |
| 3 | Verify | Rollout and Deployment run in parallel (co-existence) |

---

### Scenario C: Generate ArgoCD ignoreDifferences (include_deployment_replicas)

| Step | Action | Prompt / Tool |
|------|--------|----------------|
| 1 | Generate | "Generate ArgoCD ignoreDifferences for hello-world in default with include_deployment_replicas so Argo CD won't revert the Rollout's scale-down of the Deployment." |
| 2 | Or use tool | `generate_argocd_ignore_differences(include_deployment_replicas=True, deployment_name="hello-world")` |
| 3 | Add to Application | Paste output into `Application.spec.ignoreDifferences` |
| 4 | Commit and sync | Commit to Git, Argo CD syncs |

---

### Scenario D: Update scaleDown (never → progressively)

| Step | Action | Prompt / Tool |
|------|--------|----------------|
| 1 | Update | "Change the workloadRef scaleDown on hello-world rollout in default to progressively." |
| 2 | Or use tool | `argo_update_rollout(update_type='workload_ref', name="hello-world", namespace="default", scale_down="progressively")` |

---

### Scenario E: Scale Down Deployment — GitOps Path (Argo CD–Managed)

| Step | Action | Prompt / Tool |
|------|--------|----------------|
| 1 | Generate manifest | "Generate the Deployment scale-down YAML for hello-world in default — I'll commit it to Git for Argo CD to apply after the Rollout is stable." |
| 2 | Or use tool | `argo_manage_legacy_deployment(action='generate_scale_down_manifest', name="hello-world", namespace="default")` |
| 3 | Commit to Git | Add the returned Deployment YAML (with `replicas: 0`) to your repo |
| 4 | Sync | Argo CD applies the change; Deployment scales to 0 |

---

### Scenario F: Scale Down Deployment — Non-GitOps Path

When Deployment is **not** managed by Argo CD:

| Step | Action | Prompt / Tool |
|------|--------|----------------|
| 1 | Scale to 0 | Use tool: `argo_manage_legacy_deployment(action='scale_cluster', name="hello-world", namespace="default", replicas=0)` |
| 2 | Verify | `kubectl get deployment hello-world -n default` |

---

### Scenario G: Delete Deployment (Non-GitOps Only)

| Step | Action | Prompt / Tool |
|------|--------|----------------|
| 1 | Delete | Use tool: `argo_manage_legacy_deployment(action='delete_cluster', name="hello-world", namespace="default")` |
| 2 | **Warning** | Only when **not** managed by Argo CD. Argo CD will recreate if still in Git. |

---

## 5. Natural Language Prompts

Copy-paste these prompts into your MCP client (Cursor, Claude, etc.).

### Validate

```
Run validate_deployment_ready for hello-world in default before zero-downtime migration.
```

### Convert (workloadRef)

```
Convert the hello-world deployment in default to an Argo Rollout using workloadRef mode — keep the existing Deployment running, scale_down=never. Apply to cluster.
```

### ignoreDifferences

```
Generate ArgoCD ignoreDifferences for hello-world in default with include_deployment_replicas so Argo CD won't revert the Rollout's scale-down of the Deployment.
```

### Scale-Down Manifest (GitOps)

```
Generate the Deployment scale-down YAML for hello-world in default — I'll commit it to Git for Argo CD to apply after the Rollout is stable.
```

### Full Sequence

```
Run validate_deployment_ready for hello-world in default before zero-downtime migration.
```

```
Generate ArgoCD ignoreDifferences for hello-world in default with include_deployment_replicas so Argo CD won't revert the Rollout's scale-down of the Deployment.
```

```
Generate the Deployment scale-down YAML for hello-world in default — I'll commit it to Git for Argo CD to apply after the Rollout is stable.
```

---

## 6. Quick Reference: Tool → Migration Step

| Migration Step | Tool | Notes |
|----------------|------|-------|
| 1. Validate readiness | `validate_deployment_ready` | Structural + Service selector (no `pod-template-hash`) |
| 2. Introduce Rollout (workloadRef) | `convert_deployment_to_rollout(migration_mode="workload_ref", scale_down="never", apply=True)` | Co-existence phase |
| 3. Argo CD ignoreDifferences | `generate_argocd_ignore_differences(include_deployment_replicas=True, deployment_name="hello-world")` | Prevents revert of scale-down |
| 4. Switch traffic | Traffic MCP server (out of scope) | Traefik, Istio, etc. |
| 5. Update scaleDown | `argo_update_rollout(update_type='workload_ref', scale_down="progressively")` | `never` → `onsuccess` or `progressively` |
| 6. Scale down Deployment | **GitOps**: `argo_manage_legacy_deployment(action='generate_scale_down_manifest')` → commit YAML. **Non-GitOps**: `argo_manage_legacy_deployment(action='scale_cluster', replicas=0)` | Argo CD reverts cluster-direct scale |
| 7. Delete Deployment (optional) | **Non-GitOps**: `argo_manage_legacy_deployment(action='delete_cluster')` | Only when not managed by Argo CD |

---

## 7. Troubleshooting

| Issue | Check |
|-------|-------|
| Argo CD reverts Deployment scale-down | Use Git path: `generate_scale_down_manifest` → commit YAML. Add `include_deployment_replicas=True` to ignoreDifferences. |
| Rollout and Deployment both running | Expected during co-existence. Update `scale_down` to `onsuccess` or `progressively` when ready. |
| Traffic not switching | Traffic switching is out of scope for this MCP server. Configure Traefik/Istio separately. See [rollout-traefik-functionality.md](rollout-traefik-functionality.md). |
| ignoreDifferences not applied | Ensure output is in `Application.spec.ignoreDifferences`. Sync the Application. |
| Deployment still in Git | Remove Deployment manifest from Git repo before or after scale-down, depending on your GitOps workflow. |
