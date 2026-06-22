# Onboarding Test Guide — OpenTelemetry MCP Server

**Phase 1 of 5** in the OTel Demo end-to-end journey.
**Next phase**: [Pipeline Investigation](OTEL_PIPELINE_INVESTIGATION_TEST_GUIDE.md)

> This guide walks through onboarding real applications running in the `otel-demo` namespace
> from scratch — discovering services, detecting languages, provisioning collectors, and
> enabling auto-instrumentation. Every step uses the MCP server tools.

---

## Prerequisites

| Component | Status |
|-----------|--------|
| Kubernetes cluster | v1.24+ with `kubectl` configured |
| OTel Operator | Installed (`kubectl get crd instrumentations.opentelemetry.io`) |
| OTel Demo | Deployed in `otel-demo` namespace (`helm install my-otel-demo open-telemetry/opentelemetry-demo`) |
| MCP Server | Running (`uv run opentelemetry-mcp-server`) |

---

## The Starting Point

You have 20+ services running in `otel-demo` — a real microservices application with services
written in Java, Python, Go, .NET, Node.js, C++, Ruby, Rust, PHP, and Kotlin. You want to
onboard their telemetry (traces, metrics, logs) using the MCP server. Where do you start?

### OTel Demo Service Inventory

| Service | Language | Role |
|---------|----------|------|
| `ad` | Java | Ad service with error injection |
| `cart` | .NET | Shopping cart (Redis-backed) |
| `checkout` | Go | Order processing |
| `currency` | C++ | Currency conversion |
| `email` | Ruby | Email notifications |
| `frontend` | TypeScript/Node.js | Web storefront (Next.js) |
| `fraud-detection` | Kotlin (JVM) | Fraud analysis |
| `load-generator` | Python | Traffic generator (Locust) |
| `payment` | JavaScript/Node.js | Payment processing |
| `product-catalog` | Go | Product database |
| `product-reviews` | Python | Review system |
| `quote` | PHP | Quote generation |
| `recommendation` | Python | ML recommendations |
| `shipping` | Rust | Shipping calculation |

---

## Phase 1: System Health Check

Before anything else, verify the MCP server can talk to the cluster.

### Step 1.1: Check Cluster Connectivity

| Field | Value |
|-------|-------|
| **Prompt** | `Check if the OTel MCP server can connect to Kubernetes and see OTel CRDs.` |
| **Resource** | `otel://system/health` |
| **Parameters** | *(none — resource read)* |
| **Internal action** | Calls `VersionApi().get_code()` to verify K8s API connectivity; checks server process health |
| **Expected output** | `server.status: "healthy"`, `kubernetes.status: "healthy"`, `kubernetes.git_version: "v1.35.1"`, `kubernetes.context: "docker-desktop"` |

**Manual validation:**
```bash
kubectl version --short
kubectl config current-context
```

---

## Phase 2: Service Discovery

### Step 2.1: Discover What's Already Running

| Field | Value |
|-------|-------|
| **Prompt** | `List all OTel collectors in the cluster.` |
| **Tool** | `otel_list_collectors` |
| **Parameters** | `{}` |
| **Internal action** | Scans all namespaces for `OpenTelemetryCollector` CRDs |
| **Expected output** | 1 collector found: `otel-demo-collector` in `otel-demo` (daemonset mode, 3 pipelines) |
| **Why this matters** | Tells you a shared collector already exists — you don't need to create one from scratch |

### Step 2.2: Discover Instrumented Services

| Field | Value |
|-------|-------|
| **Prompt** | `Show me all instrumented services in the "otel-demo" namespace.` |
| **Tool** | `otel_list_instrumented_services` |
| **Parameters** | `{"namespace": "otel-demo"}` |
| **Internal action** | Lists all Deployments in the namespace; for each, checks: (1) OTel Operator annotations (`inject-java`, etc.), (2) init containers with `otel` prefix, (3) `OTEL_*` env vars, (4) language detection via 4-tier cascade: annotations → image patterns → container names → runtime env vars |
| **Expected output** | 15+ services found, all with `sdk_env_vars_present: true` (manual SDK), `language` auto-detected |

**What the tool reveals for each service:**

