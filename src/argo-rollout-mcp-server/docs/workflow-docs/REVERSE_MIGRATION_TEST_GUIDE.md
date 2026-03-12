# Reverse Migration Test Guide — Rollout → Deployment with Argo Rollout MCP Server

**Target application**: `hello-world` in `default` namespace  
**Scenario**: Abandon Argo Rollouts and return to standard Kubernetes Deployments  
**Related**: [WORKFLOW_JOURNEYS.md](WORKFLOW_JOURNEYS.md) § Workflow 5b, [PROMPT_REFERENCE.md](PROMPT_REFERENCE.md)

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Environment Setup](#2-environment-setup)
3. [What Gets Converted](#3-what-gets-converted)
4. [Test Scenarios](#4-test-scenarios)
5. [Natural Language Prompts](#5-natural-language-prompts)
6. [Quick Reference: Tool → Prompt Mapping](#6-quick-reference-tool--prompt-mapping)
7. [Troubleshooting](#7-troubleshooting)

---

## 1. Prerequisites

| Component | Status |
|-----------|--------|
| Kubernetes cluster | Accessible via `kubectl` |
| Argo Rollout MCP Server | Running (Docker recommended: `talkopsai/argo-rollout-mcp-server:latest`) |
| hello-world Rollout | Exists in `default` namespace |

---

## 2. Environment Setup

### Verify hello-world Rollout

```bash
kubectl get rollout hello-world -n default -o yaml
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

## 3. What Gets Converted

| Preserved | Removed |
|-----------|---------|
| `spec.template` (pod template) | Argo strategy (canary/bluegreen steps) |
| `spec.replicas` | trafficRouting |
| `spec.selector` | workloadRef |
| `metadata` (name, namespace, labels) | Argo-specific annotations (`argoproj.io/*`) |
| | `managed-by: argoflow-mcp-server` label |

**Output**: Standard `apps/v1` Deployment with `RollingUpdate` strategy (or `Recreate`).

---

## 4. Test Scenarios

### Scenario A: Get Rollout YAML

| Step | Action | Prompt / Tool |
|------|--------|----------------|
| 1 | Fetch YAML | `kubectl get rollout hello-world -n default -o yaml` |
| 2 | Or use resource | `argorollout://rollouts/default/hello-world/detail` (may include full manifest) |

---

### Scenario B: Convert Rollout → Deployment

| Step | Action | Prompt / Tool |
|------|--------|----------------|
| 1 | Convert | "Convert the hello-world Argo Rollout in default back to a standard Kubernetes Deployment with RollingUpdate strategy, 25% max surge." |
| 2 | Or use tool | `convert_rollout_to_deployment(rollout_yaml="<yaml from step A>", deployment_strategy="RollingUpdate", max_surge="25%", max_unavailable="25%")` |
| 3 | Review | Check `deployment_yaml` in response — verify apiVersion, kind, template, replicas |

---

### Scenario C: Review Generated Deployment YAML

| Step | Action | Prompt / Tool |
|------|--------|----------------|
| 1 | Inspect | Verify `apiVersion: apps/v1`, `kind: Deployment`, `spec.strategy.type: RollingUpdate` |
| 2 | Adjust | Re-run with different `max_surge` or `max_unavailable` if needed |
| 3 | Save | Save YAML to file for `kubectl apply` |

---

### Scenario D: Apply Deployment and Delete Rollout

| Step | Action | Prompt / Tool |
|------|--------|----------------|
| 1 | Apply Deployment | `kubectl apply -f deployment.yaml` (manual step) |
| 2 | Delete Rollout | "Delete the hello-world rollout from the default namespace." |
| 3 | Or use tool | `argo_delete_rollout(name="hello-world", namespace="default")` |
| 4 | Verify | `kubectl get deployment hello-world -n default` |

---

### Scenario E: Update Services (Manual Step)

If the Rollout used `hello-world-stable` and `hello-world-canary` Services, you may need to:

| Step | Action | Prompt / Tool |
|------|--------|----------------|
| 1 | Point main Service | Update the primary Service selector to match the Deployment's pod template labels |
| 2 | Remove canary/stable | Delete or repurpose `hello-world-stable` and `hello-world-canary` if no longer needed |

---

### Scenario F: Clean Up Ingress Routes

| Step | Action | Prompt / Tool |
|------|--------|----------------|
| 1 | Update IngressRoute/TraefikService | Point traffic to the Deployment's Service instead of weighted TraefikService |
| 2 | Remove weighted routing | Delete or simplify TraefikService/IngressRoute if canary routing is no longer used |

---

## 5. Natural Language Prompts

Copy-paste these prompts into your MCP client (Cursor, Claude, etc.).

### Convert

```
Convert the hello-world Argo Rollout in default back to a standard Kubernetes Deployment with RollingUpdate strategy, 25% max surge.
```

```
I need to abandon Argo Rollouts for hello-world — convert the rollout YAML back to a standard deployment.
```

### Delete Rollout

```
Delete the hello-world Argo Rollout from the default namespace.
```

```
Remove the hello-world rollout in default and all its associated services.
```

---

## 6. Quick Reference: Tool → Prompt Mapping

| Tool | Example Prompt |
|------|----------------|
| `convert_rollout_to_deployment` | "Convert the hello-world Argo Rollout in default back to a standard Deployment with RollingUpdate, 25% max surge." |
| `argo_delete_rollout` | "Delete the hello-world Argo Rollout from the default namespace." |

### convert_rollout_to_deployment Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `rollout_yaml` | (required) | Argo Rollout YAML string (from `kubectl get rollout ... -o yaml`) |
| `deployment_strategy` | `"RollingUpdate"` | `RollingUpdate` or `Recreate` |
| `max_surge` | `"25%"` | Max surge for RollingUpdate |
| `max_unavailable` | `"25%"` | Max unavailable for RollingUpdate |

---

## 7. Troubleshooting

| Issue | Check |
|-------|-------|
| convert_rollout_to_deployment fails | Ensure `rollout_yaml` is valid YAML. For workloadRef rollouts, the tool strips workloadRef; ensure template is reconstructable. |
| Deployment has no template | workloadRef rollouts have no inline template. Fetch the referenced Deployment YAML and use that, or convert after the Rollout has been promoted and owns the workload. |
| Services still point to canary/stable | Manually update Service selectors to match Deployment pod template labels. |
| Argo CD recreates Rollout | If Rollout is in Git/Argo CD, remove it from the repo first, then delete from cluster. |
| Ingress still uses TraefikService | Update IngressRoute to point to the main Service; remove or simplify weighted routing. |
