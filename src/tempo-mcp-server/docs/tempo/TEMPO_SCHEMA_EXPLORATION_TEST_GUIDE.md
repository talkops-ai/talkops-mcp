# Schema Exploration Test Guide — Tempo MCP Server (OTel Demo)

**Phase 6 of 7** in the Tempo end-to-end journey.
**Previous phase**: [Metrics-First Triage (RED)](TEMPO_METRICS_FIRST_TRIAGE_TEST_GUIDE.md)
**Next phase**: [Service Topology & Alerting](TEMPO_TOPOLOGY_ALERTING_TEST_GUIDE.md)

> This phase performs a comprehensive first-time exploration of the Tempo
> environment — discovering backends, running diagnostics, building a complete
> attribute taxonomy, enumerating services and namespaces, resolving K8s attribute
> mappings, and understanding the deployment topology.
>
> **Use case**: First connection by an AI agent (e.g., k8s-autopilot) or a new team
> onboarding onto Tempo. This is the recommended starting workflow for all integrations.

---

## Prerequisites (Completed in Phase 5)

| Component | Status |
|-----------|--------|
| ✅ RED metrics working | `tempo_traceql_metrics_range` — rate, errors, P99, histogram |
| ✅ Cross-pillar pivots working | `tempo_get_exemplar_traces`, `tempo_get_trace_from_log` — traces from metrics/logs |
| ✅ Search and summarization | `tempo_traceql_search`, `tempo_summarize_trace` — working |

---

## The Starting Point

Phase 5 performed RED analysis. Now you want a complete picture of the Tempo environment — this is what an agent or operator would do on first connection:

1. **How many backends?** — Discover all configured Tempo backends.
2. **Are they healthy?** — Detailed health and diagnostics.
3. **What data exists?** — Complete attribute taxonomy by scope.
4. **What services and namespaces?** — Service inventory from trace data.
5. **How do K8s concepts map?** — Canonical attribute mapping.
6. **What are the limits?** — Query guardrails and policies.
7. **What's the topology?** — Deployment modes, tenants, K8s integration.

---

## Phase 1: Backend Discovery

### Step 1.1: List All Backends

| Field | Value |
|-------|-------|
| **Prompt** | `What Tempo backends are available?` |
| **Tool** | `tempo_list_backends` |
| **Parameters** | `{}` |
| **Internal action** | Iterates all configured backends. Probes each with a health check (`/ready`). Returns list with health status. |
| **Expected output** | `{"backends": [{"id": "default", "display_name": "", "type": "tempo", "base_url": "http://localhost:3200", "health": "ready", "deployment_mode": "unknown", "multi_tenant": false}], "total": 1}` |

**What to check:**

| Field | What to Verify |
|-------|----------------|
| `id` | Backend ID used in all subsequent tool calls |
| `health` | `"ready"` = healthy; `"not_ready"` = backend unreachable |
| `multi_tenant` | If `true`, tools require a `tenant` parameter |
| `deployment_mode` | `"monolithic"`, `"microservices"`, or `"unknown"` |

### Step 1.2: Read Backend Resource

| Field | Value |
|-------|-------|
| **Prompt** | `Show me all configured Tempo backends with health status.` |
| **Resource** | `tempo://system/backends` |
| **Internal action** | Returns JSON with all backends. Same data as `tempo_list_backends`. |

---

## Phase 2: Detailed Backend Profile

### Step 2.1: Get Backend Details

| Field | Value |
|-------|-------|
| **Prompt** | `Show me the detailed profile for the "default" Tempo backend.` |
| **Tool** | `tempo_get_backend` |
| **Parameters** | `{"backend_id": "default"}` |
| **Internal action** | Probes health, fetches build info, checks capabilities. |
| **Expected output** | `{"id": "default", "health": "ready", "version": "2.7.x", "build_info": {"branch": "main", "revision": "abc123"}, "deployment_mode": "unknown", "multi_tenant": false, "default_tenant": null, "capabilities": {...}}` |

### Step 2.2: Read Backend Detail Resource

| Field | Value |
|-------|-------|
| **Prompt** | `Show me the detailed profile for the "default" backend via resource.` |
| **Resource** | `tempo://system/backends/default` |

---

## Phase 3: Comprehensive Diagnostics

### Step 3.1: Full Health Check

