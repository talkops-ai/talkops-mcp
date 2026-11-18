---
name: operating-tempo-deployments-and-tenants
description: Operates Grafana Tempo Kubernetes custom resources (`TempoStack` and `TempoMonolithic` `tempo.grafana.com/v1alpha1`), conducts production readiness reviews, and manages per-tenant runtime `/api/overrides` with HTTP `ETag` (`If-Match` / `412 Precondition Failed`) optimistic concurrency control. Use when sizing or applying Tempo Operator deployments (`dev`, `small-prod`, `large-prod`), tuning `ingestion_rate_limit_bytes`, `ingestion_burst_size_bytes`, `max_bytes_per_trace`, or `block_retention`, or enabling per-tenant `metrics_generator.processors`. Do not use for live Tempo ring/ingestion outage diagnosis (use diagnosing-tempo-ingestion-and-health), `LokiStack` operations (use operating-loki-deployments-and-ingestion), or OTel Collector provisioning (use provisioning-opentelemetry-collectors).
---

# Operating Tempo Deployments and Tenants

## Preconditions & Safety Guardrails

- Read `tempo://server/capabilities` and `tempo://deployment/overview` via MCP resources first to verify whether `allow_write` is enabled (`MCP_ALLOW_WRITE`) and which toolsets (`overrides`, `operator`) are active.
- **Read-Only Mode (`allow_write: false`)**: When `tempo://server/capabilities` reports `allow_write: false`, do NOT invoke mutating tools (`tempo_patch_tenant_overrides`, `tempo_apply_operator_cr`); inspect live state via read-only MCP resources/scripts and emit a complete copy-pasteable GitOps YAML / JSON `merge_patch` plan.
- **Zero-Secret Hygiene (`hooks/secret-safety.py`)**: NEVER dump Kubernetes `Secret` payloads (`kubectl get secret ... -o yaml/jsonpath`) and NEVER embed inline S3/GCS/Azure access keys, secret keys, SAS tokens, or connection strings inside manifests or tool calls. Always reference storage credentials exclusively via `spec.storage.secret: {name: <secret-name>, type: s3|gcs|azure}` (or workload identity / IRSA).

## Workflow A: Per-Tenant Runtime `/api/overrides` Management

- [ ] **Step 1 — Read Current Tenant Overrides & ETag**: Read `tempo://overrides/{backend_id}/{tenant}` via MCP resources to obtain the current override payload and concurrency `etag`.
- [ ] **Step 2 — Validate & Compose Override Merge Patch**:
  - Consult [overrides-cookbook.md](references/overrides-cookbook.md) and run `scripts/build_overrides_patch.py` to compute `ingestion_rate_limit_bytes`, `ingestion_burst_size_bytes`, `max_bytes_per_trace`, `max_traces_per_user`, `block_retention`, and `metrics_generator.processors` (`["service-graphs", "span-metrics", "local-blocks"]`).
  - **Burst Ratio Guardrail**: Refuse to apply `ingestion_burst_size_bytes < ingestion_rate_limit_bytes`; explain the token-bucket anti-pattern, adjust `ingestion_burst_size_bytes` to `>= 1.5 * ingestion_rate_limit_bytes` via `scripts/build_overrides_patch.py`, and always preview the corrected patch via `tempo_patch_tenant_overrides(..., expected_etag=<etag>, dry_run=True)` without mutating live (`dry_run=False`).
- [ ] **Step 3 — Execute Dry-Run Diff First**: Call `tempo_patch_tenant_overrides(..., expected_etag=<etag>, dry_run=True)` to preview the merged payload and unified `diff` without modifying the server.
- [ ] **Step 4 — Handle ETag Conflicts (`412 Precondition Failed`) & Confirm Live Apply**: `[GATE]`
  - If an `expected_etag` conflict (`412 Precondition Failed`) occurs because another operator updated `/api/overrides` concurrently, NEVER strip `expected_etag` to force a blind overwrite—re-read `tempo://overrides/{backend_id}/{tenant}` to inspect the concurrent changes and obtain the fresh `etag`, re-merge your intended fields preserving peer updates, and re-run `tempo_patch_tenant_overrides(..., expected_etag=<fresh_etag>, dry_run=True)`.
  - Only when explicitly approved by the user, execute `tempo_patch_tenant_overrides(..., expected_etag=<etag>, dry_run=False, confirm=True)`.

