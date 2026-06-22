# Missing Traces Diagnostic Test Guide — Tempo MCP Server (OTel Demo)

**Phase 3 of 7** in the Tempo end-to-end journey.
**Previous phase**: [Latency Investigation](TEMPO_LATENCY_INVESTIGATION_TEST_GUIDE.md)
**Next phase**: [TraceQL Query Builder](TEMPO_TRACEQL_BUILDER_TEST_GUIDE.md)

> You're expecting to see traces from the `payment` service but searches return nothing.
> This phase walks through a systematic diagnostic: verify backend health, confirm
> data ingestion, broaden searches, check attribute names, and consult the runbook.
>
> **Target service**: `payment` — JavaScript payment processing service.

---

## Prerequisites (Completed in Phase 2)

| Component | Status |
|-----------|--------|
| ✅ Tempo backend accessible | `tempo_get_diagnostics` — healthy |
| ✅ Metrics-generator working | `tempo_traceql_metrics_range` — time series returned |
| ✅ Search works for other services | `tempo_traceql_search` — traces found for `checkout`, `frontend` |
| ✅ Trace comparison working | `tempo_compare_traces` — diff returned |

---

## The Starting Point

Phase 2 investigated latency. Now you're facing a different problem: no traces found. This can happen for many reasons — wrong service name, wrong tenant, expired retention, pipeline issues, or backend problems.

You need to answer:

1. **Is Tempo healthy?** — Rule out backend issues.
2. **Is data being ingested at all?** — Check if attributes exist.
3. **Can I find any traces?** — Broadest possible search.
4. **Is the service name correct?** — Check attribute values.
5. **Is this a multi-tenant or retention issue?** — Check tenant/time range.

---

## Phase 1: Verify Backend Health

### Step 1.1: Run Full Diagnostics

| Field | Value |
|-------|-------|
| **Prompt** | `Run comprehensive diagnostics on the "default" Tempo backend.` |
| **Tool** | `tempo_get_diagnostics` |
| **Parameters** | `{"backend_id": "default"}` |
| **Internal action** | (1) Health probe: `GET /ready`. (2) Build info: `GET /api/status/buildinfo`. (3) Service status: `GET /status/services`. (4) Ring checks (per deployment mode). Aggregates into severity-ranked findings. |
| **Expected output** | `{"status": "healthy", "ready": true, "build_info": {"version": "2.7.x", "goVersion": "go1.23.x"}, "services": {"query-frontend": "Running", "querier": "Running", ...}, "findings": [], "issues": 0}` |

**What to check:**

| Outcome | Meaning | Next Action |
|---------|---------|-------------|
| `status: "healthy"`, `ready: true` | ✅ Backend is fine | Proceed to Phase 2 |
| `status: "degraded"` | ⚠️ Some components unhealthy | Check `findings` for details |
| `status: "unhealthy"`, `ready: false` | ❌ Tempo is down | Fix Tempo before continuing |
| `findings` contains ring errors | ⚠️ Likely behind a gateway | Set `TEMPO_DEPLOYMENT_MODE=unknown` |

### Step 1.2: Check Backend Details

| Field | Value |
|-------|-------|
| **Prompt** | `Show me the detailed profile for the "default" Tempo backend.` |
| **Tool** | `tempo_get_backend` |
| **Parameters** | `{"backend_id": "default"}` |
| **Internal action** | Returns backend health, version, build info, capabilities, deployment mode, tenant config. |

**What to check:**
- `multi_tenant` — is the backend multi-tenant? If yes, you need a `tenant` parameter.
- `default_tenant` — if set, this is auto-injected.

---

## Phase 2: Verify Data Exists

### Step 2.1: Check Available Attributes

| Field | Value |
|-------|-------|
| **Prompt** | `What trace attributes are available in Tempo for the last hour?` |
| **Tool** | `tempo_get_attribute_names` |
| **Parameters** | `{"backend_id": "default", "since": "1h"}` |
| **Internal action** | Calls `GET /api/v2/search/tags` with time range. Returns attributes grouped by scope. |
| **Expected output** | `{"scopes": {"resource": ["service.name", "k8s.namespace.name", ...], "span": ["http.method", "http.status_code", ...], "intrinsic": ["duration", "name", "status", ...]}}` |

**What to check:**

| Outcome | Meaning | Next Action |
|---------|---------|-------------|
| Attributes returned | ✅ Data is being ingested | Proceed to Phase 3 |
| Empty or error | ❌ No data in the time window | Broaden to `since="24h"` or `since="7d"` |
| `service.name` missing from resource | ⚠️ OTel Collector not enriching resource attributes | Check Collector config |

### Step 2.2: Broaden Time Range (If Empty)

| Field | Value |
|-------|-------|
| **Prompt** | `Check attributes with a 7-day lookback.` |
| **Tool** | `tempo_get_attribute_names` |
| **Parameters** | `{"backend_id": "default", "since": "7d"}` |

---

## Phase 3: Broadest Possible Search

### Step 3.1: Search for ANY Traces

| Field | Value |
|-------|-------|
| **Prompt** | `Find any traces in the last 24 hours — no filters at all.` |
| **Tool** | `tempo_traceql_search` |
| **Parameters** | `{"backend_id": "default", "since": "24h", "limit": 5}` |
| **Internal action** | Minimal query: `{ }`. Note: `TEMPO_REQUIRE_FILTER_OR_QUERY` must be `false` for this, otherwise the server requires at least one filter. If blocked, use `query="{ duration > 0ns }"` as a workaround. |

