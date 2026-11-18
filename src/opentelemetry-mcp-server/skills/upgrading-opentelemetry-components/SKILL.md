---
name: upgrading-opentelemetry-components
description: Safely upgrades OpenTelemetry Collector versions, migrates deprecated collector YAML syntax (logging exporter, memory_ballast extension, opencensus, loki exporter, and legacy internal telemetry address), aligns HTTP semantic conventions, and upgrades Operator CRDs (v1alpha1 to v1beta1 for OpenTelemetryCollector and TargetAllocator compatibility) with instant rollback protection. Use when upgrading Collector images, auditing config deprecations before an Operator upgrade, ordering Gateway-before-Agent rollouts, or rolling back failed upgrades. Do not use for greenfield collector provisioning (use provisioning-opentelemetry-collectors), runtime queue saturation triage (use troubleshooting-telemetry-pipelines), Helm application release upgrades, or Argo Rollouts workload migrations.
---

# Upgrading OpenTelemetry Components

## Preconditions

- Read `otel://server/capabilities` via MCP resources (preferring MCP over raw `kubectl` CLI commands) to verify write permissions (`allow_write`) and active toolsets.
- Read `otel://operator/status`, `otel://collector/{namespace}/{name}`, `otel://collector/{namespace}/{name}/config`, `otel://collector/{namespace}/{name}/history`, and `otel://target-allocator/{namespace}/{name}` (or call `otel_survey_cluster` for fleet inventories) to inspect current Operator version, Collector image tag, TargetAllocator settings, and CRD schema versions (`v1alpha1` vs `v1beta1`).

## Component Upgrade & Migration Workflow Checklist

- [ ] **Step 1 — Scan Collector Configuration for Breaking Changes**:
  - Read `otel://collector/{namespace}/{name}/config` to retrieve the live Collector YAML.
  - Run `scripts/check_config_deprecations.py --file config.yaml` offline to detect removed or deprecated syntax across Collector `v0.100`–`v0.152+` (`logging` exporter, `memory_ballast` extension, `service.telemetry.metrics.address`, `opencensus`).
  - Consult `references/collector-breaking-changes.md` and `references/operator-crd-migration.md`.
- [ ] **Step 2 — Validate Upgraded Configuration (`otel_validate_collector_config`)**:
  - Call `otel_validate_collector_config` (`namespace`, `name`, `config_yaml`, `checks=["pipeline", "order", "security", "deprecations"]`, `target_version="0.152.1"`) to verify that the migrated configuration passes all structural, processor-order, deprecation, and security lint rules (`valid: true`).
- [ ] **Step 3 — Preview Upgrade & Config Patch (`dry_run=True`)**:
  - Call `otel_patch_collector` (`namespace`, `name`, `config_yaml`, `workload_options={"image": "otel/opentelemetry-collector-contrib:0.152.1"}`, `dry_run=True`).
  - Verify that the `otel.mcp/last-known-good` rollback snapshot will be preserved automatically.
  - `[GATE]` Present the deprecation report, target image version, unified diff, and GitOps status (`GITOPS_MANAGED`) to the user for confirmation.
- [ ] **Step 4 — Apply Upgrade & Verify Runtime Stability**:
  - Re-run `otel_patch_collector` with `dry_run=False, confirm=True`.
  - Call `otel_diagnose_collector` (`namespace`, `name`, `include=["status", "pods", "logs", "metrics"]`) to confirm the upgraded pods reach `Running` phase with zero startup errors.
  - If the upgraded collector enters `CrashLoopBackOff` (`RT_POD_CRASHLOOP`), inspect `otel://collector/{namespace}/{name}/history`, preview rollback via `otel_revert_collector_config(namespace=..., name=..., dry_run=True)`, and `[GATE]` execute `otel_revert_collector_config(..., dry_run=False, confirm=True)` to restore the last-known-good snapshot.

## Reference & Script Inventory

- `references/collector-breaking-changes.md` — Migration guide for OpenTelemetry Collector `v0.100` through `v0.152+` breaking changes and semantic convention stabilization.
- `references/operator-crd-migration.md` — Migration guide from `opentelemetry.io/v1alpha1` to `opentelemetry.io/v1beta1` for `OpenTelemetryCollector` and `TargetAllocator` CRDs.
- `scripts/check_config_deprecations.py` — Offline scanner that detects removed/deprecated Collector components and outputs replacement YAML snippets.