## Workflow B: Kubernetes Tempo Operator (`TempoStack` / `TempoMonolithic`) Management

- [ ] **Step 1 — Inspect Existing CRs, Manifests & CRD Schema via MCP Resources**:
  - Read `tempo://operator/crs/{namespace}` to list existing `TempoStack` and `TempoMonolithic` custom resources (do not shell out to raw `kubectl get`).
  - Read `tempo://operator/manifests/{kind}/{namespace}/{name}` before modifying any existing CR so existing `spec` fields (`storage`, `replicationFactor`, `template`) are preserved. During production readiness audits ([production-checklist.md](references/production-checklist.md)), run `tempo_get_diagnostics` and explicitly audit all five checklist pillars: (1) durable object storage (`s3`/`gcs`/`azure`), (2) `replicationFactor >= 2`, (3) `vParquet4` block encoding & Tempo 3.x Kafka partition lag (`< 5s` or 2.x N/A), (4) `multitenancy_enabled` & `X-Scope-OrgID` tenant isolation, and (5) per-tenant override burst headroom (`>= 1.5x`) & `metrics_generator.processors` (`service-graphs`, `span-metrics`, `local-blocks`).
  - Read `tempo://operator/crd-schema/{kind}` (`TempoStack` or `TempoMonolithic`) to verify supported `tempo.grafana.com/v1alpha1` schema fields in the cluster.
- [ ] **Step 2 — Enforce Storage Durability & Render Target Manifest**:
  - **Production Object-Storage Gate**: Refuse to apply `inMemory` or missing durable object storage (`s3`, `gcs`, `azure`) live on production `TempoStack` deployments; explain pod-restart data loss and distributed querier/ingester/compactor block-sharing requirements, then immediately render a corrected durable `spec.storage.secret` manifest via `scripts/render_tempo_operator_cr.py` (using an existing cluster storage secret from `observability`, e.g. `tempo-otel-s3-credentials`) and validate the corrected manifest via `tempo_apply_operator_cr(..., dry_run=True)` only (never `dry_run=False`).
  - Select a profile from [operator-profiles.md](references/operator-profiles.md) (`dev` `TempoMonolithic` `< 1 MB/s` `72h`; `small-prod` `TempoStack` `1–10 MB/s`, `replicationFactor: 2`, `336h`; `large-prod` `TempoStack` `10–50+ MB/s`, `replicationFactor: 3`, `720h`) and run `scripts/render_tempo_operator_cr.py`.
- [ ] **Step 3 — Execute Server-Side Dry-Run Validation**: Call `tempo_apply_operator_cr(manifest=..., dry_run=True)` to validate against the Kubernetes API server (`server_dry_run_validated == True`) and generate a unified `diff`.
- [ ] **Step 4 — Confirm Live Cluster Apply**: `[GATE]` Review the unified `diff` (and storage growth impact when extending retention). Only when the prompt explicitly requests live application, call `tempo_apply_operator_cr(manifest=..., dry_run=False, confirm=True)`; otherwise pause after `dry_run=True`.

## References & Offline Scripts

- `TempoStack` & `TempoMonolithic` sizing profiles (`dev`, `small-prod`, `large-prod`): [operator-profiles.md](references/operator-profiles.md)
- Per-tenant `/api/overrides` tuning cookbook: [overrides-cookbook.md](references/overrides-cookbook.md)
- Production readiness checklist for Tempo 2.x/3.x: [production-checklist.md](references/production-checklist.md)
- Offline Tempo Operator CR manifest renderer: `scripts/render_tempo_operator_cr.py`
- Offline `/api/overrides` JSON patch builder: `scripts/build_overrides_patch.py`