| Field | Description |
|-------|-------------|
| `name` | Deployment name |
| `language` | Auto-detected via 4-tier cascade |
| `init_container_injected` | Is OTel init container present? |
| `sdk_env_vars_present` | Are `OTEL_*` env vars set? |
| `signals_detected` | Which signals: traces, metrics, logs |
| `endpoint_configured` | Where telemetry is sent |
| `warnings` | Mismatches or missing configs |

**Manual validation:**
```bash
# Check a specific service's OTel config
kubectl get deploy recommendation -n otel-demo \
  -o jsonpath='{.spec.template.spec.containers[0].env}' | python3 -m json.tool | grep -i otel
```

### Step 2.3: Language Lookup for Each Service

For each unique language detected, look up the instrumentation approach:

| Field | Value |
|-------|-------|
| **Prompt** | `How do I instrument a Python service with OpenTelemetry?` |
| **Tool** | `otel_lookup_instrumentation` |
| **Parameters** | `{"language": "python"}` |
| **Internal action** | Reads the static language registry; returns auto-instrumentation support, annotation key, frameworks |
| **Expected output** | `auto_instrumentation_available: true`, `annotation_key: "instrumentation.opentelemetry.io/inject-python"` |

Repeat for each language in your service inventory:

| Language | Prompt | Key Output |
|----------|--------|------------|
| Python | `How do I instrument a Python service?` | `inject-python`, auto-instrumentation ✅ |
| Java | `Is auto-instrumentation available for Java?` | `inject-java`, auto-instrumentation ✅ |
| Go | `How do I instrument a Go service?` | `inject-go`, auto-instrumentation ✅ |
| .NET | `Is OTel auto-instrumentation available for .NET?` | `inject-dotnet`, auto-instrumentation ✅ |
| Node.js | `How do I instrument a Node.js service?` | `inject-nodejs`, auto-instrumentation ✅ |
| Rust | `Is auto-instrumentation available for Rust?` | Manual SDK only ❌ |
| C++ | `Is auto-instrumentation available for C++?` | Manual SDK only ❌ |
| Ruby | `Is auto-instrumentation available for Ruby?` | Manual SDK only ❌ |

**Resource alternative:** `otel://registry/languages` returns all languages at once.

---

## Phase 3: Collector Provisioning

Now you know what services exist and what languages they use. The next decision is:
**do you use the existing shared collector, or provision new ones?**

### Decision Matrix

| Scenario | Approach | Tool |
|----------|----------|------|
| Single team, shared namespace | Use existing shared collector | `otel_get_collector` to inspect |
| Per-application isolation | Provision a dedicated collector per app | `otel_provision_collector` |
| Traces-only service | Lightweight deployment-mode collector | `otel_provision_collector` |
| Full telemetry (traces + metrics + logs) | DaemonSet collector | `otel_provision_collector` |

### Step 3.1: Inspect the Existing Shared Collector

| Field | Value |
|-------|-------|
| **Prompt** | `Show me the full configuration of the collector "otel-demo-collector" in the "otel-demo" namespace.` |
| **Tool** | `otel_get_collector` |
| **Parameters** | `{"namespace": "otel-demo", "name": "otel-demo-collector", "detail_level": "full"}` |
| **Internal action** | Reads the CRD, parses config, returns full pipeline topology including `raw_config_yaml` |
| **Key findings** | 3 pipelines (traces→Jaeger, metrics→Prometheus, logs→OpenSearch), SpanMetrics enabled, DaemonSet mode |

### Step 3.2: Provision a Dedicated Collector for a Python Service (Traces + Metrics)

Suppose the `recommendation` service (Python) needs its own collector for isolation:

| Field | Value |
|-------|-------|
| **Prompt** | `Provision a new OTel collector for traces and metrics in the "otel-demo" namespace — dry run first.` |
| **Tool** | `otel_provision_collector` |
| **Parameters** | `{"namespace": "otel-demo", "signals": ["traces", "metrics"], "name": "recommendation-collector", "dry_run": true}` |
| **Internal action** | (1) Auto-discovers cluster size (nodes, workloads). (2) Scans for backend services (finds Jaeger on `jaeger:4317`, Prometheus on `prometheus:9090`). (3) Auto-selects mode → `deployment` (no logs = no need for DaemonSet). (4) Generates best-practice processor chain: `memory_limiter → k8sattributes → resourcedetection → resource → batch`. (5) Sizes resources based on cluster size. (6) Returns full CRD preview. |
| **Expected output** | `action: "dry_run"`, generated config with OTLP receivers, 2 pipelines (traces/metrics), auto-discovered exporter targets, mode rationale, resource sizing, labels: `talkops.ai/provisioned=true` |

