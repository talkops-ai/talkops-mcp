---
name: progressing-argo-rollouts
description: Executes and manages Canary, Blue-Green, Rolling, and multi-cluster wave deployments on Argo Rollouts, including image updates, step progression, traffic routing (Traefik and Gateway API), pause/resume, promotion, and rollback abort. Use when creating a new Rollout, deploying a new container image, promoting or aborting a canary or blue-green deployment, or configuring traffic routing weights.
---

# Progressing Argo Rollouts

## Preconditions

1. Read `argorollout://server/capabilities` to verify `cluster_connected`, `allow_write`, and `crds_installed.rollout`.
2. Read `argorollout://rollouts/{namespace}/{name}/detail` (or `argorollout://rollouts/list`) to inspect the current `phase`, `strategy`, `currentStep`, `canaryWeight`, `paused`, and `healthScore`.
3. Select the strategy playbook in [references/strategy-playbooks.md](references/strategy-playbooks.md):
   - **Canary** (`strategy="canary"`): Gradual traffic shifting (e.g., `5% -> 25% -> 50% -> 100%`) with pause/analysis gates.
   - **Blue-Green** (`strategy="bluegreen"`): Full preview environment verification on `{name}-preview` before atomic cutover to `{name}-active`.
   - **Rolling** (`strategy="rolling"`): Pod-by-pod replacement without canary steps.
   - **Multi-Cluster Waves**: Consult [references/multi-cluster-waves.md](references/multi-cluster-waves.md) when coordinating sequential regional rollouts across multiple MCP server instances.
4. For `[GATE]` steps: always preview strategy/rollout changes with `dry_run=True` first (`argo_configure_rollout_strategy`, `argo_create_rollout`); if the operator's prompt already explicitly directs executing the live rollout change, promotion, pause/resume, or abort and `allow_write == true`, proceed immediately with `dry_run=False` (and `confirm=True` for `promote_full` or `abort`) and verify post-action Rollout state—otherwise stop after preview/inspection and request confirmation.

## Canary Progression Workflow

- [ ] **Step 1 — Inspect Baseline State**:
  Read `argorollout://rollouts/{namespace}/{name}/detail` and confirm the Rollout is `Healthy` before starting a new release.
- [ ] **Step 2 — Configure Strategy or Traffic Routing (Optional)**:
  If canary steps or Traefik/Gateway API routing need adjustment, consult [references/traffic-routing.md](references/traffic-routing.md) (or generate steps with `scripts/render_canary_steps.py`), preview via `argo_configure_rollout_strategy(..., dry_run=True)`, and `[GATE]` apply with `dry_run=False`.
- [ ] **Step 3 — `[GATE]` Trigger Image Release**:
  Call `argo_set_rollout_image(name, image, namespace, container_name)` to start the canary cycle.
- [ ] **Step 4 — Monitor Step Progression & Compare Metrics**:
  Read `argorollout://rollouts/{namespace}/{name}/detail` until `paused == true` at the current canary weight. Call `argo_compare_canary_metrics(rollout_name=name, namespace=namespace, window="5m")` to compare error rate, P95, and P99 latency between `{name}-stable` and `{name}-canary`.
- [ ] **Step 5 — Promote or Abort**:
  - If metrics are healthy (`recommendation == "promote"`): call `argo_manage_rollout_lifecycle(name, action="promote", namespace)` to advance to the next step.
  - `[GATE]` To skip all remaining steps to 100%: require user approval and call `argo_manage_rollout_lifecycle(name, action="promote_full", namespace, confirm=True)`.
  - `[GATE]` If metrics degrade (`recommendation == "abort"`): immediately rollback via `argo_manage_rollout_lifecycle(name, action="abort", namespace, confirm=True)`.

## Blue-Green Cutover Workflow

- [ ] **Step 1 — `[GATE]` Update Image**:
  Call `argo_set_rollout_image(name, image, namespace)` to spin up the preview ReplicaSet behind `{name}-preview`.
- [ ] **Step 2 — Verify Preview Environment**:
  Read `argorollout://rollouts/{namespace}/{name}/detail` and `argorollout://metrics/{namespace}/{name}-preview/summary` while the Rollout is paused awaiting cutover.
- [ ] **Step 3 — `[GATE]` Cut Over or Abort**:
  - Promote traffic to the new active ReplicaSet: `argo_manage_rollout_lifecycle(name, action="promote", namespace)`.
  - Abort and scale down preview ReplicaSet: `argo_manage_rollout_lifecycle(name, action="abort", namespace, confirm=True)`.

## Bundled References & Offline Scripts

- [references/strategy-playbooks.md](references/strategy-playbooks.md) — Canary, Blue-Green, Rolling, and Cost-Conscious (`setCanaryScale`) playbooks.
- [references/traffic-routing.md](references/traffic-routing.md) — `TraefikService` and Kubernetes Gateway API `HTTPRoute` integration.
- [references/multi-cluster-waves.md](references/multi-cluster-waves.md) — Multi-cluster wave rollout orchestration across per-cluster MCP server entries.
- `scripts/render_canary_steps.py` — Deterministic canary step array generator (`conservative`, `standard`, `fast`, `cost-optimized`).
