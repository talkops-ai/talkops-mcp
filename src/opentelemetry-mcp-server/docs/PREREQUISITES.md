# Prerequisites — OpenTelemetry MCP Server Testing Environment

This guide documents the complete infrastructure setup required to test the OpenTelemetry MCP server's tools and resources against a live Kubernetes cluster.

---

## Architecture Overview

```
┌──────────────────────────┐
│   MCP Client (IDE)       │
└──────────┬───────────────┘
           │ MCP Protocol
┌──────────▼───────────────┐
│  OpenTelemetry MCP Server│
│  (localhost:8768/mcp)    │
└──────────┬───────────────┘
           │ K8s API
┌──────────▼───────────────────────────────────────┐
│  Kubernetes Cluster (Docker Desktop)             │
│                                                  │
│  ┌────────────────────────────────────────────┐  │
│  │  cert-manager (cert-manager namespace)     │  │
│  │  └─ TLS certs for OTel Operator webhooks   │  │
│  └────────────────────────────────────────────┘  │
│                                                  │
│  ┌────────────────────────────────────────────┐  │
│  │  OTel Operator (opentelemetry-operator-    │  │
│  │    system namespace)                       │  │
│  │  └─ Watches OpenTelemetryCollector &       │  │
│  │     Instrumentation CRDs                   │  │
│  └────────────────────────────────────────────┘  │
│                                                  │
│  ┌────────────────────────────────────────────┐  │
│  │  Backends (monitoring namespace)           │  │
│  │  ├─ Tempo   → traces  (OTLP gRPC :4317)   │  │
│  │  ├─ Loki    → logs    (HTTP :3100)        │  │
│  │  └─ Grafana → visualization (:3000)       │  │
│  └────────────────────────────────────────────┘  │
│                                                  │
│  ┌────────────────────────────────────────────┐  │
│  │  OTel Collector (created by MCP tools)     │  │
│  │  └─ Routes: traces→Tempo, logs→Loki       │  │
│  └────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────┘
```

---

## Component Summary

| Component | Namespace | Version | Purpose |
|:----------|:----------|:--------|:--------|
| **cert-manager** | `cert-manager` | v1.20.2 | TLS certificate management for OTel Operator admission webhooks |
| **OpenTelemetry Operator** | `opentelemetry-operator-system` | v0.114.1 | Watches for `OpenTelemetryCollector` and `Instrumentation` CRDs, reconciles them into pods |
| **Grafana Tempo** | `monitoring` | Chart v1.24.4 | Traces backend (OTLP gRPC on port 4317) |
| **Grafana Loki** | `monitoring` | v3.6.7 (Chart v7.0.0) | Logs backend (HTTP on port 3100), SingleBinary mode |
| **Grafana** | `monitoring` | Chart v10.5.15 | Visualization UI with Tempo and Loki datasources pre-configured |

---

## System Requirements

| Requirement | Minimum | Notes |
|:------------|:--------|:------|
| **Kubernetes** | v1.24+ | Docker Desktop, kind, minikube, or cloud cluster |
| **Helm** | v3.9+ | Package manager for all installations |
| **kubectl** | Configured | Must have access to the target cluster |
| **Python** | 3.12+ | For running the MCP server |
| **uv** | Latest | Python dependency manager |

---

## Step-by-Step Installation

### Step 1: Add Helm Repositories

```bash
helm repo add jetstack https://charts.jetstack.io
helm repo add open-telemetry https://open-telemetry.github.io/opentelemetry-helm-charts
helm repo add grafana https://grafana.github.io/helm-charts
helm repo update
```

---

### Step 2: Install cert-manager

The OpenTelemetry Operator requires TLS certificates for its admission webhooks. cert-manager automates certificate generation and rotation.

```bash
helm install cert-manager jetstack/cert-manager \
  --namespace cert-manager \
  --create-namespace \
  --set crds.enabled=true
```

**Wait for readiness:**

```bash
kubectl wait --for=condition=ready pod \
  -l app.kubernetes.io/instance=cert-manager \
  -n cert-manager \
  --timeout=60s
```

**Expected output (3 pods):**

```
pod/cert-manager-xxx              condition met
pod/cert-manager-cainjector-xxx   condition met
pod/cert-manager-webhook-xxx      condition met
```

