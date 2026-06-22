# TraceQL Query Builder Test Guide — Tempo MCP Server (OTel Demo)

**Phase 4 of 7** in the Tempo end-to-end journey.
**Previous phase**: [Missing Traces Diagnostic](TEMPO_MISSING_TRACES_TEST_GUIDE.md)
**Next phase**: [Metrics-First Triage (RED)](TEMPO_METRICS_FIRST_TRIAGE_TEST_GUIDE.md)

> After verifying data exists (Phase 3), this phase constructs TraceQL queries
> from natural language intent — discovering available attributes, exploring values,
> consulting syntax references, checking query policies, and executing.
>
> **Target intent**: *"Find all checkout traces that call the payment service and take longer than 1 second"*
> and *"Find error traces with HTTP 500 in the frontend namespace"*.

---

## Prerequisites (Completed in Phase 3)

| Component | Status |
|-----------|--------|
| ✅ Tempo backend healthy | `tempo_get_diagnostics` — healthy |
| ✅ Data ingestion confirmed | `tempo_get_attribute_names` — attributes present |
| ✅ Service names known | `tempo_get_attribute_values` — `checkout`, `frontend`, `payment`, etc. |
| ✅ Broadest search works | `tempo_traceql_search(since="24h")` — traces returned |

---

## The Starting Point

Phase 3 confirmed data exists. Now you want to build a TraceQL query from a natural language request. You need to:

1. **Discover the environment** — what attributes and values exist.
2. **Resolve K8s concepts** — map K8s names to OTel attributes.
3. **Consult references** — use TraceQL syntax guide and examples.
4. **Check guardrails** — know the query limits.
5. **Execute and refine** — run and iterate.

---

## Phase 1: Environment Discovery

### Step 1.1: Discover Span Attributes

| Field | Value |
|-------|-------|
| **Prompt** | `What span-level attributes exist in the last hour?` |
| **Tool** | `tempo_get_attribute_names` |
| **Parameters** | `{"backend_id": "default", "scope": "span", "since": "1h"}` |
| **Internal action** | Calls `GET /api/v2/search/tags` with `scope=span`. Returns span-scoped attribute names. |
| **Expected output** | `{"scope": "span", "attributes": ["http.method", "http.status_code", "http.url", "rpc.method", "rpc.service", "db.statement", "db.system", ...]}` |

### Step 1.2: Discover Resource Attributes

| Field | Value |
|-------|-------|
| **Prompt** | `What resource-level attributes are available?` |
| **Tool** | `tempo_get_attribute_names` |
| **Parameters** | `{"backend_id": "default", "scope": "resource", "since": "1h"}` |
| **Expected output** | `{"scope": "resource", "attributes": ["service.name", "k8s.namespace.name", "k8s.deployment.name", "k8s.pod.name", ...]}` |

### Step 1.3: Explore Service Names

| Field | Value |
|-------|-------|
| **Prompt** | `What services are sending traces?` |
| **Tool** | `tempo_get_attribute_values` |
| **Parameters** | `{"backend_id": "default", "attribute": "resource.service.name", "since": "1h"}` |
| **Internal action** | Calls `GET /api/v2/search/tag/resource.service.name/values`. Returns distinct values. |
| **Expected output** | `{"tag": "resource.service.name", "tag_values": [{"value": "ad"}, {"value": "cart"}, {"value": "checkout"}, ...]}` |

### Step 1.4: Explore HTTP Methods

| Field | Value |
|-------|-------|
| **Prompt** | `What HTTP methods exist in the trace data?` |
| **Tool** | `tempo_get_attribute_values` |
| **Parameters** | `{"backend_id": "default", "attribute": "span.http.method", "since": "1h"}` |
| **Expected output** | `{"tag": "span.http.method", "tag_values": [{"value": "GET"}, {"value": "POST"}, {"value": "PUT"}, ...]}` |

---

## Phase 2: K8s Attribute Resolution

### Step 2.1: Get K8s-to-Tempo Mapping

| Field | Value |
|-------|-------|
| **Prompt** | `Show me the Kubernetes-to-Tempo attribute mapping and validate against the live backend.` |
| **Tool** | `tempo_get_k8s_attribute_map` |
| **Parameters** | `{"backend_id": "default"}` |
| **Internal action** | Returns the canonical K8s → OTel mapping. If `backend_id` is provided, validates which attributes exist in the live backend's tag list. |
| **Expected output** | `{"mapping": [{"k8s_concept": "Namespace", "otel_attribute": "k8s.namespace.name", "tempo_filter": "resource.k8s.namespace.name", "available": true}, {"k8s_concept": "Pod", "otel_attribute": "k8s.pod.name", ...}]}` |

**Use this to translate K8s concepts into TraceQL:**
- "otel-demo namespace" → `resource.k8s.namespace.name = "otel-demo"`
- "checkout deployment" → `resource.k8s.deployment.name = "checkout"`
- "checkout service" → `resource.service.name = "checkout"`

---

## Phase 3: Reference Consultation

### Step 3.1: TraceQL Syntax Reference

| Field | Value |
|-------|-------|
| **Prompt** | `Show me the TraceQL syntax reference.` |
| **Resource** | `tempo://reference/traceql` |
| **Content** | Full syntax: selectors, intrinsics, scoped attributes, operators, structural queries, nil checks, examples. |

### Step 3.2: Common Query Examples

| Field | Value |
|-------|-------|
| **Prompt** | `Show me common TraceQL query examples.` |
| **Resource** | `tempo://examples/common-queries` |
| **Content** | Service exploration, error investigation, performance analysis, structural queries, metrics queries. |