| Field | Value |
|-------|-------|
| **Prompt** | `Run comprehensive diagnostics on the "default" Tempo backend.` |
| **Tool** | `tempo_get_diagnostics` |
| **Parameters** | `{"backend_id": "default"}` |
| **Internal action** | (1) Health check: `GET /ready`. (2) Build info: `GET /api/status/buildinfo`. (3) Service status: `GET /status/services` — checks component statuses (query-frontend, querier, ingester, etc.). (4) Ring checks (per deployment mode). (5) Aggregates findings with severity ranking. |
| **Expected output** | `{"status": "healthy", "ready": true, "deployment_mode": "unknown", "build_info": {"version": "2.7.x", ...}, "services": {"query-frontend": "Running", "querier": "Running", "compactor": "Running", ...}, "rings": {...}, "findings": [], "issues": 0}` |

**What to check:**

| Field | What to Verify |
|-------|----------------|
| `status` | Overall health: `"healthy"`, `"degraded"`, or `"unhealthy"` |
| `services` | All services should be `"Running"` |
| `findings` | Severity-ranked list of issues with suggested remediation |
| `issues` | Count of warnings + critical findings |

**Findings severity levels:**

| Severity | Meaning | Example |
|----------|---------|---------|
| `critical` | Backend is non-functional | Readiness probe failed |
| `warning` | Degraded but functional | One ring member unhealthy |
| `info` | Informational | Deployment mode not configured |

---

## Phase 4: Attribute Taxonomy

### Step 4.1: All Attributes (All Scopes)

| Field | Value |
|-------|-------|
| **Prompt** | `What trace attributes are available across all scopes in the last hour?` |
| **Tool** | `tempo_get_attribute_names` |
| **Parameters** | `{"backend_id": "default", "since": "1h"}` |
| **Internal action** | Calls `GET /api/v2/search/tags`. Returns attributes grouped by scope. |
| **Expected output** | `{"scopes": {"resource": [...], "span": [...], "intrinsic": [...]}, "total_attributes": N}` |

### Step 4.2: Resource Attributes Only

| Field | Value |
|-------|-------|
| **Prompt** | `Show me resource-scoped attributes only.` |
| **Tool** | `tempo_get_attribute_names` |
| **Parameters** | `{"backend_id": "default", "scope": "resource", "since": "1h"}` |

### Step 4.3: Span Attributes Only

| Field | Value |
|-------|-------|
| **Prompt** | `Show me span-scoped attributes.` |
| **Tool** | `tempo_get_attribute_names` |
| **Parameters** | `{"backend_id": "default", "scope": "span", "since": "1h"}` |

### Expected Attribute Inventory (OTel Demo)

| Scope | Expected Attributes |
|-------|---------------------|
| **resource** | `service.name`, `k8s.namespace.name`, `k8s.deployment.name`, `k8s.pod.name`, `k8s.container.name`, `k8s.node.name`, `telemetry.sdk.language`, `telemetry.sdk.version` |
| **span** | `http.method`, `http.status_code`, `http.url`, `rpc.method`, `rpc.service`, `rpc.system`, `db.statement`, `db.system`, `net.peer.name`, `net.peer.port` |
| **intrinsic** | `duration`, `name`, `status`, `kind`, `rootName`, `rootServiceName`, `traceDuration`, `span:childCount` |

---

## Phase 5: Service & Namespace Inventory

### Step 5.1: All Services

| Field | Value |
|-------|-------|
| **Prompt** | `What services are sending traces to Tempo?` |
| **Tool** | `tempo_get_attribute_values` |
| **Parameters** | `{"backend_id": "default", "attribute": "resource.service.name", "since": "1h"}` |
| **Expected output** | `{"tag": "resource.service.name", "tag_values": [{"value": "ad"}, {"value": "cart"}, {"value": "checkout"}, {"value": "currency"}, {"value": "email"}, {"value": "frontend"}, {"value": "frontend-proxy"}, {"value": "kafka"}, {"value": "load-generator"}, {"value": "payment"}, {"value": "product-catalog"}, {"value": "quote"}, {"value": "recommendation"}, {"value": "shipping"}]}` |

### Step 5.2: All Namespaces

| Field | Value |
|-------|-------|
| **Prompt** | `What namespaces exist in the trace data?` |
| **Tool** | `tempo_get_attribute_values` |
| **Parameters** | `{"backend_id": "default", "attribute": "resource.k8s.namespace.name", "since": "1h"}` |

### Step 5.3: HTTP Methods

| Field | Value |
|-------|-------|
| **Prompt** | `What HTTP methods exist in the span data?` |
| **Tool** | `tempo_get_attribute_values` |
| **Parameters** | `{"backend_id": "default", "attribute": "span.http.method", "since": "1h"}` |

### Step 5.4: Span Kinds

