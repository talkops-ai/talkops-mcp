# Argo Rollout MCP Server — Natural Language Prompt Reference

**For every tool and resource call documented in [WORKFLOW_JOURNEYS.md](WORKFLOW_JOURNEYS.md), this guide provides ready-to-use natural language prompts you can give to an AI agent.**

Copy any prompt below exactly or adapt it for your app name, namespace, and image.

> **Design**: Read-only context (list rollouts, status, health, metrics) uses **resources** (`argorollout://...`). State-changing actions (create, update, delete, promote, abort) use **tools**.

---

## Workflow 1: Onboarding an Existing Application

### Step 1 — Validate readiness (structural + Service selector)

> **Tool**: `validate_deployment_ready`  
> Unified pre-flight check: validates Deployment structure (selector, template, containers, replicas, limits, probes) and Service selector compatibility (no `pod-template-hash`). Single call for full migration readiness.

```
Check if my "hello-world" deployment in the "default" namespace is ready to migrate to Argo Rollouts.
```
```
Run a readiness check on deployment "api-service" in namespace "production" before converting it to a rollout.
```
```
Validate the "frontend" deployment in "staging" — does it meet all requirements for Argo Rollouts onboarding?
```

---

### Step 2 — Convert Deployment → Rollout (primary onboarding path)

> **Tool**: `convert_deployment_to_rollout`  
> This is the correct tool for onboarding an **existing** app. It auto-fetches the Deployment from the cluster, preserves all config (resource limits, probes, env vars), auto-discovers the existing Service's port and selector by matching the Deployment's pod labels, and with `apply=True` creates the Rollout CRD + stable/canary Services in a single call — no port information needed.

```
Convert the "api-service" deployment in "production" to a canary Argo Rollout and apply it to the cluster.
```
```
Migrate "hello-world" in "default" to an Argo Rollout using canary strategy — apply everything to the cluster now.
```
```
Convert "frontend" deployment in "staging" to a blue-green Argo Rollout and apply it.
```
```
Convert "api-service" in "production" to a canary rollout using workloadRef mode (no pod duplication), scale down on success, apply=True.
```
```
Convert "api-service" in "production" to a canary rollout — give me the YAML for review first, don't apply yet.
```
```
Convert "api-service" in "production" to a canary rollout and apply, but override the service port to 8080 instead of auto-discovering it.
```

> **For brand-new apps** (no existing Deployment to migrate from): use `argo_create_rollout` instead.  
> `Create a new canary Argo Rollout "payment-service" in "production" with image "payment:v1" on port 8080.`

> **Services only** (no conversion): use `convert_deployment_to_rollout(mode='generate_services_only', app_name='...', apply=True)` to create stable+canary (or active+preview for bluegreen) Services without converting a Deployment.

---

### Step 3 — Link Rollout to traffic routing (optional, canary only)

> **Tool**: `argo_update_rollout` (update_type='traffic_routing')  
> **Canary strategy only.** Links the Rollout to an existing weighted traffic service (e.g., TraefikService, Gateway API HTTPRoute, Istio VirtualService). The traffic service must be created separately via your ingress controller or CI/CD. Without this, the Argo Rollouts controller shifts traffic via replica counts only.  
> ⚠️ **Blue-green** does not use this — it flips the `activeService` selector on promotion. **Rolling** uses standard K8s mechanics.  
> **Gateway API** (Traefik 3.x, Envoy Gateway): use `gateway_api_config={"httpRoute": "my-route", "namespace": "default"}` instead of `traefik_service_name`.

```
Link the "hello-world" rollout in "default" to TraefikService "hello-service-route-wrr".
```
```
Set trafficRouting on "api-service" rollout in "production" to use TraefikService "api-service-route-wrr".
```
```
Connect "frontend" rollout in "staging" to its weighted traffic service "frontend-route-wrr" for canary weight shifting.
```
```
Remove the trafficRouting from "frontend" rollout in "staging" (clear_routing=True).
```
```
Link the "api-service" rollout in "production" to Gateway API HTTPRoute "api-http-route" in namespace "default" (gateway_api_config={"httpRoute": "api-http-route", "namespace": "default"}).
```