### Step 3.3: K8s Attribute Reference

| Field | Value |
|-------|-------|
| **Prompt** | `Show me the K8s attribute reference.` |
| **Resource** | `tempo://reference/k8s-attributes` |
| **Content** | Table: K8s Concept | OTel Attribute | Example values |

### TraceQL Query Construction (OTel Demo)

Using the discovered attributes and references, construct queries:

| Intent | TraceQL |
|--------|---------|
| All checkout traces | `{ resource.service.name = "checkout" }` |
| Checkout errors | `{ resource.service.name = "checkout" && status = error }` |
| Slow checkout (> 1s) | `{ resource.service.name = "checkout" && duration > 1s }` |
| HTTP 500 in frontend | `{ resource.service.name = "frontend" && span.http.status_code >= 500 }` |
| Frontend → checkout structural | `{ resource.service.name = "frontend" } >> { resource.service.name = "checkout" }` |
| Slow checkout calling payment | `{ resource.service.name = "checkout" } >> { resource.service.name = "payment" && duration > 500ms }` |
| Errors in otel-demo namespace | `{ resource.k8s.namespace.name = "otel-demo" && status = error }` |
| Missing HTTP status code | `{ resource.service.name = "frontend" && span.http.status_code = nil }` |
| Leaf spans only (actual work) | `{ span:childCount = 0 && duration > 200ms }` |

---

## Phase 4: Check Query Policies

### Step 4.1: Get Current Guardrails

| Field | Value |
|-------|-------|
| **Prompt** | `What are the current query guardrails?` |
| **Tool** | `tempo_get_query_policies` |
| **Parameters** | `{"backend_id": "default"}` |
| **Internal action** | Returns the configured query policy for the backend. |
| **Expected output** | `{"max_lookback": "168h", "default_search_limit": 20, "max_search_limit": 100, "default_spss": 3, "max_spss": 10, "require_time_range": true, "require_filter_or_query": true}` |

**What to check:**

| Policy | Impact on Query Building |
|--------|------------------------|
| `max_lookback` | Can't query beyond this (default 168h = 7 days) |
| `default_search_limit` | Results capped at this unless you specify `limit` |
| `max_search_limit` | Absolute maximum traces per search |
| `require_time_range` | Must provide `since` parameter |
| `require_filter_or_query` | Must have at least one filter or TraceQL query |

---

## Phase 5: Execute and Refine

### Step 5.1: Execute — Slow Checkout Calling Payment

| Field | Value |
|-------|-------|
| **Prompt** | `Find checkout traces that call payment and take longer than 1 second.` |
| **Tool** | `tempo_traceql_search` |
| **Parameters** | `{"backend_id": "default", "query": "{ resource.service.name = \"checkout\" } >> { resource.service.name = \"payment\" && duration > 1s }", "since": "1h"}` |
| **Internal action** | Validates TraceQL (structural `>>` operator). Resolves time range. Enforces limits. Calls `GET /api/search`. |

### Step 5.2: Execute — HTTP 500 in Frontend

| Field | Value |
|-------|-------|
| **Prompt** | `Find error traces with HTTP 500 status codes in the frontend.` |
| **Tool** | `tempo_traceql_search` |
| **Parameters** | `{"backend_id": "default", "query": "{ resource.service.name = \"frontend\" && span.http.status_code >= 500 }", "since": "1h"}` |

### Step 5.3: Execute — Using K8s-Friendly Filters

| Field | Value |
|-------|-------|
| **Prompt** | `Find error traces from checkout in the otel-demo namespace.` |
| **Tool** | `tempo_traceql_search` |
| **Parameters** | `{"backend_id": "default", "service": "checkout", "namespace": "otel-demo", "status": "error", "since": "1h"}` |
| **Internal action** | Auto-translates K8s-friendly filters to TraceQL: `{ resource.service.name = "checkout" && resource.k8s.namespace.name = "otel-demo" && status = error }` |

### Step 5.4: Refine If No Results

If a query returns zero results, systematically broaden:

| Attempt | Change | Why |
|---------|--------|-----|
| 1st | Remove the most specific filter | Structural queries or attribute filters may be too narrow |
| 2nd | Broaden duration threshold | Increase from `> 1s` to `> 500ms` |
| 3rd | Remove all filters except service name | Verify base data exists for the service |
| 4th | Broaden time range to `since="24h"` | Data may be outside the window |
| 5th | Check attribute values | Verify spellings via `tempo_get_attribute_values` |

---

## Phase Summary

At the end of this phase, you've:

| What | Tool / Resource | Status |
|------|----------------|--------|
| ✅ Attributes discovered | `tempo_get_attribute_names` (span + resource scopes) | Available attributes known |
| ✅ Values explored | `tempo_get_attribute_values` | Service names, HTTP methods, etc. |
| ✅ K8s mapping resolved | `tempo_get_k8s_attribute_map` | K8s concepts → TraceQL attributes |
| ✅ References consulted | `tempo://reference/traceql`, `tempo://examples/common-queries` | Syntax and patterns available |
| ✅ Policies checked | `tempo_get_query_policies` | Guardrails understood |
| ✅ Queries executed | `tempo_traceql_search` | Structural, filtered, and K8s-friendly queries working |

**Next step →** [Metrics-First Triage (RED)](TEMPO_METRICS_FIRST_TRIAGE_TEST_GUIDE.md): RED analysis (Rate, Errors, Duration) with cross-pillar pivots from metrics to traces and logs to traces.
