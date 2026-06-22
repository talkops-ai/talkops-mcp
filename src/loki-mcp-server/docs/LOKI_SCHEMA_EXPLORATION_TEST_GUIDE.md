# Schema Exploration Test Guide — Loki MCP Server

**Phase 5 of 7** in the Loki end-to-end journey.
**Previous phase**: [LogQL Query Builder](LOKI_LOGQL_BUILDER_TEST_GUIDE.md)
**Next phase**: [Incident Response](LOKI_INCIDENT_RESPONSE_TEST_GUIDE.md)

> After building queries (Phase 4), this phase performs a full schema exploration
> of the Loki cluster — global labels, service inventory, cardinality health
> assessment, log structure analysis, and governance review. This is the recommended
> first workflow when connecting to a new Loki instance.

---

## Prerequisites (Completed in Phase 4)

| Component | Status |
|-----------|--------|
| ✅ Query builder tested | `execute_logql_query` — log and metric queries working |
| ✅ Fields discovered | `get_detected_fields` — field discovery verified |
| ✅ References accessible | `loki://reference/logql` — static resources loading |

---

## The Starting Point

Phase 4 built queries for a single service. Now you want a complete picture of the entire Loki cluster. You need to answer:

1. **What is the label taxonomy?** — All label dimensions across the cluster.
2. **What services exist?** — Complete service inventory.
3. **What namespaces exist?** — Organizational structure.
4. **Is cardinality healthy?** — Any labels at risk of explosion?
5. **What log formats are in use?** — JSON, logfmt, or plain text per service?
6. **Do labels follow governance rules?** — Naming conventions and best practices.

---

## Phase 1: Global Label Taxonomy

### Step 1.1: Discover All Labels

| Field | Value |
|-------|-------|
| **Prompt** | `What labels are available in my Loki cluster?` |
| **Tool** | `get_cluster_labels` |
| **Parameters** | `{}` |
| **Internal action** | Calls `GET /loki/api/v1/labels`. Returns all label names. |
| **Expected output** | `{"labels": ["app", "cluster", "container", "env", "instance", "job", "namespace", "node", "pod", ...], "count": N}` |

**What to check:**

| Category | Expected Labels |
|----------|----------------|
| Service identity | `app`, `service_name`, `job` |
| Infrastructure | `namespace`, `cluster`, `node`, `pod`, `container` |
| Environment | `env`, `environment`, `stage` |
| Custom | Any domain-specific labels your org uses |

### Step 1.2: Time-Scoped Labels

| Field | Value |
|-------|-------|
| **Prompt** | `Show me labels from the last 24 hours only.` |
| **Tool** | `get_cluster_labels` |
| **Parameters** | `{"start": "now-24h", "end": "now"}` |
| **Internal action** | Same as 1.1 but scoped to last 24 hours. Useful for identifying recently added or removed labels. |

---

## Phase 2: Service & Namespace Inventory

### Step 2.1: Service Inventory

| Field | Value |
|-------|-------|
| **Prompt** | `What services are sending logs to Loki?` |
| **Tool** | `get_label_values` |
| **Parameters** | `{"label": "app"}` |
| **Internal action** | Calls `GET /loki/api/v1/label/app/values`. Returns all distinct service names. |
| **Expected output** | `{"label": "app", "values": ["api-gateway", "checkout", "order-service", "payment-service", ...], "count": N}` |

### Step 2.2: Namespace Inventory

| Field | Value |
|-------|-------|
| **Prompt** | `What namespaces exist in Loki?` |
| **Tool** | `get_label_values` |
| **Parameters** | `{"label": "namespace"}` |
| **Expected output** | `{"label": "namespace", "values": ["default", "kube-system", "monitoring", "production", "staging", ...], "count": N}` |

### Step 2.3: Environment Inventory

| Field | Value |
|-------|-------|
| **Prompt** | `What environments exist?` |
| **Tool** | `get_label_values` |
| **Parameters** | `{"label": "env"}` |
| **Expected output** | `{"label": "env", "values": ["dev", "staging", "production"], "count": 3}` |

### Step 2.4: Scoped Service List

| Field | Value |
|-------|-------|
| **Prompt** | `What services are in the production namespace?` |
| **Tool** | `get_label_values` |
| **Parameters** | `{"label": "app", "query": "{namespace=\"production\"}"}` |
| **Internal action** | Returns app values scoped to production namespace only. |

