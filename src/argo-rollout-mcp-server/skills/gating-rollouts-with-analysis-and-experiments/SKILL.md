---
name: gating-rollouts-with-analysis-and-experiments
description: Configures Prometheus-backed AnalysisTemplates, ClusterAnalysisTemplates, and ephemeral Argo Experiments to automatically gate canary and blue-green rollouts on error-rate and latency SLOs. Use when attaching automated Prometheus metric analysis to a Rollout, running side-by-side baseline vs. canary Experiments, or comparing live canary metrics against stable.
---

# Gating Rollouts with Analysis and Experiments

## Preconditions

1. Read `argorollout://server/capabilities` to verify `crds_installed.analysis_template`, `crds_installed.experiment`, and `allow_write`.
2. Read `argorollout://metrics/prometheus/status` to verify Prometheus is reachable (`status == "available"`) before attaching Prometheus-backed `AnalysisTemplate` gates.
3. Read `argorollout://analysistemplates/{namespace}` to check whether a suitable namespace `AnalysisTemplate` or `ClusterAnalysisTemplate` already exists.
4. For `[GATE]` steps: always preview with `dry_run=True` first (`argo_configure_analysis_template`, `argo_create_experiment`); if the operator's prompt already explicitly directs applying, launching, or deleting the resource on the cluster and pre-checks pass (`allow_write == true`), proceed immediately with `dry_run=False` (or `confirm=True` for `argo_delete_analysis_template` / `argo_delete_experiment`)—otherwise stop after the preview and ask for approval.

## Workflow A: Attaching Automated Prometheus Analysis to a Rollout

- [ ] **Step 1 — Inspect Target Rollout Strategy**:
  Read `argorollout://rollouts/{namespace}/{name}/detail` to determine whether the Rollout uses `canary` or `bluegreen` strategy.
  - Note: Blue-green `prePromotionAnalysis` requires finite metric `count` (e.g., `count: 3`) so the `AnalysisRun` terminates and unblocks promotion.
- [ ] **Step 2 — Preview `AnalysisTemplate` (`dry_run=True`)**:
  Call `argo_configure_analysis_template(rollout_name, namespace, template_name, metrics, thresholds, scope, dry_run=True)` (or run `scripts/generate_analysis_template.py` and `scripts/validate_analysis_template.py` offline). Consult [references/prometheus-analysis-queries.md](references/prometheus-analysis-queries.md) for PromQL conventions.
- [ ] **Step 3 — `[GATE]` Apply and Link `AnalysisTemplate` (`dry_run=False`)**:
  After user review of the previewed YAML and thresholds, call `argo_configure_analysis_template(..., dry_run=False)` to create the `AnalysisTemplate`/`ClusterAnalysisTemplate` and wire it into the Rollout (`spec.strategy.canary.analysis` or `spec.strategy.blueGreen.prePromotionAnalysis`).
- [ ] **Step 4 — Monitor `AnalysisRun` Execution (and Decommission Unused Templates)**:
  During a rollout, read `argorollout://rollouts/{namespace}/{name}/analysisruns` and call `argo_compare_canary_metrics(rollout_name, namespace, window="5m")`. When retiring an obsolete `AnalysisTemplate` or `ClusterAnalysisTemplate` (after detaching it from any Rollouts), `[GATE]` confirm with the user and call `argo_delete_analysis_template(name, namespace, scope="namespace"|"cluster", confirm=True)`.

## Workflow B: Running a Side-by-Side Argo Experiment

- [ ] **Step 1 — Verify Rollout Has Active Canary/Preview ReplicaSet**:
  Consult [references/experiment-design.md](references/experiment-design.md). When using `specRef: "canary"` or `specRef: "preview"`, ensure a rollout is in progress (`currentPodHash != stableRS` in `argorollout://rollouts/{namespace}/{name}/detail`).
- [ ] **Step 2 — Preview Experiment (`dry_run=True`)**:
  Call `argo_create_experiment(name, templates, namespace, duration="20m", analyses=..., rollout_name=..., dry_run=True)`.
- [ ] **Step 3 — `[GATE]` Launch Experiment (`dry_run=False`)**:
  Call `argo_create_experiment(..., dry_run=False)` and poll `argorollout://experiments/{namespace}/{name}/status` until `phase` reaches `Successful` or `Failed`.
- [ ] **Step 4 — `[GATE]` Clean Up Completed Experiment**:
  When finished, call `argo_delete_experiment(name, namespace, confirm=True)` to remove ephemeral ReplicaSets.

## Bundled References & Offline Scripts

- [references/prometheus-analysis-queries.md](references/prometheus-analysis-queries.md) — PromQL templates for HTTP 5xx error rate, P95/P99 latency, and `successCondition` rules.
- [references/experiment-design.md](references/experiment-design.md) — `specRef` resolution (`stable`/`canary`/`active`/`preview`) and Traefik routing limitations.
- `scripts/generate_analysis_template.py` — Offline `AnalysisTemplate` / `ClusterAnalysisTemplate` YAML generator.
- `scripts/validate_analysis_template.py` — Offline linter checking `count`, `interval`, `failureLimit`, and `NaN`-safe `successCondition`.
