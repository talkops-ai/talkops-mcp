---
name: configuring-prometheus-scraping-and-discovery
description: Configures, validates, troubleshoots, and manages Prometheus scrape discovery across Kubernetes Operator CRDs (ServiceMonitor, PodMonitor, Probe, ScrapeConfig), Prometheus 3.0 native histogram and OTLP ingestion, and File SD target groups. Always read SKILL.md first before calling run_command, and inspect CRDs via Prometheus MCP resources rather than raw kubectl. Use when onboarding an existing Kubernetes Service or Pod metrics endpoint for scraping, configuring Blackbox Probe or external ScrapeConfig CRDs, managing file_sd JSON targets, or debugging missing/DOWN scrape targets. Do not use for installing third-party exporter workloads like postgres_exporter or redis_exporter (use onboarding-exporters-and-instrumentation), TSDB cardinality drop relabeling (use optimizing-tsdb-cardinality-and-finops), or provisioning OpenTelemetry Collectors (use provisioning-opentelemetry-collectors).
license: Apache-2.0
metadata:
  author: talkops
  version: "0.2.0"
  domain: observability
  component: prometheus
---

# Configuring Prometheus Scraping and Discovery

Manages the end-to-end lifecycle of Prometheus target discovery across Kubernetes Operator CRDs (`ServiceMonitor`, `PodMonitor`, `Probe`, `ScrapeConfig`), Prometheus 3.0 OTLP/Native Histogram ingestion, and `file_sd` target files. Strictly use Prometheus MCP resources (`prom://kubernetes/scrape-crds`, `prom://kubernetes/manifests/{kind}/{namespace}/{name}`, `prom://topology/targets`) and tools (`prom_apply_scrape_config`, `prom_delete_scrape_config`, `prom_get_diagnostics`, `prom_verify_metrics_endpoint`) — **never** run raw `kubectl` (`kubectl get`, `kubectl apply`) or `curl` shell commands. If invoked via plugin command workflow `commands/setup-monitoring.md` (`/setup-monitoring`), read that command file first and coordinate the full workflow.

## MCP Execution Primitives Used

- **Resources**:
  - `prom://topology/targets` — live scrape target health (`up` vs `down`) and last scrape errors.
  - `prom://kubernetes/scrape-crds` — cluster inventory of `ServiceMonitor`, `PodMonitor`, `Probe`, `ScrapeConfig`, `PrometheusRule` CRDs, `operator_selectors` (`serviceMonitorSelector`, `ruleSelector`, `probeSelector`), `discovered_services` (Service labels and named ports), and `discovered_workloads` (Pod labels and container named ports).
  - `prom://kubernetes/manifests/{kind}/{namespace}/{name}` — read the live redacted YAML/JSON manifest of a specific `ServiceMonitor`, `PodMonitor`, `Probe`, or `ScrapeConfig` (always use this instead of `kubectl get ... -o yaml`).
  - `prom://audit/recent` — inspect recent scrape configuration `dry_run` and `succeeded` audit records.
- **Tools (`scrape` & `diagnostics` toolsets)**:
  - `prom_get_diagnostics` — inspect `DOWN` targets (`include="targets"`), scrape errors (`got "<"` HTML parse errors, `context deadline exceeded` timeouts), and backend health.
  - `prom_verify_metrics_endpoint` — probe an HTTP `/metrics` URL (including in-cluster `.svc` endpoints) and poll Prometheus until `up{job=...} == 1.0`.
  - `prom_apply_scrape_config` — create or update `ServiceMonitor` (supporting `target_service` auto-discovery), `PodMonitor`, `Probe`, `ScrapeConfig`, or `file_sd` target groups (`dry_run=True` default).
  - `prom_delete_scrape_config` — remove retired scrape CRDs or `file_sd` files (`dry_run=True` default).

## Step-by-Step Scrape Configuration Workflow

### 1. Inspect Current Scrape Topology, CRDs & Access Mode `[HIGH FREEDOM]`
> [!CAUTION]
> **Strictly Zero Raw `kubectl` Commands**: Do NOT execute any `kubectl` shell commands (`kubectl get`, `kubectl describe`, `kubectl apply`, etc.) at any step! `prom://kubernetes/scrape-crds` already returns `operator_selectors`, `prometheus_instances`, `discovered_services` (labels & named ports), and `discovered_workloads`, and `prom://kubernetes/manifests/{kind}/{namespace}/{name}` returns full live CRD manifests. If an MCP resource response is offloaded to `file:///.../resource_0.txt`, read or parse ONLY that local file via `read_file` or `python3` — NEVER invoke `kubectl`!