**What was auto-discovered (no user input needed):**
- Jaeger endpoint: `jaeger:4317` (found via service scan)
- Prometheus endpoint: `prometheus:9090/api/v1/otlp` (found via service scan)
- Cluster size: `small` (1 node)
- Recommended resources: `cpu: 100m/500m`, `memory: 256Mi/512Mi`

### Step 3.3: Provision a Full-Signal Collector (Traces + Metrics + Logs)

For a service that also needs log collection:

| Field | Value |
|-------|-------|
| **Prompt** | `Provision a collector with traces, metrics, and logs for the "otel-demo" namespace with filelog enabled — dry run.` |
| **Tool** | `otel_provision_collector` |
| **Parameters** | `{"namespace": "otel-demo", "signals": ["traces", "metrics", "logs"], "name": "full-signal-collector", "enable_filelog": true, "dry_run": true}` |
| **Internal action** | Same auto-discovery + filelog forces DaemonSet mode (needs node-level `/var/log/pods` access). Adds volume mounts for `/var/log/pods` and checkpoint storage. Self-exclusion pattern auto-generated. |
| **Expected output** | `mode: "daemonset"` (forced by filelog), `mode_rationale: "filelog receiver requires node-level access"`, volumes/volumeMounts auto-configured |
| **Smart recommendations** | `💡 Consider enable_spanmetrics=True to get automatic RED metrics from your traces` |

### Step 3.4: Provision with SpanMetrics Enabled

| Field | Value |
|-------|-------|
| **Prompt** | `Provision a collector with traces and metrics in "otel-demo", enable SpanMetrics for RED metrics — dry run.` |
| **Tool** | `otel_provision_collector` |
| **Parameters** | `{"namespace": "otel-demo", "signals": ["traces", "metrics"], "name": "red-metrics-collector", "enable_spanmetrics": true, "dry_run": true}` |
| **Internal action** | Adds `spanmetrics` connector between traces and metrics pipelines. Traces pipeline exports to `spanmetrics`, metrics pipeline receives from `spanmetrics`. Default dimensions: `http.method`, `http.status_code`, `rpc.method`. |
| **Expected output** | Config includes `connectors.spanmetrics` section, traces pipeline has `spanmetrics` as exporter, metrics pipeline has `spanmetrics` as receiver |

### Step 3.5: Apply the Collector (After Review)

Once you've reviewed the dry-run output:

| Field | Value |
|-------|-------|
| **Prompt** | `Apply the recommendation-collector — set dry_run to false.` |
| **Tool** | `otel_provision_collector` |
| **Parameters** | `{"namespace": "otel-demo", "signals": ["traces", "metrics"], "name": "recommendation-collector", "dry_run": false}` |
| **Internal action** | Creates the `OpenTelemetryCollector` CRD in the cluster via `create_or_patch_collector()`. The OTel Operator reconciles the CRD and deploys collector pods. |
| **Expected output** | `action: "applied"`, `message: "✅ Collector provisioned successfully!"`, `result.uid` (Kubernetes UID) |

**Manual validation:**
```bash
kubectl get opentelemetrycollectors -n otel-demo
# NAME                       MODE         VERSION   AGE
# otel-demo-collector        daemonset    0.151.0   5h
# recommendation-collector   deployment             10s  ← NEW

kubectl get pods -n otel-demo -l app.kubernetes.io/managed-by=talkops-mcp
# recommendation-collector-xxx   1/1   Running
```

---

## Phase 4: Enable Auto-Instrumentation

For services that support auto-instrumentation (Java, Python, Node.js, .NET, Go), you can enable
OTel Operator injection without modifying application code.

### Step 4.1: Create an Instrumentation CR

| Field | Value |
|-------|-------|
| **Prompt** | `Create an Instrumentation CR named "default" in the "otel-demo" namespace with endpoint "http://otel-demo-collector:4317" — dry run first.` |
| **Tool** | `otel_patch_instrumentation` |
| **Parameters** | `{"namespace": "otel-demo", "name": "default", "endpoint": "http://otel-demo-collector:4317", "dry_run": true}` |
| **Internal action** | Generates an `Instrumentation` CRD with the OTLP exporter endpoint, default propagators (`tracecontext`, `baggage`), and no sampler (100% traces). Returns the YAML preview. |
| **Expected output** | `action: "dry_run"`, spec includes `exporter.endpoint`, `propagators`, no sampler config |

