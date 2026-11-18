---
name: onboarding-exporters-and-instrumentation
description: Selects, renders, deploys, verifies, and uninstalls Prometheus infrastructure exporters across the 20-exporter catalog (postgres_exporter, redis_exporter, kafka_exporter, blackbox_exporter, node_exporter, kube-state-metrics, nginx_exporter, jmx_exporter, mysqld_exporter, aws_cloudwatch_exporter, etc.) and guides Python/Go/Java/Node.js/Rust/.NET Prometheus SDK instrumentation with OpenMetrics trace exemplars. Use when deploying or removing a Prometheus exporter for databases/caches/brokers/nodes, rendering offline GitOps exporter manifests with DSN secret redaction, fixing Python multiprocess counters, or wiring OpenMetrics trace exemplars. Do not use when a workload already exposes /metrics and only needs a ServiceMonitor (use configuring-prometheus-scraping-and-discovery), for OTel Operator zero-code injection (use instrumenting-kubernetes-workloads), for Helm database chart installs (use deploying-helm-charts), or for OTel Collector provisioning (use provisioning-opentelemetry-collectors).
license: Apache-2.0
metadata:
  author: talkops
  version: "0.2.0"
  domain: observability
  component: prometheus
---

# Onboarding Exporters and Instrumentation

Guides both **infrastructure exporter lifecycle** (`Deployment`/`DaemonSet`/`sidecar` + `Service` + `ServiceMonitor` across all 20 supported exporters with `secretKeyRef` DSN safety) and **application SDK instrumentation** (including Python `PROMETHEUS_MULTIPROC_DIR` and OpenMetrics `traceID` exemplars). Never shell out to `kubectl` when MCP resources and tools are available. **Slash-Command Entrypoint**: Whenever the user request starts with `/setup-monitoring`, you MUST immediately read `commands/setup-monitoring.md` in the workspace root (`read_file`) before running tool calls so you execute the complete onboarding workflow.

## MCP Execution Primitives Used

- **Resources**:
  - `prom://topology/targets` — inspect active scrape jobs and verify zero stale `DOWN` targets remain after uninstalling an exporter.
  - `prom://kubernetes/scrape-crds` & `prom://kubernetes/manifests/{kind}/{namespace}/{name}` — check deployed `ServiceMonitor` CRDs and required operator selector labels.
  - `prom://audit/recent` — verify exporter install/uninstall `dry_run` and `succeeded` audit entries.
- **Tools (`exporter`, `scrape`, `query`, `rules` toolsets)**:
  - `prom_install_exporter` — deploy any of the 20 curated exporters (`postgres_exporter`, `redis_exporter`, `kafka_exporter`, `node_exporter`, `kube-state-metrics`, `blackbox_exporter`, `nginx_exporter`, `jmx_exporter`, `mysqld_exporter`, `mongodb_exporter`, `aws_cloudwatch_exporter`, etc.) with `secret_env` (`valueFrom.secretKeyRef`) and optional `ServiceMonitor` (`dry_run=True` default).
  - `prom_uninstall_exporter` — cleanly remove a managed exporter workload, `Service`, and `ServiceMonitor` (`dry_run=True` default).
  - `prom_verify_metrics_endpoint` — probe the exporter `/metrics` endpoint and poll Prometheus until `up == 1.0` (e.g. `pg_up == 1`).
  - `prom_query_exemplars` — verify whether OpenMetrics `traceID` exemplars are already being stored for instrumented services.
  - `prom_validate_rules` — validate starter exporter baseline alerting rules (`PostgresDown`, `PostgresTooManyConnections`, `BlackboxProbeFailed`, etc.).

## Step-by-Step Onboarding Workflow

### 1. Select Exporter Topology or Application SDK Pattern `[HIGH FREEDOM]`
1. **Infrastructure Exporters ([references/exporter-catalog.md](references/exporter-catalog.md))**:
   - Match workload topology carefully:
     - `daemonset`: `node_exporter` (`:9100`), `windows_exporter` (`:9182`) — one pod per node.
     - `deployment`: `kube-state-metrics` (`:8080`, requires `ClusterRole` RBAC — **never** run as a `DaemonSet`, which duplicates cluster object state per node!), `kafka_exporter` (`:9308`), `postgres_exporter` (`:9187`), `blackbox_exporter` (`:9115`, mounts `http_2xx` / `tcp_connect` ConfigMap paired with `Probe` CRDs), `aws_cloudwatch_exporter` (`:5000`, use IRSA `AWS_ROLE_ARN`, never static AWS keys).
     - `sidecar`: `nginx_exporter` (`:9113` scraping pod-local `127.0.0.1:<port>/stub_status`) and `jmx_exporter` (`:5556` attached to pod-local JVM/JMX) so per-pod `pod` and `instance` labels are preserved across replicas. **Even on conceptual/architectural questions, you MUST include a complete fenced `yaml` `PodMonitor` or `ServiceMonitor` manifest scoped to the user's namespace** (e.g., `namespace: otel-demo`) scraping named sidecar ports `jmx-metrics` (`5556`) and `nginx-metrics` (`9113`).
   - **Unsupported Exporter Type Guardrail**: If asked to install an exporter outside the 20 supported catalog types (e.g., custom `flagd` exporter, Oracle DB, Cassandra), **never** fabricate fake `prom_install_exporter` calls; list the supported catalog and recommend enabling native `/metrics` (or deploying via Helm) + attaching a `ServiceMonitor` via `prom_apply_scrape_config` (`configuring-prometheus-scraping-and-discovery`).
