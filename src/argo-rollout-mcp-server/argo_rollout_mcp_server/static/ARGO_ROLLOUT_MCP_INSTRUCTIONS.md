# Argo Rollout MCP Server — Instructions

You are interacting with the **Argo Rollout MCP Server**, a specialized MCP server for **progressive delivery** using Argo Rollouts on Kubernetes.

## Capabilities

### Tools (13)
- **Rollout Management**: Create, delete, update rollouts (`argo_create_rollout`, `argo_delete_rollout`, `argo_update_rollout` with update_type: image, strategy, traffic_routing, workload_ref)
- **Rollout Operations**: Promote, abort, pause, resume rollouts (`argo_manage_rollout_lifecycle` with action: promote, promote_full, pause, resume, abort, skip_analysis)
- **Analysis**: Configure analysis templates (`argo_configure_analysis_template` with mode=execute or generate_yaml)
- **Experiments**: A/B testing (`argo_create_experiment`, `argo_delete_experiment`)
- **Generators**: Convert Deployments to Rollouts, validate, generate services (`validate_deployment_ready`, `convert_deployment_to_rollout` including mode=`generate_services_only`, `convert_rollout_to_deployment`, `argo_manage_legacy_deployment`, `create_stable_canary_services` (legacy), `generate_argocd_ignore_differences`)
- **Orchestration** (future enhancement): `orch_*` tools excluded this release — mockup implementations

### Resources (11)
- `argorollout://rollouts/list` — All rollouts overview
- `argorollout://rollouts/{ns}/{name}/detail` — Rollout status detail
- `argorollout://experiments/{ns}/{name}/status` — Experiment status
- `argorollout://health/summary` — Cluster health
- `argorollout://health/{ns}/{name}/details` — Per-app health
- `argorollout://metrics/{namespace}/{service}/summary` — Prometheus bounds mapping
- `argorollout://metrics/prometheus/status` — Prometheus endpoint validation
- `argorollout://history/{ns}/{deployment}` — Deployment history
- `argorollout://history/all` — All history
- `argorollout://cluster/health` — Cluster capacity
- `argorollout://cluster/namespaces` — Namespace listing

### Prompts (6)
- `onboard_application_guided` — Convert Deployment → Rollout
- `canary_deployment_guided` — Progressive canary deployment
- `blue_green_deployment_guided` — Blue-green deployment
- `rolling_update_guided` — Standard rolling update
- `multi_cluster_canary_guided` — Multi-region deployment
- `cost_optimized_deployment_guided` — Budget-aware deployment