### Step 4.2: Create Instrumentation CR with Sampler

For production, you'd want sampling to control trace volume:

| Field | Value |
|-------|-------|
| **Prompt** | `Create an Instrumentation CR with 25% head sampling in "otel-demo" — dry run.` |
| **Tool** | `otel_patch_instrumentation` |
| **Parameters** | `{"namespace": "otel-demo", "name": "sampled", "endpoint": "http://otel-demo-collector:4317", "sampler_type": "parentbased_traceidratio", "sampler_argument": "0.25", "dry_run": true}` |
| **Internal action** | Same as above + adds `spec.sampler.type` and `spec.sampler.argument` |
| **Expected output** | `sampler: {type: "parentbased_traceidratio", argument: "0.25"}` |

### Step 4.3: Annotate a Deployment for Auto-Injection

| Field | Value |
|-------|-------|
| **Prompt** | `Enable Python auto-instrumentation on the "recommendation" deployment in "otel-demo" — dry run first.` |
| **Tool** | `otel_annotate_deployment` |
| **Parameters** | `{"namespace": "otel-demo", "name": "recommendation", "language": "python", "dry_run": true}` |
| **Internal action** | Looks up the annotation key for Python (`instrumentation.opentelemetry.io/inject-python`), generates a patch to add it to the Deployment's pod template metadata |
| **Expected output** | `annotation.key: "instrumentation.opentelemetry.io/inject-python"`, `annotation.value: "true"` |

Repeat for other auto-instrumentable services:

| Service | Language | Prompt | Annotation Key |
|---------|----------|--------|----------------|
| `ad` | Java | `Enable Java auto-instrumentation on "ad" in "otel-demo"` | `inject-java` |
| `cart` | .NET | `Enable .NET auto-instrumentation on "cart" in "otel-demo"` | `inject-dotnet` |
| `frontend` | Node.js | `Enable Node.js auto-instrumentation on "frontend" in "otel-demo"` | `inject-nodejs` |
| `checkout` | Go | `Enable Go auto-instrumentation on "checkout" in "otel-demo"` | `inject-go` |
| `recommendation` | Python | `Enable Python auto-instrumentation on "recommendation" in "otel-demo"` | `inject-python` |

### Step 4.4: Verify Instrumentation Status

| Field | Value |
|-------|-------|
| **Prompt** | `Show me all instrumented services in the "otel-demo" namespace.` |
| **Tool** | `otel_list_instrumented_services` |
| **Parameters** | `{"namespace": "otel-demo"}` |
| **Internal action** | Re-scans all deployments; now should show updated annotations and init containers |
| **Expected output** | Previously-annotated services now show `init_container_injected: true` and `language` from annotations (Tier 1 confidence) |

**Manual validation:**
```bash
# Check if auto-injection took effect
kubectl get deploy recommendation -n otel-demo -o jsonpath='{.spec.template.metadata.annotations}' | python3 -m json.tool
# Expected: "instrumentation.opentelemetry.io/inject-python": "true"

# Check for OTel init container
kubectl get pods -n otel-demo -l app.kubernetes.io/name=recommendation -o jsonpath='{.items[0].spec.initContainers[*].name}'
# Expected: opentelemetry-auto-instrumentation
```

---

## Phase Summary

At the end of this phase, you have:

| What | Status |
|------|--------|
| ✅ System health verified | K8s connected, OTel CRDs available |
| ✅ Services discovered | 15+ services with languages auto-detected |
| ✅ Existing collector inspected | `otel-demo-collector` (shared, 3 pipelines) |
| ✅ New collectors provisioned | Per-application or per-signal as needed |
| ✅ Instrumentation CRs created | OTLP endpoint + optional sampler config |
| ✅ Deployments annotated | Auto-injection enabled for supported languages |
| ✅ Instrumentation verified | Init containers injected, env vars present |

**Next step →** [Pipeline Investigation](OTEL_PIPELINE_INVESTIGATION_TEST_GUIDE.md): Verify the collectors are working, validate processor ordering, check filelog safety, and inspect enrichment profiles.