> **Note:** If you want to skip cert-manager, you can use auto-generated self-signed certificates instead:
> ```bash
> # Alternative: no cert-manager needed
> helm install opentelemetry-operator open-telemetry/opentelemetry-operator \
>   --namespace opentelemetry-operator-system --create-namespace \
>   --set admissionWebhooks.certManager.enabled=false \
>   --set admissionWebhooks.autoGenerateCert.enabled=true
> ```

---

### Step 3: Install OpenTelemetry Operator

The Operator installs CRD **definitions** (`OpenTelemetryCollector`, `Instrumentation`) and a controller that watches for CRD **instances**. It does **not** deploy any collectors or instrumentation by itself — the MCP server tools create those.

```bash
helm install opentelemetry-operator open-telemetry/opentelemetry-operator \
  --namespace opentelemetry-operator-system \
  --create-namespace
```

**Wait for readiness:**

```bash
kubectl wait --for=condition=ready pod \
  -l app.kubernetes.io/instance=opentelemetry-operator \
  -n opentelemetry-operator-system \
  --timeout=60s
```

**Verify CRD definitions exist:**

```bash
kubectl get crd opentelemetrycollectors.opentelemetry.io instrumentations.opentelemetry.io
```

**Expected output:**

```
NAME                                       CREATED AT
opentelemetrycollectors.opentelemetry.io   2026-05-29T06:16:03Z
instrumentations.opentelemetry.io          2026-05-29T06:16:03Z
```

**Verify no instances exist yet (expected — MCP tools will create these):**

```bash
kubectl get opentelemetrycollectors -A   # empty
kubectl get instrumentations -A          # empty
```

---

### Step 4: Install Grafana Tempo (Traces Backend)

Tempo receives traces via OTLP gRPC on port 4317. Deployed in monolithic (single-binary) mode for Docker Desktop.

```bash
helm install tempo grafana/tempo \
  --namespace monitoring \
  --create-namespace \
  --set tempo.receivers.otlp.protocols.grpc.endpoint="0.0.0.0:4317" \
  --set tempo.receivers.otlp.protocols.http.endpoint="0.0.0.0:4318"
```

**Wait for readiness:**

```bash
kubectl wait --for=condition=ready pod \
  -l app.kubernetes.io/name=tempo \
  -n monitoring \
  --timeout=60s
```

**Verify the service exposes OTLP port:**

```bash
kubectl get svc tempo -n monitoring
# Should show port 4317 (OTLP gRPC)
```

---

### Step 5: Install Grafana Loki (Logs Backend)

Loki receives logs via HTTP on port 3100. Deployed in SingleBinary mode with filesystem storage (no object storage required for testing).

```bash
helm install loki grafana/loki \
  --namespace monitoring \
  --set deploymentMode=SingleBinary \
  --set singleBinary.replicas=1 \
  --set loki.auth_enabled=false \
  --set loki.commonConfig.replication_factor=1 \
  --set loki.storage.type=filesystem \
  --set 'loki.schemaConfig.configs[0].from=2024-01-01' \
  --set 'loki.schemaConfig.configs[0].store=tsdb' \
  --set 'loki.schemaConfig.configs[0].object_store=filesystem' \
  --set 'loki.schemaConfig.configs[0].schema=v13' \
  --set 'loki.schemaConfig.configs[0].index.prefix=index_' \
  --set 'loki.schemaConfig.configs[0].index.period=24h' \
  --set read.replicas=0 \
  --set write.replicas=0 \
  --set backend.replicas=0 \
  --set chunksCache.enabled=false \
  --set resultsCache.enabled=false
```

**Wait for readiness:**

```bash
kubectl wait --for=condition=ready pod \
  -l app.kubernetes.io/name=loki \
  -n monitoring \
  --timeout=120s
```

**Expected output (3 pods):**

```
pod/loki-0              condition met
pod/loki-canary-xxx     condition met
pod/loki-gateway-xxx    condition met
```

---

### Step 6: Install Grafana (Visualization)

Grafana provides the UI to explore traces stored in Tempo and logs stored in Loki. Installed with both datasources pre-configured.

```bash
helm install grafana grafana/grafana \
  --namespace monitoring \
  --set replicas=1 \
  --set adminPassword=admin \
  --set 'datasources.datasources\.yaml.apiVersion=1' \
  --set 'datasources.datasources\.yaml.datasources[0].name=Tempo' \
  --set 'datasources.datasources\.yaml.datasources[0].type=tempo' \
  --set 'datasources.datasources\.yaml.datasources[0].url=http://tempo:3200' \
  --set 'datasources.datasources\.yaml.datasources[0].access=proxy' \
  --set 'datasources.datasources\.yaml.datasources[0].isDefault=true' \
  --set 'datasources.datasources\.yaml.datasources[1].name=Loki' \
  --set 'datasources.datasources\.yaml.datasources[1].type=loki' \
  --set 'datasources.datasources\.yaml.datasources[1].url=http://loki-gateway:80' \
  --set 'datasources.datasources\.yaml.datasources[1].access=proxy'
```