| Field | Value |
|-------|-------|
| **Prompt** | `What span kinds are present?` |
| **Tool** | `tempo_get_attribute_values` |
| **Parameters** | `{"backend_id": "default", "attribute": "kind", "since": "1h"}` |

---

## Phase 6: K8s Attribute Mapping

### Step 6.1: Get Canonical Mapping with Live Validation

| Field | Value |
|-------|-------|
| **Prompt** | `Show me the K8s-to-Tempo attribute mapping and validate against the live backend.` |
| **Tool** | `tempo_get_k8s_attribute_map` |
| **Parameters** | `{"backend_id": "default"}` |
| **Internal action** | Returns the canonical K8s → OTel attribute mapping. Validates each attribute against the live backend's tag list to confirm which are present. |
| **Expected output** | `{"mapping": [{"k8s_concept": "Namespace", "otel_attribute": "k8s.namespace.name", "tempo_filter": "resource.k8s.namespace.name", "available": true}, ...]}` |

**What to check:**

| Field | What to Verify |
|-------|----------------|
| `mapping[i].available` | `true` = attribute exists in the backend's data |
| `mapping[i].tempo_filter` | Use this exact string in your TraceQL queries |

### Step 6.2: Read K8s Reference Resource

| Field | Value |
|-------|-------|
| **Prompt** | `Show me the K8s attribute reference table.` |
| **Resource** | `tempo://reference/k8s-attributes` |

---

## Phase 7: Query Policies & Deployment Topology

### Step 7.1: Get Query Policies

| Field | Value |
|-------|-------|
| **Prompt** | `What are the current query guardrails?` |
| **Tool** | `tempo_get_query_policies` |
| **Parameters** | `{"backend_id": "default"}` |
| **Expected output** | `{"max_lookback": "168h", "default_search_limit": 20, "max_search_limit": 100, "default_spss": 3, "max_spss": 10, "require_time_range": true, "require_filter_or_query": true}` |

### Step 7.2: Read Deployment Overview

| Field | Value |
|-------|-------|
| **Prompt** | `Show me the Tempo deployment topology.` |
| **Resource** | `tempo://deployment/overview` |
| **Internal action** | Returns deployment configuration: number of backends, modes, tenants, K8s integration status. |
| **Expected output** | `{"total_backends": 1, "backends": [{"id": "default", "type": "tempo", "deployment_mode": "unknown", "multi_tenant": false, "base_url": "http://localhost:3200"}], "kubernetes_enabled": false}` |

### Step 7.3: Read Query Policies Resource

| Field | Value |
|-------|-------|
| **Prompt** | `Show me the query guardrails resource.` |
| **Resource** | `tempo://reference/query-policies` |

---

## Integration Readiness Checklist

After completing this phase, an integrating agent (e.g., k8s-autopilot) has the following context:

| Context | Source | Data |
|---------|--------|------|
| Backend ID | `tempo_list_backends` | `"default"` |
| Backend health | `tempo_get_diagnostics` | `"healthy"` |
| Multi-tenant? | `tempo_get_backend` | `false` |
| Available services | `tempo_get_attribute_values` | 14+ services in `otel-demo` |
| K8s attribute map | `tempo_get_k8s_attribute_map` | Namespace, Pod, Deployment → TraceQL filters |
| Query limits | `tempo_get_query_policies` | Max lookback: 168h, Max limit: 100 |
| Deployment mode | `tempo://deployment/overview` | Monolithic/microservices/unknown |

---

## Phase Summary

At the end of this phase, you've:

| What | Tool / Resource | Status |
|------|----------------|--------|
| ✅ Backends discovered | `tempo_list_backends` | All backends listed with health |
| ✅ Backend profiled | `tempo_get_backend` | Version, capabilities, tenant config known |
| ✅ Diagnostics run | `tempo_get_diagnostics` | Full health check with findings |
| ✅ Attribute taxonomy built | `tempo_get_attribute_names` | All scopes: resource, span, intrinsic |
| ✅ Service inventory complete | `tempo_get_attribute_values` | All services and namespaces enumerated |
| ✅ K8s mapping validated | `tempo_get_k8s_attribute_map` | K8s concepts → TraceQL with live validation |
| ✅ Query policies understood | `tempo_get_query_policies` | Guardrails and limits known |
| ✅ Deployment topology mapped | `tempo://deployment/overview` | Backends, modes, tenants, K8s status |

**Next step →** [Service Topology & Alerting](TEMPO_TOPOLOGY_ALERTING_TEST_GUIDE.md): Map service dependencies, generate alerting expressions, and manage Tempo Operator CRDs.