**What to check:**

| Outcome | Meaning | Next Action |
|---------|---------|-------------|
| Traces returned | ✅ Data exists — issue is with your specific filters | Proceed to Phase 4 |
| No traces at all | ❌ No data ingested in the time window | Check OTel Collector → Tempo pipeline |
| Error: "filter required" | ⚠️ Guardrail active | Try `query="{ duration > 0ns }"` instead |

---

## Phase 4: Check Service Names

### Step 4.1: List All Service Names

| Field | Value |
|-------|-------|
| **Prompt** | `What services are sending traces to Tempo?` |
| **Tool** | `tempo_get_attribute_values` |
| **Parameters** | `{"backend_id": "default", "attribute": "resource.service.name", "since": "1h"}` |
| **Internal action** | Calls `GET /api/v2/search/tag/resource.service.name/values`. Returns distinct values. |
| **Expected output** | `{"tag": "resource.service.name", "tag_values": [{"value": "ad"}, {"value": "cart"}, {"value": "checkout"}, {"value": "currency"}, {"value": "email"}, {"value": "frontend"}, {"value": "frontend-proxy"}, {"value": "payment"}, ...]}` |

**What to check:**

| Outcome | Meaning | Next Action |
|---------|---------|-------------|
| `"payment"` in the list | ✅ Service exists — check your query spelling | Ensure exact match in your TraceQL |
| `"payment-service"` instead of `"payment"` | ⚠️ Name mismatch | Use the correct name from this list |
| Service not in the list at all | ❌ Service not instrumented or not sending traces | Check OTel SDK setup for that service |

### Step 4.2: Check Namespace Values

| Field | Value |
|-------|-------|
| **Prompt** | `What namespaces exist in the trace data?` |
| **Tool** | `tempo_get_attribute_values` |
| **Parameters** | `{"backend_id": "default", "attribute": "resource.k8s.namespace.name", "since": "1h"}` |

---

## Phase 5: Check Multi-Tenancy and Retention

### Step 5.1: Check Backend Tenant Configuration

| Field | Value |
|-------|-------|
| **Prompt** | `Show me the "default" backend profile — is it multi-tenant?` |
| **Tool** | `tempo_get_backend` |
| **Parameters** | `{"backend_id": "default"}` |

**Decision tree:**

| Situation | Fix |
|-----------|-----|
| `multi_tenant: true` but no `tenant` in your queries | Add `tenant` parameter to all tool calls |
| `multi_tenant: true` and you're using the wrong tenant ID | Check with your admin for the correct tenant |
| `multi_tenant: false` | Tenant is not the issue — continue |

### Step 5.2: Consult Cross-Tenant Runbook

| Field | Value |
|-------|-------|
| **Prompt** | `Show me the cross-tenant access configuration guide.` |
| **Resource** | `tempo://runbooks/cross-tenant-access` |

### Step 5.3: Consult No-Traces Runbook

| Field | Value |
|-------|-------|
| **Prompt** | `Show me the runbook for troubleshooting missing traces.` |
| **Resource** | `tempo://runbooks/no-traces-found` |
| **Content** | Diagnostic steps: backend health, attribute existence, time range, filters, tenant, ingestion, retention |

---

## Phase 6: Verify Ingestion Pipeline

### Step 6.1: Try Direct Trace Retrieval (If You Have a Known Trace ID)

| Field | Value |
|-------|-------|
| **Prompt** | `Get trace abc123def456789012345678abcdef01 — I know this trace exists.` |
| **Tool** | `tempo_get_trace` |
| **Parameters** | `{"backend_id": "default", "trace_id": "abc123def456789012345678abcdef01"}` |

**What to check:**

| Outcome | Meaning |
|---------|---------|
| Trace returned | ✅ Tempo has data — search index may need time to catch up |
| 404 Not Found | Trace doesn't exist — either expired or never ingested |
| Connection error | Backend connectivity issue |

---

## Diagnostic Summary Matrix

| Check | Tool | Passes? | Root Cause |
|-------|------|---------|------------|
| Backend healthy | `tempo_get_diagnostics` | If no → Tempo is down |
| Attributes exist | `tempo_get_attribute_names` | If no → No data ingested |
| Any traces found | `tempo_traceql_search(since="24h")` | If no → Pipeline or retention issue |
| Service name exists | `tempo_get_attribute_values(attribute="resource.service.name")` | If no → Service not instrumented |
| Service name matches | Compare query service with attribute values | If no → Typo in service name |
| Tenant correct | `tempo_get_backend` multi_tenant check | If wrong → Wrong tenant ID |
| Time range OK | Broaden to `24h` or `7d` | If still no → Data outside retention |

---

## Phase Summary

At the end of this phase, you've:

| What | Tool / Resource | Status |
|------|----------------|--------|
| ✅ Backend health verified | `tempo_get_diagnostics`, `tempo_get_backend` | Backend is healthy |
| ✅ Data existence confirmed | `tempo_get_attribute_names` | Attributes present = data ingested |
| ✅ Broadest search attempted | `tempo_traceql_search(since="24h")` | Traces exist in the system |
| ✅ Service name validated | `tempo_get_attribute_values` | Correct service name identified |
| ✅ Tenant/retention checked | `tempo_get_backend`, runbooks | Multi-tenancy and retention verified |

**Next step →** [TraceQL Query Builder](TEMPO_TRACEQL_BUILDER_TEST_GUIDE.md): Build TraceQL queries from natural language intent — discover attributes, consult references, and execute.