**Wait for readiness:**

```bash
kubectl wait --for=condition=ready pod \
  -l app.kubernetes.io/name=grafana \
  -n monitoring \
  --timeout=60s
```

**Access Grafana:**

```bash
# Port-forward to localhost:3000
kubectl port-forward svc/grafana 3000:80 -n monitoring &

# Open in browser
open http://localhost:3000
```

**Login credentials:**

| Field | Value |
|:------|:------|
| Username | `admin` |
| Password | `admin` |

**Pre-configured datasources:**

| Datasource | Type | Internal URL | Purpose |
|:-----------|:-----|:-------------|:--------|
| Tempo | `tempo` | `http://tempo:3200` | Trace search & visualization |
| Loki | `loki` | `http://loki-gateway:80` | Log search & visualization |

---

## Verification Checklist

Run these commands to verify the entire setup:

```bash
# 1. All namespaces created
kubectl get ns cert-manager opentelemetry-operator-system monitoring

# 2. All pods running
kubectl get pods -n cert-manager
kubectl get pods -n opentelemetry-operator-system
kubectl get pods -n monitoring

# 3. CRD definitions exist
kubectl get crd opentelemetrycollectors.opentelemetry.io
kubectl get crd instrumentations.opentelemetry.io

# 4. Backend services discoverable
kubectl get svc -n monitoring
```

**Expected final state:**

| Namespace | Pods | Replicas | Status |
|:----------|:-----|:--------:|:------:|
| `cert-manager` | cert-manager, cainjector, webhook | 1 each | ✅ Running |
| `opentelemetry-operator-system` | opentelemetry-operator | 1 | ✅ Running |
| `monitoring` | tempo-0 | 1 | ✅ Running |
| `monitoring` | loki-0, loki-canary, loki-gateway | 1 each | ✅ Running |
| `monitoring` | grafana | 1 | ✅ Running |

---

## Auto-Discovery Endpoints

The MCP server's `otel_provision_collector` tool auto-discovers backends by scanning K8s service names in the `monitoring` namespace (among others). With this setup, it will find:

| Service | Pattern Match | Signal | Exporter Type | Endpoint |
|:--------|:-------------|:-------|:-------------|:---------|
| `tempo` | `tempo` | traces | `otlp` (gRPC) | `tempo.monitoring:4317` |
| `loki` | `loki` | logs | `loki` (HTTP) | `http://loki.monitoring:3100` |

---

## Cleanup

To tear down the entire test environment:

```bash
# Remove visualization and backends
helm uninstall grafana -n monitoring
helm uninstall loki -n monitoring
helm uninstall tempo -n monitoring
kubectl delete namespace monitoring

# Remove OTel Operator
helm uninstall opentelemetry-operator -n opentelemetry-operator-system
kubectl delete namespace opentelemetry-operator-system

# Remove cert-manager
helm uninstall cert-manager -n cert-manager
kubectl delete namespace cert-manager

# Remove CRDs (optional — left behind by Helm)
kubectl delete crd opentelemetrycollectors.opentelemetry.io
kubectl delete crd instrumentations.opentelemetry.io
kubectl delete crd certificates.cert-manager.io certificaterequests.cert-manager.io \
  clusterissuers.cert-manager.io issuers.cert-manager.io orders.acme.cert-manager.io \
  challenges.acme.cert-manager.io
```

---

## Next Steps

With all prerequisites in place, proceed to testing the MCP server:

1. **Start the MCP server**: `uv run opentelemetry-mcp-server`
2. **Health check**: Read resource `otel://system/health`
3. **Provision a collector**: Use `otel_provision_collector` to route traces → Tempo, logs → Loki
4. **Onboard services**: Use `otel_patch_instrumentation` + `otel_annotate_deployment`
5. **Validate pipelines**: Use `otel_verify_pipeline_health`

See [WORKFLOW_JOURNEYS.md](WORKFLOW_JOURNEYS.md) for the full testing workflows.

---

*Document Version: 1.0 | Docker Desktop single-node setup | Tested: 2026-05-29*