---

### Step 4 — Configure automated analysis (optional)

> **Tool**: `argo_configure_analysis_template` (mode='execute')

```
Set up automated Prometheus analysis for the "api-service" rollout in "production" with Prometheus at "http://prometheus:9090". Abort if error rate exceeds 5% or P99 latency exceeds 2 seconds.
```
```
Configure analysis for my "hello-world" rollout using Prometheus at "http://prometheus.monitoring:9090".
```
```
Add automated health checks to the "api-service" rollout — link it to Prometheus so failing canaries auto-rollback.
```

---

## Workflow 2: Deploying a New Version

### Update the image (trigger rollout)

> **Tool**: `argo_update_rollout` (update_type='image')

```
Deploy "api-service:v2.0" to the "api-service" rollout in "production".
```
```
Update the "frontend" rollout in "staging" to image "frontend:2.1.0".
```
```
Roll out a new version of "checkout" — new image is "checkout:1.6-hotfix" in "production".
```

---

### Update canary strategy (steps, canaryService)

> **Tool**: `argo_update_rollout` (update_type='strategy')  
> Patches `canaryService`, `stableService`, or `canary_steps` on an existing canary Rollout. Creates the canary Service automatically if `canaryService` is a new name.

```
Update the "canary-demo" rollout in "canary-demo" namespace to use canaryService "canary-demo-preview" and steps: 20% → pause → 40% → pause 10s → 60% → pause 10s → 80% → pause 10s.
```
```
Change the canary steps on "api-service" rollout in "production" to: setWeight 10, pause, setWeight 25, pause 5m, setWeight 50, pause, setWeight 100.
```
```
Update "canary-demo" rollout strategy — use canaryService "canary-demo-preview", service port 8080.
```

> **Advanced canary steps**: `canary_steps` also supports `setCanaryScale` (requires trafficRouting; e.g. `{"setCanaryScale": {"replicas": 1}}` for cost savings), and `analysis` (inline AnalysisTemplate; `templateName` must reference an existing template). See `argo_create_rollout` docstring for full examples.

---

### Check rollout details

> **Resource**: `argorollout://rollouts/{namespace}/{name}/detail`  
> Read-only context — returns rollout details (phase, replicas, conditions) plus full YAML manifest.

```
What's the current status of the "api-service" rollout in "production"?
```
```
Show me the status of the "hello-world" rollout in "default" namespace.
```
```
Is my "frontend" rollout healthy? Check the status in "staging".
```
```
Give me the live status of the "api-service" rollout in "production".
```

---

### List all rollouts

> **Resource**: `argorollout://rollouts/list`  
> Read-only context — cluster-wide overview of all rollouts.

```
Show me an overview of all rollouts in my cluster.
```
```
List all Argo Rollouts across namespaces.
```
```
What rollouts do I have? Fetch the rollouts list.
```

---

### Manage rollout lifecycle (promote, pause, resume, abort)

> **Tool**: `argo_manage_rollout_lifecycle`  
> Unified tool for rollout lifecycle actions. Use `action` parameter: `promote`, `promote_full`, `pause`, `resume`, `abort`, `skip_analysis`.

```
Promote "api-service" rollout in "production" to the next step.
```
```
Skip all remaining steps and promote "api-service" rollout fully to 100%.
```
```
Pause the "api-service" rollout in "production" — hold at current traffic level.
```
```
Resume the paused "api-service" rollout in "production".
```
```
Abort the "api-service" rollout in "production" and roll back to stable.
```
```
Something is wrong with the canary — roll back "frontend" rollout in "staging" immediately.
```
```
Advance the "frontend" canary rollout to the next stage in "staging".
```

---

### Rollout history

> **Resource**: `argorollout://history/{namespace}/{deployment}`

```
Show me the deployment revision history for "api-service" rollout in "production" including previous images.
```
```
What are the last rollout history entries and replica set hashes for "frontend" in "staging"?
```

