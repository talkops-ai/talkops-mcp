# Language Auto-Instrumentation & Protocol Support Matrix

## Table of Contents
1. [Pinned Auto-Instrumentation Agent Images](#pinned-auto-instrumentation-agent-images)
2. [Per-Language OTLP Protocol & Port Alignment](#per-language-otlp-protocol--port-alignment)
3. [Multi-Container & Runtime Annotations](#multi-container--runtime-annotations)
4. [Common Injection Failure Modes](#common-injection-failure-modes)

## Pinned Auto-Instrumentation Agent Images

| Language | Pinned Agent Image | Signals Supported |
|---|---|---|
| `java` | `ghcr.io/open-telemetry/opentelemetry-operator/autoinstrumentation-java:2.11.0` | `traces`, `metrics`, `logs` |
| `python` | `ghcr.io/open-telemetry/opentelemetry-operator/autoinstrumentation-python:0.50b0` | `traces`, `metrics`, `logs` |
| `nodejs` | `ghcr.io/open-telemetry/opentelemetry-operator/autoinstrumentation-nodejs:0.56.0` | `traces`, `metrics` |
| `dotnet` | `ghcr.io/open-telemetry/opentelemetry-operator/autoinstrumentation-dotnet:1.9.0` | `traces`, `metrics`, `logs` |
| `go` | `ghcr.io/open-telemetry/opentelemetry-go-instrumentation/autoinstrumentation-go:v0.19.0-alpha` | `traces`, `metrics` |

## Per-Language OTLP Protocol & Port Alignment

A single top-level `spec.exporter.endpoint` in an `Instrumentation` CR breaks mixed-language namespaces because Java and Go agents default to gRPC (`:4317`) while Python, Node.js, and .NET agents default to `http/protobuf` (`:4318`). `otel_patch_instrumentation` automatically injects per-language environment variables:

- **Java (`spec.java.env`) & Go (`spec.go.env`)**:
  - `OTEL_EXPORTER_OTLP_PROTOCOL=grpc`
  - `OTEL_EXPORTER_OTLP_ENDPOINT=http://<collector-host>:4317`
- **Python (`spec.python.env`), Node.js (`spec.nodejs.env`), & .NET (`spec.dotnet.env`)**:
  - `OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf`
  - `OTEL_EXPORTER_OTLP_ENDPOINT=http://<collector-host>:4318`

## Multi-Container & Runtime Annotations

- **Target Specific Containers**: `instrumentation.opentelemetry.io/container-names: "app,worker"`
- **Go Target Executable**: `instrumentation.opentelemetry.io/otel-go-auto-target-exe: "/app/server"`
- **.NET Alpine / musl Runtime**: `instrumentation.opentelemetry.io/inject-dotnet-runtime: "linux-musl-x64"`
- **Custom Resource Attributes**: `resource.opentelemetry.io/service.version: "1.4.2"`

## Common Injection Failure Modes

1. **`OP_MULTIPLE_INSTRUMENTATIONS`**: Multiple `Instrumentation` CRs exist in the same namespace and the workload annotation uses `"true"`. Either delete duplicate CRs with `otel_delete_resource` or set the CR name explicitly in `injection_options={"instrumentation_cr_name": "my-cr"}`.
2. **`INST_CONFLICTING_ENV`**: Hardcoded `OTEL_EXPORTER_OTLP_ENDPOINT` on the container spec overrides Operator-injected values. Remediate via `injection_options={"strip_conflicting_env": True}`.
3. **`INST_POD_PREDATES_INJECTION`**: Pods were created before the `Instrumentation` CR existed. Trigger a rolling restart via `otel_manage_workload_instrumentation(..., action="restart")`.
