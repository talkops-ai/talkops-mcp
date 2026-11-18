# Manual SDK Quickstart & Kubernetes Downward API Integration

## Table of Contents

1. [When to Choose Manual SDK Instrumentation](#1-when-to-choose-manual-sdk-instrumentation)
2. [Kubernetes Downward API Resource Attributes](#2-kubernetes-downward-api-resource-attributes)
3. [Rust OpenTelemetry SDK Pattern](#3-rust-opentelemetry-sdk-pattern)
4. [C++ OpenTelemetry SDK Pattern](#4-c-opentelemetry-sdk-pattern)
5. [Custom Business Spans & Baggage Propagation](#5-custom-business-spans--baggage-propagation)

---

## 1. When to Choose Manual SDK Instrumentation

Use manual OpenTelemetry SDK integration when:
- The workload is written in a compiled language without Operator auto-instrumentation webhook support (**Rust**, **C++**, **Swift**), and kernel eBPF zero-code instrumentation (OBI) is either unavailable or insufficient for custom application spans.
- High-throughput financial, gaming, or HFT services require zero reflection overhead and deterministic span allocation.
- Domain-specific attributes (e.g., `order.id`, `tenant.tier`, `payment.provider`) or custom metric histograms must be recorded inside business logic.

---

## 2. Kubernetes Downward API Resource Attributes

Regardless of language, every manually instrumented Kubernetes pod should receive standard OpenTelemetry resource attributes via the Kubernetes Downward API so traces, metrics, and logs correlate with `k8sattributes` processor metadata:

```yaml
env:
  - name: K8S_NODE_NAME
    valueFrom:
      fieldRef:
        fieldPath: spec.nodeName
  - name: K8S_POD_NAME
    valueFrom:
      fieldRef:
        fieldPath: metadata.name
  - name: K8S_POD_NAMESPACE
    valueFrom:
      fieldRef:
        fieldPath: metadata.namespace
  - name: K8S_POD_UID
    valueFrom:
      fieldRef:
        fieldPath: metadata.uid
  - name: OTEL_SERVICE_NAME
    value: "checkout-rs"
  - name: OTEL_EXPORTER_OTLP_ENDPOINT
    value: "http://otel-agent.opentelemetry-system.svc.cluster.local:4317"
  - name: OTEL_EXPORTER_OTLP_PROTOCOL
    value: "grpc"
  - name: OTEL_RESOURCE_ATTRIBUTES
    value: "service.namespace=$(K8S_POD_NAMESPACE),k8s.pod.name=$(K8S_POD_NAME),k8s.namespace.name=$(K8S_POD_NAMESPACE),k8s.pod.uid=$(K8S_POD_UID),k8s.node.name=$(K8S_NODE_NAME)"
```

---

## 3. Rust OpenTelemetry SDK Pattern

Use `opentelemetry`, `opentelemetry_sdk`, `opentelemetry-otlp`, and `tracing-opentelemetry` with Tokio runtime batching:

```rust
use opentelemetry::global;
use opentelemetry_otlp::WithExportConfig;
use opentelemetry_sdk::{runtime, propagation::TraceContextPropagator, trace as sdktrace};

pub fn init_telemetry() -> Result<sdktrace::Tracer, Box<dyn std::error::Error>> {
    global::set_text_map_propagator(TraceContextPropagator::new());
    let tracer = opentelemetry_otlp::new_pipeline()
        .tracing()
        .with_exporter(
            opentelemetry_otlp::new_exporter()
                .tonic()
                .with_env(),
        )
        .with_batch_config(sdktrace::BatchConfig::default())
        .install_batch(runtime::Tokio)?;
    Ok(tracer)
}
```

Ensure `global::shutdown_tracer_provider()` is called inside the `SIGTERM` graceful shutdown handler so buffered spans flush before the pod terminates.

---

## 4. C++ OpenTelemetry SDK Pattern

Compile with `opentelemetry-cpp` (`WITH_OTLP_GRPC=ON` or `WITH_OTLP_HTTP=ON`) and configure `BatchSpanProcessor`:

```cpp
#include "opentelemetry/exporters/otlp/otlp_grpc_exporter_factory.h"
#include "opentelemetry/sdk/trace/batch_span_processor_factory.h"
#include "opentelemetry/sdk/trace/tracer_provider_factory.h"
#include "opentelemetry/trace/provider.h"

void InitTracer() {
  opentelemetry::exporter::otlp::OtlpGrpcExporterOptions opts;
  auto exporter = opentelemetry::exporter::otlp::OtlpGrpcExporterFactory::Create(opts);
  opentelemetry::sdk::trace::BatchSpanProcessorOptions bsp_opts{};
  auto processor = opentelemetry::sdk::trace::BatchSpanProcessorFactory::Create(
      std::move(exporter), bsp_opts);
  std::shared_ptr<opentelemetry::trace::TracerProvider> provider =
      opentelemetry::sdk::trace::TracerProviderFactory::Create(std::move(processor));
  opentelemetry::trace::Provider::SetTracerProvider(provider);
}
```

---

## 5. Custom Business Spans & Baggage Propagation

- Always configure `W3C TraceContext` (`traceparent`, `tracestate`) and `W3C Baggage` (`baggage`) propagators.
- Avoid putting unbounded high-cardinality IDs in span names (use `POST /orders/{id}` as the span name and set `app.order.id` as a span attribute).
- Verify telemetry delivery using `otel_verify_instrumentation` after deploying the updated workload.

---

## 6. Short-Lived `Job` & `CronJob` Telemetry

- Rolling workload tools (`otel_manage_workload_instrumentation` and `scripts/lint_workload_manifest.py`) target `Deployment`, `StatefulSet`, and `DaemonSet` controllers (`INST_UNSUPPORTED_KIND` on standalone `Job` / `CronJob` / bare `Pod`).
- For recurring `CronJob` workloads, set `instrumentation.opentelemetry.io/inject-<lang>` inside `spec.jobTemplate.spec.template.metadata.annotations` (never on top-level `CronJob` metadata).
- Short-lived batch processes often exit before `BatchSpanProcessor`'s periodic timer flushes buffered spans; always invoke explicit SDK flush/shutdown (`trace.get_tracer_provider().force_flush()` and `trace.get_tracer_provider().shutdown()`) in a `finally` block before process exit.
