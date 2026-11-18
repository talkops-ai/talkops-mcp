---
name: controlling-telemetry-cardinality-and-noise
description: Configures OTTL transform, filter, k8sattributes, and redaction processors on OpenTelemetry Collectors to drop noisy healthcheck endpoints, parse structured JSON logs, scrub PII and sensitive credentials in-flight, and normalize high-cardinality URL paths and metric attributes. Use when observability costs spike, PII or tokens leak in logs or spans, or high-cardinality attributes overload Prometheus or OTLP backends. Do not use for trace tail sampling or spanmetrics connectors (use tuning-sampling-and-trace-derived-metrics), Prometheus ServiceMonitor metricRelabelings (use optimizing-tsdb-cardinality-and-finops), Loki or Alloy indexed label governance and Bloom filters (use optimizing-loki-cardinality-and-finops), or RBAC and container security compliance audits (use auditing-observability-security-posture).
---

# Controlling Telemetry Cardinality and Noise

## Preconditions

- Read `otel://server/capabilities` via MCP resources (never raw `kubectl` CLI commands when MCP is connected) to verify write permissions (`allow_write`) and enabled `pipeline` toolset.
- Read `otel://collector/{namespace}/{name}/config`, `otel://logs-profile/{namespace}/{collector}`, and `otel://k8s-enrichment/{namespace}/{collector}` to inspect existing `transform`, `filter`, `redaction`, and `k8sattributes` enrichment processors and pipeline ordering.

## Processor Ordering Invariant (`memory_limiter` -> `transform`/`filter` -> `batch`)

Always enforce `[memory_limiter, k8sattributes, transform/*, filter/*, batch]` and explain both failure modes whenever reviewing or fixing pipeline processor order:
- **`transform` before `memory_limiter` (OOMKill Risk)**: Running OTTL `ParseJSON`/regex allocations before `memory_limiter` allows traffic bursts to exhaust Go heap memory and `OOMKill` the collector pod before backpressure triggers.
- **`filter` after `batch` (Under-Filled / Fragmented Batches)**: Running `filter` *after* `batch` wastes CPU assembling batches only to strip spans/logs out afterward, emitting tiny under-filled, fragmented export batches to downstream backends.

## Cardinality & Noise Reduction Workflow Checklist

- [ ] **Step 1 — Audit Existing Signal Processing, Enrichment & PII Posture**:
  - Read `otel://k8s-enrichment/{namespace}/{collector}` and `otel://logs-profile/{namespace}/{collector}` to inspect extracted pod metadata/labels, JSON parsing, severity mapping, and trace-context correlation (`trace_id`, `span_id`).
  - Call `otel_audit_security_posture` (`namespace`) when checking pipelines for unredacted secrets or PII exposure.
- [ ] **Step 2 — Design OTTL Transform, Filter & Redaction Rules**:
  - Consult `references/ottl-cookbook.md` for verified OTTL syntax across `span`, `spanevent`, `metric`, `datapoint`, and `log` contexts.
  - Consult `references/pii-patterns-and-compliance.md` for GDPR/PCI/HIPAA regex scrubbing patterns (emails, SSNs, credit cards, JWTs, API keys).
  - Consult `references/metric-cardinality-playbooks.md` for dropping high-cardinality attributes (`http.target`, `url.query`, `user.id`, `container.id`).
  - Run `scripts/render_ottl_statements.py` offline when custom composite OTTL statements are required.
- [ ] **Step 3 — Preview Processing Pipeline Changes (`dry_run=True`)**:
  - Always use `otel_configure_processing` (`namespace`, `collector_name`, `signals=["logs", "traces", "metrics"]`, `rules={"parse_json": True, "mask_pii": ["email", "credit_card", "ssn", "jwt", "bearer_token", "url_query_secrets"], "custom_mask_rules": [...], "drop_attributes": [...], "drop_noise_paths": ["/healthz", "/readyz", "/metrics"], "preserve_errors": True, "filter_conditions": {...}, "ottl_statements": [...]}`, `target_pipelines=[...]`, `dry_run=True`) to preview OTTL `transform` and `filter` rules (including `"url_query_secrets"` / `(?i)([?&](?:api_key|access_token|code|secret)=)[^&\s"']+` for URL query secret scrubbing, `http.request.header.x_api_key`/`authorization`/`cookie` + `http.response.header.set_cookie` header deletion, and status-aware probe filtering via `preserve_errors=True`).
  - `[GATE]` Present the unified config diff, explicitly confirming **`error_mode: ignore`** on every `transform`/`filter` processor and strict processor ordering (`memory_limiter` first to prevent OOM before regex/JSON parsing, `transform`/`filter` in the middle, `batch` last so `filter` never creates under-filled fragmented batches after batching).
- [ ] **Step 4 — Apply & Verify Telemetry Reduction**:
  - Re-run `otel_configure_processing` with `dry_run=False`.
  - Verify `error_mode: ignore` and pipeline ordering in `otel://collector/{namespace}/{name}/config`, and call `otel_diagnose_collector` (`namespace`, `name`, `include=["metrics", "config_lint"]`) to confirm zero processor syntax errors and healthy throughput.

## Reference & Script Inventory

- `references/ottl-cookbook.md` — Verified OpenTelemetry Transformation Language (OTTL) expressions for spans, metrics, and logs.
- `references/pii-patterns-and-compliance.md` — Standard PII/PCI/secret regex patterns and `redaction` vs. `transform` processor strategies.
- `references/metric-cardinality-playbooks.md` — Strategies for capping Prometheus/OTLP series explosion via attribute deletion and URL path normalization.
- `scripts/render_ottl_statements.py` — Offline generator for `transform` and `filter` processor YAML blocks.