---

### Orchestration tools (future enhancement)

Policy validation, cost checks, deployment insights, and intelligent promotion (`orch_*` tools) are excluded from this release. Use `argorollout://cluster/health` and `argorollout://rollouts/{ns}/{name}/detail` for cluster and rollout status.

---

## Workflow 3: A/B Testing with Experiments

### Create an experiment

> **Tool**: `argo_create_experiment`

```
Create an A/B test experiment called "api-ab-test" in "production" — run "baseline" (stable) and "candidate" (canary) side by side for 30 minutes.
```
```
Start an Argo Experiment named "ui-experiment" in "staging" with two templates: control (stable spec) and variant (canary spec), running for 1 hour.
```

---

### Monitor experiment status

> **Resource**: `argorollout://experiments/{namespace}/{name}/status`

```
What is the status of the "api-ab-test" experiment in "production"?
```
```
Show me the analysis results for the "ui-experiment" experiment in "staging".
```

---

### Clean up experiment

> **Tool**: `argo_delete_experiment`

```
Delete the "api-ab-test" experiment in "production" — the baseline won, keeping stable.
```
```
Clean up the "ui-experiment" in "staging".
```

---

## Workflow 4: ArgoCD GitOps Integration

> **Tool**: `generate_argocd_ignore_differences`

```
Generate the ArgoCD ignoreDifferences configuration for "api-service" in "production" — include Rollout status and AnalysisRun fields.
```
```
Generate ignoreDifferences for "api-service" in "production" with include_deployment_replicas for workloadRef — so Argo CD doesn't revert the Rollout's scale-down of the referenced Deployment.
```
```
Generate ignoreDifferences YAML for my ArgoCD app "frontend" in "production" to prevent OutOfSync when Argo Rollouts updates status at runtime.
```
```
Create the ArgoCD ignoreDifferences snippet for "checkout" in "production" — include Rollout status, AnalysisRun, and optionally TraefikService if using external traffic routing.
```

---

## Workflow 5a: workloadRef Migration (Deployment → Rollout)

> **Tool**: `convert_deployment_to_rollout`

```
Convert the "api-service" deployment in "production" to an Argo Rollout using workloadRef mode — keep the existing Deployment running and scale it down only on success. Apply to cluster.
```

> **Tool**: `argo_update_rollout` (update_type='workload_ref')  
> Patches `spec.workloadRef.scaleDown` on an existing Rollout (`never` → `onsuccess` or `progressively`).

```
Change the workloadRef scaleDown on "api-service" rollout in "production" to progressively scale down the Deployment.
```
```
Update "frontend" rollout in "staging" — set workloadRef scaleDown to onsuccess so the Deployment scales down when the Rollout is healthy.
```

### Manage legacy Deployment (scale, delete, generate scale-down manifest)

> **Tool**: `argo_manage_legacy_deployment`  
> Unified tool for Deployment lifecycle during workloadRef migration. Use `action`: `scale_cluster`, `delete_cluster`, or `generate_scale_down_manifest`. For GitOps review-only, pass `deployment_yaml` when the Deployment is not yet live in the cluster.

```
Generate a scale-down manifest for the "api-service" deployment in "production" — I'll commit it to Git for Argo CD to apply.
```
```
Generate YAML to scale "frontend" deployment in "staging" to 0 replicas for GitOps.
```
```
Scale the "api-service" deployment in "production" to 0 replicas. (Only if NOT managed by Argo CD.)
```
```
Delete the "api-service" deployment in "production" — we've fully migrated to the Rollout. (Only if NOT managed by Argo CD.)
```

```
Convert deployment "frontend" in "staging" to a canary rollout using workload_ref migration mode with progressive scale-down. Apply directly.
```
```
Convert the "api-service" deployment in "production" to a blue-green rollout and apply it to the cluster.
```
```
Convert "api-service" to a canary rollout in "production" — show me the YAML first (apply=False), I'll review before applying.
```

---