1. Read `prom://topology/targets` and `prom://kubernetes/scrape-crds` (plus `prom://kubernetes/manifests/{kind}/{namespace}/{name}` when inspecting specific CRDs).
2. If write tools (`prom_apply_scrape_config` / `prom_delete_scrape_config`) are absent or disabled because the MCP server is running in read-only mode (`MCP_ALLOW_WRITE=false`), perform read-only discovery + offline script validation and output copy-pasteable Kubernetes YAML manifests without attempting live cluster writes.
3. Consult [references/operator-scrape-crds.md](references/operator-scrape-crds.md) and [references/file-sd-and-relabel-guide.md](references/file-sd-and-relabel-guide.md) when diagnosing failing scrape targets:
   - **CRD missing from `/targets` completely**: Missing Prometheus Operator `serviceMonitorSelector` / `probeSelector` label (e.g., `release: kube-prometheus-stack`; `prom_apply_scrape_config` auto-injects required selector labels).
   - **`0/0` active targets**: `spec.selector.matchLabels` does not match `Service.metadata.labels` (not pod labels!), or `spec.namespaceSelector.matchNames` omits the target namespace.
   - **`0/N UP` or `DOWN` target**:
     - `port: "10000"` numeric port string used in `ServiceMonitor.spec.endpoints[].port` instead of the Kubernetes `Service`'s **named** port string (`spec.ports[].name`, e.g., `envoy-admin` or `metrics`).
     - `expected a valid start token, got "<" ("INVALID")`: Scrape `path` hit an HTML UI/login page (e.g. `/`) instead of an OpenMetrics/Prometheus text endpoint (`/metrics` or `/stats/prometheus`).
     - `context deadline exceeded`: Exporter response exceeds `scrapeTimeout`; increase `interval` and `scrapeTimeout` while strictly maintaining `scrapeTimeout <= interval`.
   - **Prometheus 3.0 Native Histograms & OTLP Ingestion**: Set `scrapeNativeHistograms: true` and `nativeHistogramBucketLimit` (e.g., `160`) on `ServiceMonitor`/`PodMonitor` endpoints, configure `otlp.promote_resource_attributes` (e.g., `service.instance.id`, `service.name`, `service.namespace`, `deployment.environment.name`, `k8s.namespace.name`, `k8s.pod.name`), and always explicitly contrast `otlp.translation_strategy` modes:
     - `UnderscoreEscapingWithSuffixes`: escapes dots/special characters to underscores and appends unit/`_total` suffixes (e.g., `http_server_request_duration_seconds`, `service_name`).
     - `NoUTF8EscapingWithSuffixes`: preserves native UTF-8 dotted metric and promoted resource attribute names (e.g., `{"http.server.request.duration_seconds", "service.name"="checkout-service"}`) while keeping standard Prometheus unit/counter suffixes.

### 2. Enforce Zero-Secret Hygiene & Offline Manifest Validation `[MEDIUM FREEDOM]`
1. **Zero Inline Credentials (`secret-safety.py`)**: Strictly **refuse** inline plaintext `bearerToken`, `basicAuth.password`, or embedded `user:pass@` URLs in `ServiceMonitor` / `PodMonitor` / `ScrapeConfig` specs (never echo raw secret values back). Replace inline tokens with `bearerTokenSecret: {name: "<secret-name>", key: "<key>"}` (or `basicAuth` Kubernetes `Secret` references), **immediately call `prom_apply_scrape_config(..., dry_run=True)` with the hardened `bearerTokenSecret` spec** to generate a safe preview, and stop before `dry_run=False` until the user confirms the Secret exists.
2. Validate candidate `ServiceMonitor`, `PodMonitor`, `Probe`, `ScrapeConfig`, or `file_sd` specs offline using [scripts/validate_scrape_manifest.py](scripts/validate_scrape_manifest.py) (catches illegal DNS-1123 underscores `_`, missing selectors, and numeric `port` anti-patterns):
   ```bash
   python3 .agents/skills/configuring-prometheus-scraping-and-discovery/scripts/validate_scrape_manifest.py \
     --kind ServiceMonitor --name frontend-proxy-envoy-monitor \
     --spec-json '{"selector":{"matchLabels":{"app.kubernetes.io/name":"frontend-proxy"}},"endpoints":[{"port":"envoy-admin","path":"/stats/prometheus","interval":"30s"}]}'
   ```
   *(If running outside `.agents/skills`, invoke `./scripts/validate_scrape_manifest.py` relative to this skill directory.)*

### 3. Preview, Apply/Delete, and Verify Scrape Health `[LOW FREEDOM — GATE]`
> [!IMPORTANT]
> Always execute `prom_apply_scrape_config` or `prom_delete_scrape_config` with `dry_run=True` first!

1. **Preview (`dry_run=True`)**: Call `prom_apply_scrape_config(..., dry_run=True)` or `prom_delete_scrape_config(..., dry_run=True)` to inspect the rendered manifest, resolved `discovered_service` ports/labels, and operator selector labels.
2. **`[GATE]` Hold or Execute Live**:
   - If the operator asked only to validate/preview/plan, if write mode is disabled, or if a security guard failed (e.g., inline plaintext `bearerToken`), **stop** after the `dry_run=True` preview and present the hardened manifest.
   - When the operator explicitly asked to onboard, fix, apply, or delete the scrape config live and all guards pass, **proceed immediately in the same turn** to `dry_run=False, confirm=True`.
3. **Post-Change Verification**: Call `prom_verify_metrics_endpoint(backend_id="default", endpoint_url=..., job_label=..., verify_timeout=15)` to verify `/metrics` exposition and `up == 1.0`, and read `prom://audit/recent` to confirm the recorded audit trail.

## Reference Documentation

- [Prometheus Operator Scrape CRDs & Prometheus 3.0 Ingestion Reference](references/operator-scrape-crds.md)
- [File Service Discovery (`file_sd`) and Target Relabeling Guide](references/file-sd-and-relabel-guide.md)
