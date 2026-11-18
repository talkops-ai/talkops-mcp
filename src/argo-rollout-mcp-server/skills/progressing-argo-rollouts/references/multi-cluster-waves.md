# Multi-Cluster Wave Rollouts

## Architecture: One MCP Server Instance per Cluster

As configured in `mcp.json`, multi-cluster progressive delivery runs one `argo-rollout-mcp-server` instance per Kubernetes cluster context (for example, `argo-rollout-us-west` and `argo-rollout-eu-central`), each bound to its own `--context` and `--prometheus-url`.

## Wave Progression Playbook

- [ ] **Wave 0 — Pre-Flight Verification Across All Clusters**:
  1. Read `argorollout://cluster/contexts` and `argorollout://server/capabilities` on each cluster server instance.
  2. Confirm `argorollout://rollouts/{namespace}/{name}/detail` reports `phase == "Healthy"` in every target region.
- [ ] **Wave 1 — Canary Cluster (Lowest Blast Radius Region)**:
  1. `[GATE]` Call `argo_set_rollout_image(name, image, namespace)` on the Wave 1 cluster server only.
  2. Progress through canary steps (`5% -> 25% -> 50% -> 100%`) using `argo_compare_canary_metrics` and `argo_manage_rollout_lifecycle(action="promote")`.
  3. Bake at 100% (`phase == "Healthy"`) for at least 10 minutes before starting Wave 2.
- [ ] **Wave 2+ — Primary Production Clusters**:
  1. `[GATE]` Trigger `argo_set_rollout_image(name, image, namespace)` on the next regional cluster server.
  2. If any cluster reports `ANALYSIS_RUN_FAILED` or `recommendation == "abort"`, immediately abort the active wave (`argo_manage_rollout_lifecycle(action="abort", confirm=True)`) and halt subsequent waves.