## Workflow 5b: Reverse Migration — Rollout → Deployment

> **Tool**: `convert_rollout_to_deployment`

```
Convert the "api-service" Argo Rollout in "production" back to a standard Kubernetes Deployment with RollingUpdate strategy, 25% max surge.
```
```
I need to abandon Argo Rollouts for "frontend" — convert the rollout YAML back to a standard deployment.
```

> **Tool**: `argo_delete_rollout`

```
Delete the "api-service" Argo Rollout in "production" — we're reverting to standard Deployments.
```
```
Remove the "frontend" rollout in "staging" and all its associated services.
```

---

## Workflow 6: Zero-Downtime Migration (Argo CD)

> See [Zero-Downtime Migration from Kubernetes Deployment to Argo Rollouts under Argo CD](Zero-Downtime%20Migration%20from%20Kubernetes%20Deployment%20to%20Argo%20Rollouts%20under%20Argo%20CD.md) for the full guide. Use these prompts in sequence:

> **Validate → Convert (workloadRef) → ignoreDifferences → Patch scaleDown → Scale down via Git**

```
Run validate_deployment_ready for "api-service" in "production" before zero-downtime migration.
```
```
Generate ArgoCD ignoreDifferences for "api-service" in "production" with include_deployment_replicas so Argo CD won't revert the Rollout's scale-down of the Deployment.
```
```
Generate the Deployment scale-down YAML for "api-service" in "production" — I'll commit it to Git for Argo CD to apply after the Rollout is stable.
```

---

## General Monitoring

> **Resource**: `argorollout://health/summary`

```
Give me a health summary of the entire cluster.
```

> **Resource**: `argorollout://health/{namespace}/{name}/details`

```
Show health details for "api-service" in "production".
```

> **Resource**: `argorollout://metrics/{namespace}/{service}/summary`

```
Show performance metrics for "api-service" in "production".
```

> **Resource**: `argorollout://metrics/prometheus/status`

```
Is Prometheus connected and working for metrics collection?
```

> **Resource**: `argorollout://cluster/health`

```
What is the overall health and capacity of my Kubernetes cluster?
```

> **Resource**: `argorollout://cluster/namespaces`

```
List all namespaces in the cluster.
```

> **Resource**: `argorollout://history/{namespace}/{deployment}`

```
Show the deployment history for "api-service" in "production".
```

> **Resource**: `argorollout://history/all`

```
Show me all deployment history across the cluster.
```

---

## Guided Prompts (Full Workflow Automation)

These prompts trigger entire guided workflows — not individual tool calls.

| Say this | What happens |
|----------|-------------|
| `Onboard "api-service" in "production" to Argo Rollouts` | Triggers `onboard_application_guided` — full Step 1–5 walkthrough |
| `Guide me through a canary deployment of "api-service:v2" in "production"` | Triggers `canary_deployment_guided` — pre-flight → deploy → weight shifts → promote/abort |
| `Set up a blue-green deployment for "checkout" in "production"` | Triggers `blue_green_deployment_guided` — preview → analysis → switch |
| `Do a rolling update of "frontend" in "staging" to image "frontend:2.0"` | Triggers `rolling_update_guided` — validate → update → monitor |
| `Run an intelligent multi-cluster canary for "api-service:v2" across regions` | Triggers `multi_cluster_canary_guided` |
| `Deploy "api-service:v2" in "production" with cost optimization` | Triggers `cost_optimized_deployment_guided` |

---

## Emergency / Skip Analysis

> **Tool**: `argo_manage_rollout_lifecycle` with `action="skip_analysis"`

```
Emergency: skip the analysis step and promote "api-service" rollout in "production" — Prometheus is down but the version is verified healthy.
```
```
Override analysis and force-promote "frontend" rollout — manual validation has been completed.
```

> ⚠️ Use only when analysis metrics are unavailable but the version is confirmed healthy through other means.

---

*Document Version: 1.1 | Companion to [WORKFLOW_JOURNEYS.md](WORKFLOW_JOURNEYS.md)*
