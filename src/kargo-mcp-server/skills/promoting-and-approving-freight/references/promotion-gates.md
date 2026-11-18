# Promotion Gates & Verification Reference (Kargo v1.12)

## Table of Contents
1. [Freight Eligibility Rules](#freight-eligibility-rules)
2. [Availability Strategy & Soak Time](#availability-strategy--soak-time)
3. [Auto-Promotion & Selection Policy](#auto-promotion--selection-policy)
4. [Stage Verification with AnalysisTemplates](#stage-verification-with-analysistemplates)

## Freight Eligibility Rules

A `Stage` defines one or more `requestedFreight` entries in `Stage.spec.requestedFreight`. Each entry specifies:
- `origin`: `{kind: "Warehouse", name: "<warehouse-name>"}`
- `sources`:
  - `direct: true`: Freight can be promoted directly from the Warehouse without passing through an upstream stage.
  - `stages: ["dev", "qa"]`: Freight must be verified in upstream stages (unless manually approved for the target stage via `kargo_approve_freight`).

Use `kargo_trace_freight` to evaluate whether a specific Freight satisfies a stage's `requestedFreight` rules.

## Availability Strategy & Soak Time

Inside `requestedFreight[*].sources`:
- `availabilityStrategy`:
  - `OneOf` (default): Freight is eligible once verified in **any** listed upstream stage.
  - `All`: Freight must be verified in **every** listed upstream stage (fan-in gate).
- `requiredSoakTime`: Duration string (e.g., `"1h0m0s"`, `"30m0s"`) that Freight must remain continuously verified in upstream stages before becoming eligible for downstream promotion.
- `autoPromotionOptions`:
  - `selectionPolicy: NewestFreight` (default): Promotes the newest eligible Freight from the origin Warehouse.
  - `selectionPolicy: MatchUpstream`: Promotes the exact Freight currently deployed in the upstream stage.

## Auto-Promotion & Selection Policy

Auto-promotion is enabled per stage inside `ProjectConfig.spec.promotionPolicies` (inspect via `kargo://projects/{project}` and update via `kargo_apply_project_config`), while `autoPromotionOptions.selectionPolicy` (`NewestFreight` or `MatchUpstream`) is configured per source inside `Stage.spec.requestedFreight[*].sources.autoPromotionOptions`:

```yaml
apiVersion: kargo.akuity.io/v1alpha1
kind: ProjectConfig
metadata:
  name: my-project
  namespace: my-project
spec:
  promotionPolicies:
    - stageSelector:
        name: dev
      autoPromotionEnabled: true
```

In Kargo v1.11+, manually promoting an older Freight (rollback) places a hold in `Stage.status.autoPromotionHolds`. Clear the hold by promoting by origin warehouse: `kargo_promote(project=..., stage=..., origin_warehouse=...)`.

## Stage Verification with AnalysisTemplates

Stages can run Argo Rollouts `AnalysisTemplate` checks after every promotion:
1. Create or update an `AnalysisTemplate` via `kargo_apply_analysis_template`.
2. Attach `verification={"analysisTemplates": [{"name": "smoke-test"}]}` to the Stage via `kargo_apply_stage`.
3. Inspect the resulting `AnalysisRun` via `kargo://projects/{project}/analysis-runs/{run}` and `kargo://projects/{project}/analysis-runs/{run}/logs`.
4. Trigger re-verification (`kargo_manage_verification(action="reverify", ...)`) or abort an active run (`kargo_manage_verification(action="abort", ..., confirm=True)`).
