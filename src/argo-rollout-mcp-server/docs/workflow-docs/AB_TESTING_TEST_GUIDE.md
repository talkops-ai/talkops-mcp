# A/B Testing Test Guide — Experiments with Argo Rollout MCP Server

**Target application**: `hello-world` in `default` namespace  
**Prerequisite**: Onboarded canary rollout with AnalysisTemplate (see [ONBOARDING_TEST_GUIDE.md](ONBOARDING_TEST_GUIDE.md))  
**Related**: [WORKFLOW_JOURNEYS.md](WORKFLOW_JOURNEYS.md) § Workflow 3, [PROMPT_REFERENCE.md](PROMPT_REFERENCE.md)

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Environment Setup](#2-environment-setup)
3. [Experiment Phases](#3-experiment-phases)
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
| hello-world Rollout | Canary strategy, onboarded in `default` namespace |
| AnalysisTemplate | Exists for hello-world (see [ONBOARDING_TEST_GUIDE.md](ONBOARDING_TEST_GUIDE.md) for setup) |
| Prometheus | Required for analysis-backed experiments |

> **Note**: Experiments create separate ReplicaSets for metric comparison. Weighted traffic routing for experiments depends on your ingress (Traefik, Istio, SMI, ALB). **Traefik does not support experiment traffic routing** — use experiments for metrics comparison only (experiment-as-analysis pattern).

---

## 2. Environment Setup

### Verify hello-world Rollout and Canary

```bash
kubectl get rollout hello-world -n default
kubectl get analysistemplate -n default
```

### Ensure Canary Deployment in Progress

For experiments that use `specRef: "stable"` and `specRef: "canary"`, the rollout must have a canary deployment in progress:

```bash
# Trigger a new version first
# "Deploy hello-world:v2 to the hello-world rollout in default."
# Then create the experiment while canary is running
```

> **specRef resolution**: When using `specRef` in templates, the MCP server resolves stable/canary (or active/preview for blue-green) from the Rollout's ReplicaSets. You must pass `rollout_name` (and optionally `rollout_namespace` if different from the experiment namespace) so the server can fetch the correct pod templates. See [EXPERIMENT_SPECREF_FIX_PROPOSAL.md](../EXPERIMENT_SPECREF_FIX_PROPOSAL.md).

### Start MCP Server (Docker — recommended)

```bash
docker run --rm -it \
  -p 8768:8768 \
  -v ~/.kube:/app/.kube:ro \
  -e K8S_KUBECONFIG=/app/.kube/config \
  talkopsai/argo-rollout-mcp-server:latest
```

### Resource for Monitoring

| Resource | Purpose |
|----------|---------|
| `argorollout://experiments/default/hello-world-ab-test/status` | Experiment phase, template statuses, analysis results |

---

## 3. Experiment Phases

| Phase | Meaning |
|-------|---------|
| `Pending` | Experiment created, pods not yet ready |
| `Running` | Both templates running, analysis in progress |
| `Successful` | All analysis passed, experiment complete |
| `Failed` | Analysis failed or pods unhealthy |
| `Error` | Configuration issue |

---

## 4. Test Scenarios

### Scenario A: Create Experiment (Baseline + Candidate)

Run two versions side-by-side for metric comparison. Templates reference the rollout's stable and canary ReplicaSets.

| Step | Action | Prompt / Tool |
|------|--------|----------------|
| 1 | Trigger canary (if not already) | "Deploy hello-world:v2 to the hello-world rollout in default." |
| 2 | Create experiment | "Create an A/B test experiment called hello-world-ab-test in default — run baseline (stable) and candidate (canary) side by side for 30 minutes." |
| 3 | Or use tool | `argo_create_experiment(name="hello-world-ab-test", namespace="default", templates=[{"name": "baseline", "specRef": "stable"}, {"name": "candidate", "specRef": "canary"}], duration="30m", rollout_name="hello-world", analyses=[{"name": "success-rate", "templateName": "hello-world-analysis"}])` |

**Notes**:
- `rollout_name` is **required** when templates use `specRef` — the server resolves stable/canary from the Rollout's ReplicaSets.
- Replace `hello-world-analysis` with your actual AnalysisTemplate name from onboarding.

---

### Scenario B: Monitor Experiment Status

| Step | Action | Prompt / Tool |
|------|--------|----------------|
| 1 | Poll status | "What is the status of the hello-world-ab-test experiment in default?" |
| 2 | Or fetch resource | `argorollout://experiments/default/hello-world-ab-test/status` |
| 3 | Review | Check `template_statuses` and `analysis_runs` in response |

---

### Scenario C: Promote Candidate to Production (If Wins)

| Step | Action | Prompt / Tool |
|------|--------|----------------|
| 1 | Promote candidate | "Deploy hello-world:v2 to the hello-world rollout in default." (if not already) + "Fully promote the hello-world rollout in default." |
| 2 | Or use tool | `argo_update_rollout(update_type='image', name="hello-world", new_image="hello-world:v2", namespace="default")` then `argo_manage_rollout_lifecycle(action='promote_full', ...)` |
| 3 | Delete experiment | "Delete the hello-world-ab-test experiment in default." |

---

### Scenario D: Clean Up Experiment (If Baseline Wins)

| Step | Action | Prompt / Tool |
|------|--------|----------------|
| 1 | Abort rollout | "Abort the hello-world rollout in default." |
| 2 | Delete experiment | "Delete the hello-world-ab-test experiment in default." |
| 3 | Or use tool | `argo_delete_experiment(name="hello-world-ab-test", namespace="default")` |

---

### Scenario E: Inconclusive — Extend Duration or Manual Review

| Step | Action | Prompt / Tool |
|------|--------|----------------|
| 1 | Review analysis | Fetch `argorollout://experiments/default/hello-world-ab-test/status` |
| 2 | Manual decision | Extend experiment duration (re-create with longer `duration`) or manually promote/abort based on metrics |

---

## 5. Natural Language Prompts

Copy-paste these prompts into your MCP client (Cursor, Claude, etc.).

### Create Experiment

```
Create an A/B test experiment called "hello-world-ab-test" in "default" — run "baseline" (stable) and "candidate" (canary) side by side for 30 minutes. Use rollout "hello-world" for specRef resolution.
```

```
Start an Argo Experiment named "hello-world-ab-test" in "default" with two templates: baseline (stable spec) and candidate (canary spec), running for 1 hour. Resolve specRef from rollout "hello-world".
```

> When using specRef, the MCP client must pass `rollout_name="hello-world"` to `argo_create_experiment` so the server can resolve stable/canary from the Rollout's ReplicaSets.

### Monitor

```
What is the status of the "hello-world-ab-test" experiment in "default"?
```

```
Show me the analysis results for the "hello-world-ab-test" experiment in "default".
```

### Clean Up

```
Delete the "hello-world-ab-test" experiment in "default" — the baseline won, keeping stable.
```

```
Clean up the "hello-world-ab-test" experiment in "default".
```

---

## 6. Quick Reference: Tool → Prompt Mapping

| Tool | Example Prompt |
|------|----------------|
| `argo_create_experiment` | "Create an A/B test experiment called hello-world-ab-test in default — run baseline and candidate side by side for 30 minutes." |
| `argo_delete_experiment` | "Delete the hello-world-ab-test experiment in default." |
| `argorollout://experiments/default/hello-world-ab-test/status` | "What is the status of the hello-world-ab-test experiment in default?" |
| `argo_update_rollout` (image) | "Deploy hello-world:v2 to the hello-world rollout in default." (promote candidate) |
| `argo_manage_rollout_lifecycle` (abort) | "Abort the hello-world rollout in default." (keep baseline) |

---

## 7. Troubleshooting

| Issue | Check |
|-------|-------|
| Experiment stuck in Pending | Verify rollout has canary in progress. Check pod status: `kubectl get pods -n default -l app=hello-world` |
| AnalysisTemplate not found | Ensure AnalysisTemplate exists and `templateName` in `analyses` matches. See [ONBOARDING_TEST_GUIDE.md](ONBOARDING_TEST_GUIDE.md). |
| specRef "stable"/"canary" invalid | Pass `rollout_name` when using specRef (required). Ensure the Rollout has a canary deployment in progress — trigger `argo_update_rollout(update_type='image')` first. |
| Traefik traffic routing | Traefik does not support experiment traffic routing. Use experiments for metrics comparison only; configure ingress separately for user-facing A/B tests. |
| Experiment Failed | Check AnalysisRun status: `kubectl get analysisruns -n default`. Verify Prometheus queries return data. |
