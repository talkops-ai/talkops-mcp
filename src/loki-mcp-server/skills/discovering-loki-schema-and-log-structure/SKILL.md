---
name: discovering-loki-schema-and-log-structure
description: Discovers Grafana Loki indexed stream labels, scoped label values, active stream combinations, Loki 3.x detected fields/structured metadata, OTLP log mappings, Promtail unpack envelopes, and repeating log patterns to infer optimal LogQL parsers. Use when exploring an unfamiliar Loki cluster or tenant, onboarding services, locating OTLP resource/log attributes, or inferring pattern/logfmt/json/unpack/regexp parsers for raw log lines. Do not use for executing LogQL analytics or A2UI charts (use authoring-logql-and-analyzing-logs), auditing stream cardinality FinOps (use optimizing-loki-cardinality-and-finops), incident triage (use triaging-loki-incidents-and-errors), or Tempo trace attribute discovery (use authoring-traceql-and-metrics-queries).
license: Apache-2.0
metadata:
  author: TalkOps
  version: "0.2.0"
  domain: observability
  service: grafana-loki
---

# Discovering Loki Schema and Log Structure

Use this skill to systematically map out an unfamiliar Grafana Loki 3.x environment—from indexed TSDB labels down to chunk-header structured metadata, Promtail `pack` envelopes, and recurring `<_>` log templates—without guessing field names or running blind regex scans.

## Progressive 6-Step Schema Discovery Funnel

Always narrow from macro index metadata down to micro log structure via Loki MCP resources and tools (passing explicit `org_id` whenever inspecting specific tenants):

1. **Cluster Capabilities & Cached Labels**:
   - Read `loki://server/capabilities` and `loki://schema/labels` first to check Loki server version, `allow_write`, and whether Loki 3.x `/detected_fields` and `/patterns` endpoints are supported.
   - If operating against a legacy Loki 2.x backend (or if `/detected_fields` / `/patterns` are disabled), skip Steps 5–6, run Steps 2–4, sample `<= 10` bounded lines via `loki_query_range(..., max_log_lines=10)`, and pass a sample line to `infer_log_parser.py`.
2. **Indexed Label Names (`loki_get_labels`)**:
   - Call `loki_get_labels(start="now-6h", org_id=...)` to list active TSDB-indexed stream labels (`service_name`, `service_namespace`, `namespace`, `cluster`, `job`, `app`, `env`).
   - When comparing multiple tenants, call `loki_get_labels` separately per `org_id`.
3. **Scoped Label Values (`loki_get_label_values`)**:
   - Call `loki_get_label_values(label="service_name", query='{namespace="<namespace>"}', start="now-3h")` using the `query` parameter to scope values to the target namespace rather than scanning cluster-wide.
4. **Active Stream Combinations (`loki_get_series`)**:
   - Call `loki_get_series(match='{service_name="<service>", namespace="<namespace>"}')` to inspect exact indexed label sets and stream counts before querying logs.
5. **Detected Fields, Structured Metadata & Envelopes (`loki_get_detected_fields`)**:
   - Consult [references/structured-metadata-and-otlp.md](references/structured-metadata-and-otlp.md) and call `loki_get_detected_fields(query='{service_name="<service>", namespace="<namespace>"}', start="now-1h")`:
     - **Loki 3.x Native OTLP (`/otlp/v1/logs`) 3-Tier Model**: `service.name` / `service.namespace` map to indexed `{service_name, service_namespace}`; high-cardinality attributes (`k8s.pod.name` / `k8s_pod_name`, `k8s.container.name`, `trace_id`, `span_id`, `severity_text`) land in **Structured Metadata** (`parsers: null` / `""`), so `{k8s_pod_name="..."}` returns `0` streams—filter them **after** `{}` via `| k8s.pod.name="..." | trace_id="..."` without `| json`!
     - **Promtail `pack` Envelope (`_entry`)**: If detected fields show `_entry` alongside packed labels (`pod`), recommend `| unpack` first (so `_entry` becomes the log line) before `| logfmt` or `| json`, and recommend migrating packed `pod` labels to Loki 3.x `structured_metadata`.
     - **Duplicate Label Collisions (`_extracted`)**: When a parsed JSON/logfmt key (`service_name`) collides with an indexed stream label (`service_name`), Loki renames the parsed key to `service_name_extracted`; alias explicitly (`| json downstream_service="service_name"`).
6. **Log Volume & Structural Templates (`loki_get_log_patterns`)**:
   - Consult [references/pattern-parser-and-extraction-guide.md](references/pattern-parser-and-extraction-guide.md) and call `loki_get_log_patterns(query='{service_name="<service>", namespace="<namespace>"}', start="now-1h")`.
   - Convert dominant `<_>` templates into fast `| pattern "..."` extractors by naming only needed tokens (`<method>`, `<path>`, `<status>`, `<duration_ms>`) while keeping unused tokens as `<_>`.
   - **Always prefer `| pattern` as the primary recommendation** on fixed anchor literals, and always explain why `| pattern` outperforms `| regexp` by **`5–10x`** on high-volume logs (single-pass byte scan with zero per-line Go RE2 state allocation). Present Go RE2 `(?P<name>...)` `| regexp` (preceded by a literal `|=` filter) strictly as a secondary fallback when variable multi-space padding or optional tokens occur.

## Inferring Optimal LogQL Parsers Locally

Always run [scripts/infer_log_parser.py](scripts/infer_log_parser.py) when given sample log lines (Envoy, Nginx, Kubernetes `klog`, JSON, `logfmt`, or unstructured Java/Go text) to apply the speed hierarchy (`| pattern` `1x` > `| logfmt` `~1.5x` > targeted `| json` `~2–3x` > Go RE2 `| regexp` `5–10x` preceded by literal `|=`):
```bash
python3 .agents/skills/discovering-loki-schema-and-log-structure/scripts/infer_log_parser.py \
  --sample '[2026-06-01T10:00:00.123Z] "POST /v1/orders HTTP/2" 200 - 512 1024 42 40 "-" "grpc-go/1.64"' --json
```

## Key Reference Guides & Scripts

- [references/structured-metadata-and-otlp.md](references/structured-metadata-and-otlp.md) — Loki 3.x 3-tier storage model and native `/otlp/v1/logs` mapping (`service_name` indexed vs. `trace_id`, `k8s.pod.name`, `severity_text` structured metadata).
- [references/pattern-parser-and-extraction-guide.md](references/pattern-parser-and-extraction-guide.md) — Parser speed matrix (`pattern`, `logfmt`, `json`, `regexp`, `unpack`) and templates for Envoy, Nginx, Kubernetes `klog`, and Go/Java logs.
- [scripts/infer_log_parser.py](scripts/infer_log_parser.py) — Deterministic log format detector outputting optimal LogQL parser expressions.