---

## Phase 3: Cardinality Health Assessment

### Step 3.1: Broad Cardinality Check

| Field | Value |
|-------|-------|
| **Prompt** | `Check the cardinality of labels for '{namespace="production"}'.` |
| **Tool** | `get_active_series` |
| **Parameters** | `{"match": "{namespace=\"production\"}"}` |
| **Internal action** | Returns all matching series with per-label cardinality counts and high-cardinality warnings. |
| **Expected output** | `{"total_series": N, "label_cardinality": {"app": 15, "pod": 250, "instance": 300, ...}, "warnings": [...]}` |

**Cardinality assessment table:**

| Label | Unique Values | Assessment |
|-------|--------------|------------|
| `app` | 15 | ✅ Low — safe for stream selectors |
| `namespace` | 5 | ✅ Low — safe |
| `pod` | 250 | ⚠️ Medium — acceptable but monitor |
| `instance` | 300 | ⚠️ Medium — consider structured metadata for high-cardinality filtering |
| `request_id` | 50,000 | ❌ Very high — MUST NOT be used in `{}` selectors. Use `| line_format` or structured metadata. |

### Step 3.2: Service-Level Cardinality

| Field | Value |
|-------|-------|
| **Prompt** | `Check cardinality for a specific service.` |
| **Tool** | `get_active_series` |
| **Parameters** | `{"match": "{app=\"checkout\"}"}` |
| **Internal action** | Returns cardinality for a single service — useful for identifying per-service issues. |

### Step 3.3: Review Guardrails

| Field | Value |
|-------|-------|
| **Prompt** | `What are the current cardinality thresholds?` |
| **Resource** | `loki://config/guardrails` |
| **Internal action** | Returns `high_cardinality_threshold` (default: 10,000) and other limits. |

---

## Phase 4: Log Structure Per Service

### Step 4.1: Representative Service Fields

| Field | Value |
|-------|-------|
| **Prompt** | `What fields are available in "checkout" logs?` |
| **Tool** | `get_detected_fields` |
| **Parameters** | `{"query": "{app=\"checkout\"}"}` |
| **Expected output** | `{"fields": [...], "total_fields": N}` |

### Step 4.2: Compare Formats Across Services

Repeat Step 4.1 for multiple services to build a format inventory:

| Service | Format | Key Fields | Parser |
|---------|--------|------------|--------|
| `checkout` | JSON | `level`, `msg`, `status_code`, `latency_ms` | `| json` |
| `api-gateway` | JSON | `level`, `method`, `path`, `status`, `duration` | `| json` |
| `legacy-service` | Plain text | *(none detected)* | `| pattern` or line filters |

---

## Phase 5: Governance Review

### Step 5.1: Label Governance Guide

| Field | Value |
|-------|-------|
| **Prompt** | `Show me the label governance guide.` |
| **Resource** | `loki://reference/label-governance` |
| **Internal action** | Returns label naming conventions, cardinality rules, and structured metadata guidance. |

### Step 5.2: Best Practices

| Field | Value |
|-------|-------|
| **Prompt** | `Show me Loki best practices.` |
| **Resource** | `loki://reference/best-practices` |
| **Internal action** | Returns cardinality rules, pattern parser vs regex, structured metadata, and pipeline order. |

---

## Phase Summary

At the end of this phase, you've:

| What | Tool / Resource | Status |
|------|----------------|--------|
| ✅ Global label taxonomy mapped | `get_cluster_labels` | All label dimensions known |
| ✅ Service inventory built | `get_label_values(label="app")` | All services catalogued |
| ✅ Namespace inventory built | `get_label_values(label="namespace")` | All namespaces catalogued |
| ✅ Cardinality assessed | `get_active_series` | High-cardinality labels identified |
| ✅ Log formats catalogued | `get_detected_fields` (per service) | Parser per service known |
| ✅ Governance reviewed | `loki://reference/label-governance` | Naming conventions understood |

**Next step →** [Incident Response](LOKI_INCIDENT_RESPONSE_TEST_GUIDE.md): Fast-track error triage during an active incident — skip the leisurely exploration and go straight to execution.
