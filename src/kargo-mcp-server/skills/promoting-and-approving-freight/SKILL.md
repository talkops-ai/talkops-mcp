---
name: promoting-and-approving-freight
description: Evaluates freight eligibility, approves freight for restricted stages, triggers stage or downstream promotions, manages freight aliases or unused freight deletion, aborts hung promotions, and manages verification gates in Kargo v1.12 pipelines. Use when promoting artifacts to a stage, approving freight for production, promoting downstream subscribers, tagging or deleting freight, aborting active promotions, or re-running stage verification. Do not use for Kargo RBAC role/OIDC permission grants, stage rollbacks, or initial pipeline creation.
---

# Promoting and Approving Freight

Operational workflow for advancing `Freight` bundles across Kargo `Stage` DAGs, granting manual stage approvals, promoting downstream subscribers, and managing post-promotion `AnalysisRun` verifications.

## Preconditions

1. Read `kargo://server/capabilities` to verify `allow_write: true` and confirm `promotion` and `verification` toolsets are active.
2. Read `kargo://projects/{project}/pipeline` to inspect stage topology, upstream relationships, and currently deployed Freight (and read `kargo://projects/{project}/stages/{stage}` and `kargo://projects/{project}/stages/{stage}/manifest` via Kargo MCP resources rather than raw `kubectl` whenever inspecting Stage details or Stage YAML manifests).
3. Consult [references/promotion-gates.md](references/promotion-gates.md) for upstream verification rules (`availabilityStrategy`, `requiredSoakTime`, `selectionPolicy`) and `AnalysisTemplate` verification gates.

## Promotion & Approval Checklist

- [ ] **Step 1: Inspect Pipeline & Candidate Freight**
  - Read `kargo://projects/{project}/pipeline` and run `kargo_query_freight(project=..., stage=..., available_only=True)` to identify candidate Freight IDs or human-readable aliases (`angry-bird`). Use `kargo_manage_freight(project=..., action="set_alias"|"create"|"delete", ...)` when tagging a release alias, assembling manual Freight, or pruning unused Freight (`confirm=True`).
  - Run `kargo_trace_freight(project=..., freight_or_alias=...)` to inspect `currentlyIn`, `verifiedIn`, `approvedFor`, and any upstream blockers.
- [ ] **Step 2: Approve Freight When Upstream Gate Requires Manual Bypass (`[GATE]`)**
  - If `kargo_trace_freight` reports that the target stage requires upstream verification that has not completed (or the stage is a manual approval gate), verify artifact contents via `kargo://projects/{project}/freight/{freight_or_alias}`.
  - `[GATE]` If the operator explicitly instructed approving the Freight in their request, call `kargo_approve_freight(project=..., freight_or_alias=..., stage=..., confirm=True)`; otherwise request explicit operator approval before bypassing upstream gates.
- [ ] **Step 3: Promote Freight to Target Stage (`[GATE]`)**
  - Preview the promotion plan first with `dry_run=True`. `[GATE]` If the operator asked for a preview/plan only (or target/scope is ambiguous), stop and present the preview; when the operator explicitly requested live promotion, proceed immediately to execute:
    - **Single Stage**: `kargo_promote(project=..., stage=..., freight=... | freight_alias=..., downstream=False, dry_run=False)`
    - **Downstream Subscribers**: `kargo_promote(project=..., stage=..., freight=... | freight_alias=..., downstream=True, dry_run=False, confirm=True)`
    - **Latest from Warehouse (also clears v1.11+ auto-promotion holds)**: `kargo_promote(project=..., stage=..., origin_warehouse=..., dry_run=False)`
- [ ] **Step 4: Monitor Promotion Execution**
  - Read `kargo://projects/{project}/promotions` and `kargo://projects/{project}/promotions/{promotion}` (or `kargo://projects/{project}/stages/{stage}`) to monitor `status.phase` (`Pending` -> `Running` -> `Succeeded` | `Failed` | `Errored`). Wake a waiting promotion via `kargo_manage_promotion(action="refresh", project=..., promotion=...)` or `kargo_refresh(project=..., kind="promotion", name=...)`.
  - If a running promotion must be stopped, `[GATE]` confirm with the operator (or proceed directly when explicitly instructed to abort) and call `kargo_manage_promotion(action="abort", project=..., promotion=..., confirm=True)`.
- [ ] **Step 5: Configure & Verify Post-Promotion AnalysisRuns**
  - Read `kargo://projects/{project}/analysis-templates` and create or update `AnalysisTemplate` / `ClusterAnalysisTemplate` gates with `kargo_apply_analysis_template(project=..., name=..., spec=..., kind=..., dry_run=True)` followed by `dry_run=False` when live application is requested.
  - If the stage configures `verification.analysisTemplates`, inspect `kargo://projects/{project}/analysis-runs/{run}` and `kargo://projects/{project}/analysis-runs/{run}/logs`.
  - Use `kargo_manage_verification(action="reverify"|"abort"|"delete_template", project=..., stage=..., template_name=..., confirm=True)` to re-run flaky verification, abort a stuck verification run, or delete an obsolete template (`[GATE]` confirm before `abort` or `delete_template` unless explicitly instructed).
