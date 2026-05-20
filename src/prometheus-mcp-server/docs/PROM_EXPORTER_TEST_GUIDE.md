# Exporter Test Guide — Prometheus MCP Server

**Target workflow**: Exporter Lifecycle Management
**Tool tested**: `prom_recommend_exporter`, `prom_install_exporter`, `prom_verify_exporter`
**Cluster impact**: install/uninstall MUTATE Kubernetes state

---

## 1. Prerequisites

| Component | Status |
|-----------|--------|
| Kubernetes cluster | Accessible via kubeconfig |
| Prometheus MCP Server | Running |
| Target namespace | Exists (e.g. `monitoring`) |

---

## 2. Test Scenarios

### Scenario A: Exporter Discovery

| Step | Action | Tool |
|------|--------|------|
| 1 | List all exporters | `prom_list_exporters()` |
| 2 | Recommend for postgres | `prom_recommend_exporter(service_type="postgres")` |
| 3 | Recommend for kafka | `prom_recommend_exporter(service_type="kafka")` |
| 4 | Recommend for unknown | `prom_recommend_exporter(service_type="custom_db")` |

**Expected**:
- Step 1: Returns 19 exporters with type, description, default_port, image, scope
- Step 2: Returns `postgres_exporter` with port 9187
- Step 3: Returns `kafka_exporter` with port 9308

### Scenario B: Full Install → Verify → Uninstall Lifecycle

| Step | Action | Tool |
|------|--------|------|
| 1 | Install exporter | `prom_install_exporter(exporter_type="postgres_exporter", namespace="monitoring")` |
| 2 | Test endpoint | `prom_test_endpoint(endpoint_url="http://postgres-exporter.monitoring:9187/metrics")` |
| 3 | Apply ServiceMonitor | `prom_apply_servicemonitor(namespace="monitoring", service_name="postgres-exporter")` |
| 4 | Verify end-to-end | `prom_verify_exporter(backend_id="default", endpoint_url="http://postgres-exporter.monitoring:9187/metrics", job="postgres-exporter", verify_timeout=90)` |
| 5 | Uninstall exporter | `prom_uninstall_exporter(exporter_type="postgres_exporter", namespace="monitoring")` |

**Expected**:
- Step 1: Creates Deployment + Service, returns applied_resources list and manifest_yaml
- Step 3: Returns applied ServiceMonitor details
- Step 4: Returns endpoint_check, up_series_found, errors
- Step 5: Removes Deployment/DaemonSet + Service, returns removed_resources list

### Scenario C: Exporters with RBAC (kube-state-metrics)

| Step | Action | Tool |
|------|--------|------|
| 1 | Install | `prom_install_exporter(exporter_type="kube-state-metrics", namespace="monitoring")` |

**Expected**: Creates ServiceAccount + ClusterRole + ClusterRoleBinding + Deployment + Service

### Scenario D: Exporters with ConfigMap (blackbox_exporter)

| Step | Action | Tool |
|------|--------|------|
| 1 | Install | `prom_install_exporter(exporter_type="blackbox_exporter", namespace="monitoring")` |

**Expected**: Creates ConfigMap (mounted at /config) + Deployment + Service

### Scenario E: Custom Service Name Override

| Step | Action | Tool |
|------|--------|------|
| 1 | Install with custom name | `prom_install_exporter(exporter_type="redis_exporter", namespace="monitoring", service_name="cart-cache-exporter")` |
| 2 | Uninstall by custom name | `prom_uninstall_exporter(exporter_type="redis_exporter", namespace="monitoring", service_name="cart-cache-exporter")` |

**Expected**: Resources named `cart-cache-exporter` instead of `redis-exporter`

### Scenario F: Synthetic Endpoint Monitoring (Probes)

| Step | Action | Tool |
|------|--------|------|
| 1 | Install blackbox_exporter | `prom_install_exporter(exporter_type="blackbox_exporter", namespace="monitoring")` |
| 2 | Apply Probe CRD | `prom_apply_probe(targets=["https://talkops.ai"], probe_name="talkops-probe", namespace="monitoring", module="http_2xx", prober_url="blackbox-exporter:9115")` |
| 3 | Verify | `prom_query_instant(backend_id="default", query="probe_success")` |

**Expected**: 
- Step 1: `blackbox_exporter` deployed with default `http_2xx` configuration.
- Step 2: `Probe` CRD applied with correct automatically resolved operator selector labels.
- Step 3: Returns `1` indicating a successful probe of the endpoint.

---

## 3. Natural Language Prompts

```text
Show me all supported Prometheus exporters.
```

```text
What exporter should I use for monitoring PostgreSQL?
```

```text
Deploy the postgres_exporter to the "monitoring" namespace.
```

```text
Verify that the postgres_exporter is healthy and being scraped by Prometheus.
```

```text
Remove the postgres_exporter from the "monitoring" namespace.
```

```text
Deploy kube-state-metrics with full RBAC in the "monitoring" namespace.
```

```text
Set up synthetic monitoring for https://talkops.ai using the blackbox_exporter and a Probe CRD.
```
