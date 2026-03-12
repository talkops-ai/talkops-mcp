# ArgoCD GitOps Integration Test Guide — Argo Rollout MCP Server

**Target application**: `hello-world` in `default` namespace (or any ArgoCD-managed rollout)  
**Related**: [WORKFLOW_JOURNEYS.md](WORKFLOW_JOURNEYS.md) § Workflow 4, [PROMPT_REFERENCE.md](PROMPT_REFERENCE.md)

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Environment Setup](#2-environment-setup)
3. [What Gets Ignored](#3-what-gets-ignored)
4. [Test Scenarios](#4-test-scenarios)
5. [Natural Language Prompts](#5-natural-language-prompts)
6. [Quick Reference: Tool → Prompt Mapping](#6-quick-reference-tool--prompt-mapping)
7. [Troubleshooting](#7-troubleshooting)

---

## 1. Prerequisites

| Component | Status |
|-----------|--------|
| Argo CD | Installed and managing your application |
| Argo Rollouts | Installed in cluster |
| Argo Rollout MCP Server | Running (Docker recommended: `talkopsai/argo-rollout-mcp-server:latest`) |
| hello-world Rollout | Onboarded and optionally managed by Argo CD |

---

## 2. Environment Setup

### Verify Argo CD Application

```bash
argocd app get hello-world  # or your app name
argocd app list
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

## 3. What Gets Ignored

The tool generates `ignoreDifferences` for runtime fields that Argo Rollouts mutates:

| Resource | Paths Ignored | Purpose |
|----------|---------------|---------|
| TraefikService | `/spec/weighted/services` | Weight changes during canary steps |
| Rollout | `/status` | Phase, replica counts, conditions |
| Rollout | `/spec/strategy/canary/trafficRouting`, `/spec/strategy/blueGreen/trafficRouting` | MCP-patched trafficRouting (optional) |
| AnalysisRun | `/status` | Analysis run status |
| Deployment | `/spec/replicas` | workloadRef only: Rollout scale-down of referenced Deployment |

---

## 4. Test Scenarios

### Scenario A: Generate ignoreDifferences for Standard Rollout

| Step | Action | Prompt / Tool |
|------|--------|----------------|
| 1 | Generate | "Generate ArgoCD ignoreDifferences for hello-world in default, including rollout status, analysis runs, and Traefik service." |
| 2 | Or use tool | `generate_argocd_ignore_differences(include_traefik_service=True, include_rollout_status=True, include_analysis_run=True)` |
| 3 | Copy output | Copy `ignore_differences_yaml` from response |
| 4 | Add to Application | Paste into `Application.spec.ignoreDifferences` |
| 5 | Sync | `argocd app sync hello-world` or sync via UI |

---

### Scenario B: Generate for workloadRef (include_deployment_replicas)

When using workloadRef migration, Argo CD may revert the Rollout's scale-down of the referenced Deployment.

| Step | Action | Prompt / Tool |
|------|--------|----------------|
| 1 | Generate | "Generate ArgoCD ignoreDifferences for hello-world in default with include_deployment_replicas for workloadRef." |
| 2 | Or use tool | `generate_argocd_ignore_differences(include_deployment_replicas=True, deployment_name="hello-world")` |
| 3 | Add to Application | Paste output into `Application.spec.ignoreDifferences` |

---

### Scenario C: Include trafficRouting (ArgoCD/Helm-Managed Rollout)

When the Rollout is managed by Argo CD or Helm and you patch trafficRouting via MCP, sync may revert it.

| Step | Action | Prompt / Tool |
|------|--------|----------------|
| 1 | Generate | Use tool with `include_rollout_traffic_routing=True` |
| 2 | Or use tool | `generate_argocd_ignore_differences(include_rollout_traffic_routing=True)` |
| 3 | Add to Application | Paste output into `Application.spec.ignoreDifferences` |

---

### Scenario D: Verify ArgoCD Sync Status

| Step | Action | Prompt / Tool |
|------|--------|----------------|
| 1 | Check sync | `argocd app get hello-world` or Argo CD UI |
| 2 | Trigger rollout | "Deploy hello-world:v2 to the hello-world rollout in default." |
| 3 | Verify no OutOfSync | Argo CD should not show OutOfSync from Rollout status or TraefikService weights |

---

## 5. Natural Language Prompts

Copy-paste these prompts into your MCP client (Cursor, Claude, etc.).

### Standard Rollout

```
Generate the ArgoCD ignoreDifferences configuration for hello-world in default — include Rollout status and AnalysisRun fields.
```

```
Generate ignoreDifferences for hello-world in default with include_traefik_service — so Argo CD doesn't revert when Argo Rollouts updates TraefikService weights.
```

```
Create the ArgoCD ignoreDifferences snippet for hello-world in default — include Rollout status, AnalysisRun, and TraefikService if using external traffic routing.
```

### workloadRef

```
Generate ArgoCD ignoreDifferences for hello-world in default with include_deployment_replicas for workloadRef — so Argo CD doesn't revert the Rollout's scale-down of the referenced Deployment.
```

### Full Options

```
Generate ignoreDifferences YAML for my ArgoCD app hello-world in default to prevent OutOfSync when Argo Rollouts updates status at runtime. Include rollout status, AnalysisRun, TraefikService, and deployment replicas for workloadRef.
```

---

## 6. Quick Reference: Tool → Prompt Mapping

| Tool | Example Prompt |
|------|----------------|
| `generate_argocd_ignore_differences` | "Generate ArgoCD ignoreDifferences for hello-world in default, including rollout status, analysis runs, and Traefik service." |
| `generate_argocd_ignore_differences` (workloadRef) | "Generate ArgoCD ignoreDifferences for hello-world in default with include_deployment_replicas for workloadRef." |
| `generate_argocd_ignore_differences` (trafficRouting) | Use `include_rollout_traffic_routing=True` when Rollout is ArgoCD/Helm-managed and trafficRouting is MCP-patched |

### Tool Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `include_traefik_service` | `true` | Include TraefikService weight paths |
| `include_rollout_status` | `true` | Include Rollout status paths |
| `include_rollout_traffic_routing` | `false` | Include trafficRouting so MCP patches persist |
| `include_analysis_run` | `false` | Include AnalysisRun status paths |
| `include_deployment_replicas` | `false` | workloadRef: Ignore Deployment spec.replicas |
| `deployment_name` | (optional) | Scopes Deployment ignore when `include_deployment_replicas=True` |
| `traefik_api_group` | `"traefik.io"` | Use `traefik.containo.us` for Traefik v2 |

---

## 7. Troubleshooting

| Issue | Check |
|-------|-------|
| ArgoCD still OutOfSync | Ensure `ignoreDifferences` is in `Application.spec`, not a separate resource. Verify paths match your resources. |
| TraefikService weights reverted | Add `include_traefik_service=True`. For Traefik v2, use `traefik_api_group="traefik.containo.us"`. |
| trafficRouting patch reverted on sync | Add `include_rollout_traffic_routing=True`. Or add trafficRouting to your Helm chart/ArgoCD source. |
| Deployment replicas reverted (workloadRef) | Add `include_deployment_replicas=True` and `deployment_name="hello-world"`. |
| Wrong API group for Traefik | Traefik v3: `traefik.io`. Traefik v2: `traefik.containo.us`. |
