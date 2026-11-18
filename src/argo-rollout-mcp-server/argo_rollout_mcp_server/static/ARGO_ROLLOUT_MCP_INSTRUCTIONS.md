# Argo Rollout MCP Server — Execution Plane Instructions

You are connected to the **Argo Rollout MCP Server** (`v0.2.0`), the live Kubernetes execution plane for **Argo Rollouts** progressive delivery.

## Architectural Contract
- **Execution Only**: This MCP server exposes live cluster state (`resources`) and cluster-mutating/diagnostic operations (`tools`).
- **Read-Only by Default**: Write tools are disabled unless started with `--allow-write` or `MCP_ALLOW_WRITE=true`. Check `argorollout://server/capabilities` first.
- **Dry-Run Previews**: Structural mutations (`argo_create_rollout`, `argo_convert_deployment_to_rollout`, `argo_convert_rollout_to_deployment`, `argo_configure_rollout_strategy`, `argo_configure_analysis_template`, `argo_manage_legacy_deployment`) default to `dry_run=True`. Review the returned manifest before calling with `dry_run=False`.
- **Destructive Confirmations**: Destructive operations require interactive MCP elicitation or `confirm=True` after user approval.

## Toolsets (15 Tools Max, `<= 8` Parameters Each)
- **`rollouts`**: `argo_create_rollout`, `argo_set_rollout_image`, `argo_configure_rollout_strategy`, `argo_manage_rollout_lifecycle`, `argo_delete_rollout`
- **`migration`**: `argo_validate_deployment_readiness` (read-only), `argo_convert_deployment_to_rollout`, `argo_convert_rollout_to_deployment`, `argo_manage_legacy_deployment`
- **`analysis`**: `argo_configure_analysis_template`, `argo_delete_analysis_template`, `argo_create_experiment`, `argo_delete_experiment`, `argo_compare_canary_metrics` (read-only)
- **`diagnostics`**: `argo_diagnose_rollout` (read-only)

## Resources (13 Live Cluster Resources)
- `argorollout://server/capabilities` — Write mode, enabled toolsets, CRD availability, Prometheus URL
- `argorollout://cluster/contexts` — Active and available kubeconfig contexts
- `argorollout://cluster/health` — Cluster node readiness and capacity
- `argorollout://cluster/namespaces` — Cluster namespaces
- `argorollout://rollouts/list` — All rollouts with `healthScore` (0–100), phase, strategy, and replicas
- `argorollout://rollouts/{namespace}/{name}/detail` — Concise rollout status, step, weights, hashes, pause/abort state, and conditions
- `argorollout://rollouts/{namespace}/{name}/manifest` — Sanitized YAML manifest (redacts literal env values and strips `managedFields`)
- `argorollout://rollouts/{namespace}/{name}/analysisruns` — 5 most recent AnalysisRuns and failing metrics
- `argorollout://analysistemplates/{namespace}` — Namespace `AnalysisTemplate`s and `ClusterAnalysisTemplate`s
- `argorollout://experiments/{namespace}/{name}/status` — Experiment status
- `argorollout://history/{namespace}/{deployment}` — ReplicaSet revision history and status conditions
- `argorollout://metrics/{namespace}/{service}/summary` — Real Prometheus service metrics (or explicit `unavailable` status)
- `argorollout://metrics/prometheus/status` — Prometheus connectivity status
