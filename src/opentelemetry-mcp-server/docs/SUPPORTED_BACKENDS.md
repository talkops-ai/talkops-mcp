# Supported Telemetry Backends

This document lists all telemetry backends that the `otel_provision_collector` tool can auto-discover and generate exporter configs for.

---

## Auto-Discovery

When you call `otel_provision_collector` **without** specifying `exporter_targets`, the tool automatically scans Kubernetes services in the target namespace (plus well-known observability namespaces like `monitoring`, `observability`, `opentelemetry`) to find backends.

Discovery works by matching **service names** against known patterns. For example, a K8s Service named `jaeger` or `my-jaeger-query` in the `otel-demo` namespace will be detected as a traces backend.

---

## Traces Backends

| Backend | Service Name Pattern | Exporter Type | Default Port | Protocol | Notes |
|---------|---------------------|---------------|-------------|----------|-------|
| **Jaeger** | `jaeger` | `otlp` (gRPC) | `4317` | gRPC | Native OTLP ingestion (Jaeger 1.35+) |
| **Grafana Tempo** | `tempo` | `otlp` (gRPC) | `4317` | gRPC | Tempo's OTLP gRPC endpoint |
| **Zipkin** | `zipkin` | `zipkin` | `9411` | HTTP | Zipkin-native protocol |

### Example Generated Exporter Config (Jaeger)

```yaml
exporters:
  otlp/traces:
    endpoint: jaeger:4317
    tls:
      insecure: true
```

### Example Generated Exporter Config (Tempo)

```yaml
exporters:
  otlp/traces:
    endpoint: tempo:4317
    tls:
      insecure: true
```

---

## Metrics Backends

| Backend | Service Name Pattern | Exporter Type | Default Port | Protocol | Notes |
|---------|---------------------|---------------|-------------|----------|-------|
| **Prometheus** | `prometheus` | `otlphttp` | `9090` | HTTP | Uses `/api/v1/otlp` path for remote write |
| **Thanos** | `thanos` | `otlphttp` | `9090` | HTTP | Thanos receive endpoint |
| **Grafana Mimir** | `mimir` | `otlphttp` | `9009` | HTTP | Mimir's OTLP endpoint |
| **VictoriaMetrics** | `victoriametrics` | `otlphttp` | `8428` | HTTP | VM's OTLP HTTP endpoint |

### Example Generated Exporter Config (Prometheus)

```yaml
exporters:
  otlphttp/metrics:
    endpoint: http://prometheus:9090/api/v1/otlp
    tls:
      insecure: true
```

---

## Logs Backends

| Backend | Service Name Pattern | Exporter Type | Default Port | Protocol | Notes |
|---------|---------------------|---------------|-------------|----------|-------|
| **OpenSearch** | `opensearch` | `opensearch` | `9200` | HTTP | Writes to `otel-logs` index |
| **Elasticsearch** | `elasticsearch` | `elasticsearch` | `9200` | HTTP | Writes to `otel-logs` index |
| **Grafana Loki** | `loki` | `loki` | `3100` | HTTP | Loki-native protocol |

### Example Generated Exporter Config (Loki)

```yaml
exporters:
  loki:
    endpoint: http://loki:3100/loki/api/v1/push
```

> [!NOTE]
> The `/loki/api/v1/push` path suffix is **automatically appended** by the config builder. If you provide the full path in `exporter_targets`, it will not be duplicated.

### Example Generated Exporter Config (OpenSearch)

```yaml
exporters:
  opensearch:
    http:
      endpoint: http://opensearch:9200
      tls:
        insecure: true
    logs_index: otel-logs
```

---

## Exporter Overrides

The `exporter_overrides` parameter lets you inject per-exporter configuration (headers, TLS, auth) without modifying the auto-generated config. Keys are exporter type names, values are config dicts that are deep-merged into the generated exporter.

### Multi-Tenant Loki Authentication

When Loki runs with `auth_enabled: true` (multi-tenant mode), every push request must include an `X-Scope-OrgID` header:

```python
otel_provision_collector(
    namespace="my-namespace",
    signals=["logs"],
    exporter_overrides={
        "loki": {
            "headers": {"X-Scope-OrgID": "my-tenant"}
        }
    },
    dry_run=True,
)
```

This generates:

```yaml
exporters:
  loki:
    endpoint: http://loki:3100/loki/api/v1/push
    headers:
      X-Scope-OrgID: my-tenant
```

### Other Examples

```python
# Custom TLS for Prometheus
exporter_overrides={
    "otlphttp": {"tls": {"ca_file": "/etc/ssl/ca.pem"}}
}

# Elasticsearch authentication
exporter_overrides={
    "elasticsearch": {"user": "elastic", "password": "secret"}
}

# Bearer token for OTLP gRPC (Tempo, Jaeger)
exporter_overrides={
    "otlp": {"headers": {"Authorization": "Bearer <token>"}}
}
```

### Supported Exporter Type Keys

| Key | Applies To |
|-----|------------|
| `loki` | Loki exporter |
| `otlphttp` | Prometheus and other OTLP HTTP exporters |
| `otlp` | Default OTLP gRPC exporters (Tempo, Jaeger) |
| `opensearch` | OpenSearch exporter |
| `elasticsearch` | Elasticsearch exporter |

---

## Fallback Behavior

If no backend is found for a signal, the tool uses the **debug exporter** (logs telemetry to stdout) and emits a warning:

```
⚠️ No backend found for 'logs' — using debug exporter (stdout only).
Specify exporter_targets to route to a real backend.
```

---

## Manual Override

You can bypass auto-discovery entirely by specifying `exporter_targets`:

```python
otel_provision_collector(
    namespace="my-namespace",
    signals=["traces", "metrics", "logs"],
    exporter_targets={
        "traces": "tempo.monitoring:4317",
        "metrics": "http://prometheus.monitoring:9090",
        "logs": "http://loki.monitoring:3100"
    },
    # Optional: add auth headers for multi-tenant backends
    exporter_overrides={
        "loki": {"headers": {"X-Scope-OrgID": "my-tenant"}}
    },
    dry_run=True
)
```

This is useful when:
- Backends are in a different namespace than the defaults scanned
- You're using a cloud-hosted backend (Grafana Cloud, etc.)
- Service names don't match the auto-discovery patterns

---

## Port Selection Priority

When auto-discovering backends, the tool selects the correct port from Kubernetes Services using a priority-based approach:

1. **Exact match**: If the backend's default OTLP port (e.g., `4317`) exists in the service's port list, it is used directly
2. **OTLP port name**: Looks for ports named `otlp-grpc`, `otlp-http`, `otlp`, etc.
3. **Protocol hint**: Matches port names containing the protocol keyword (`grpc`, `http`)
4. **Fallback**: Uses the first port in the service definition

This prevents issues like selecting Jaeger's Zipkin-compatibility port (`9411`) instead of its native OTLP port (`4317`) when both are exposed.

---

## Adding New Backends

To add support for a new backend, add an entry to the `_BACKEND_PATTERNS` list in [`collector_config_builder.py`](../opentelemetry_mcp_server/services/collector_config_builder.py):

```python
# Format: (service_name_pattern, signal, exporter_type, default_port, protocol)
("signoz", "traces", "otlp", 4317, "grpc"),
```

If the new backend requires a custom exporter config format (beyond `otlp`, `otlphttp`), also update the `_build_exporters()` method to handle the new exporter type.