2. **Application Instrumentation & Exemplars ([references/language-instrumentation-matrix.md](references/language-instrumentation-matrix.md))**:
   - **Python Multi-Worker (`Gunicorn`/`Uvicorn --workers N`)**: Configure `PROMETHEUS_MULTIPROC_DIR` backed by an in-memory `emptyDir: {medium: Memory}` volume (cleaned on startup), `multiprocess.MultiProcessCollector(CollectorRegistry())`, Gunicorn `child_exit(server, worker)` (`multiprocess.mark_process_dead(worker.pid)`), and **always import `CONTENT_TYPE_LATEST, generate_latest` from `prometheus_client.openmetrics.exposition`** (NOT top-level `prometheus_client`) so `/metrics` serves `application/openmetrics-text; version=1.0.0; charset=utf-8` and supports trace exemplars!
   - **Go & Java OpenMetrics Exemplars**: In Go (`client_golang`), enable `promhttp.HandlerOpts{EnableOpenMetrics: true}` and record via `histogram.(prometheus.ExemplarObserver).ObserveWithExemplar(dur, prometheus.Labels{"traceID": spanCtx.TraceID().String()})`. In Java (`Micrometer`), add `micrometer-registry-prometheus` + `micrometer-tracing-bridge-otel` negotiated with `scrapeProtocols: [OpenMetricsText1.0.0, ...]`. Check `prom_query_exemplars` to verify stored exemplars.

### 2. Enforce Secret Hygiene & Render Offline Bundle `[MEDIUM FREEDOM]`
1. **Zero Plaintext Credentials (`hooks/secret-safety.py`)**: Never pass inline DB passwords or embedded `postgresql://user:pass@...` DSNs into `prom_install_exporter`! Always pass Kubernetes Secret references via `exporter_config={"secret_env": {"DATA_SOURCE_NAME": {"name": "<secret-name>", "key": "<key>"}}}` (`valueFrom.secretKeyRef`).
2. For offline GitOps bundle rendering or auditing credential redaction warnings, run [scripts/render_exporter_bundle.py](scripts/render_exporter_bundle.py):
   ```bash
   python3 .agents/skills/onboarding-exporters-and-instrumentation/scripts/render_exporter_bundle.py \
     --exporter-type postgres_exporter --namespace otel-demo --name otel-demo-pg-exporter
   ```
   *(If running outside `.agents/skills`, invoke `./scripts/render_exporter_bundle.py` relative to this skill directory.)*

### 3. Deploy / Uninstall Exporter & Verify End-to-End `[LOW FREEDOM — GATE]`
> [!IMPORTANT]
> Always preview `prom_install_exporter` or `prom_uninstall_exporter` with `dry_run=True` first!

1. If write mode is disabled (`MCP_ALLOW_WRITE=false`, write tools unavailable), run `render_exporter_bundle.py` and output the redacted Kubernetes manifests without attempting live writes.
2. Call `prom_install_exporter(..., dry_run=True)` or `prom_uninstall_exporter(..., dry_run=True)` first to preview `applied_resources` / `removed_resources`.
3. **`[GATE]`**: If the user asked for a preview/plan only, **stop** after `dry_run=True`. When live installation or uninstallation was explicitly requested, **proceed immediately in the same turn** to `dry_run=False, confirm=True`.
4. **Verify**:
   - After install: call `prom_verify_metrics_endpoint(backend_id="default", endpoint_url=..., job_label=..., expected_metrics=[...], verify_timeout=20)` to confirm `/metrics` health, validate starter baseline alerts with `prom_validate_rules(..., check_hygiene=True)` when requested, and read `prom://audit/recent`.
   - After uninstall: read `prom://topology/targets` and `prom://audit/recent` to confirm clean removal with zero orphaned `DOWN` targets.

## Reference Documentation

- [Prometheus Supported Exporters Catalog & Starter Alerts](references/exporter-catalog.md)
- [Application Language Instrumentation Matrix (Prometheus & OpenTelemetry)](references/language-instrumentation-matrix.md)
