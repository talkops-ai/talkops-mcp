---
name: instrumenting-kubernetes-workloads
description: Instruments Kubernetes Deployments, StatefulSets, and DaemonSets using OpenTelemetry Operator auto-instrumentation CRDs, zero-code eBPF/OBI DaemonSets, or manual SDKs across Java, Python, Node.js, .NET, Go, Rust, and C++. Use when onboarding services to OpenTelemetry, enabling or removing workload auto-instrumentation annotations, fixing mixed-language OTLP port mismatches (:4317 gRPC vs :4318 HTTP/protobuf), stripping conflicting OTEL_* env vars, cleaning up duplicate Instrumentation CRs, verifying initContainer injection, or generating OBI eBPF manifests. Do not use for collector provisioning (use provisioning-opentelemetry-collectors), Prometheus exporters (use onboarding-exporters-and-instrumentation), collector OOM/queue triage (use troubleshooting-telemetry-pipelines), tail sampling or spanmetrics (use tuning-sampling-and-trace-derived-metrics), or RBAC/TLS security audits (use auditing-observability-security-posture).
---

# Instrumenting Kubernetes Workloads

Onboards and verifies application telemetry across `Deployment`, `StatefulSet`, and `DaemonSet` workloads using OpenTelemetry Operator auto-instrumentation, eBPF/OBI zero-code agents, or manual SDKs—always preferring OpenTelemetry MCP resources and tools over raw `kubectl` commands.

## Preconditions

1. Read `otel://server/capabilities` to check cluster connectivity and `write_enabled` status.
2. Read `otel://operator/status`, `otel://instrumentations/{namespace}`, and `otel://instrumentation/{namespace}/{name}` (for any existing CR) via MCP resources rather than raw `kubectl` to verify the OpenTelemetry Operator mutating webhook is healthy and inspect per-language OTLP endpoints, propagators, and samplers.
3. Read `otel://collectors/{namespace}` to confirm a collector Service is reachable before injecting SDKs.

## Language & Instrumentation Strategy Matrix

| Language | Operator Auto-Instrumentation | Default OTLP Protocol / Port | Special Requirements | Zero-Code eBPF (`OBI`) |
|---|---|---|---|---|
| `java` | `instrumentation.opentelemetry.io/inject-java` | `grpc` (`:4317`) | None (`JAVA_TOOL_OPTIONS` injected automatically) | Supported |
| `python` | `instrumentation.opentelemetry.io/inject-python` | `http/protobuf` (`:4318`) | Avoid conflicting `PYTHONPATH` overrides | Supported |
| `nodejs` | `instrumentation.opentelemetry.io/inject-nodejs` | `http/protobuf` (`:4318`) | Uses `NODE_OPTIONS` `--require` loader | Supported |
| `dotnet` | `instrumentation.opentelemetry.io/inject-dotnet` | `http/protobuf` (`:4318`) | Set `dotnet_runtime="linux-musl-x64"` on Alpine containers | Supported |
| `go` | `instrumentation.opentelemetry.io/inject-go` | `grpc` (`:4317`) | Requires `go_target_exe` (`instrumentation.opentelemetry.io/otel-go-auto-target-exe`) and `enableGoInstrumentation=true` on Operator | Recommended (`OBI`) |
| `rust` / `c++` | Not supported via initContainer | `grpc` (`:4317`) | Use zero-code `OBI` eBPF DaemonSet or manual `tracing-opentelemetry` SDK | Recommended (`OBI`) |

See [references/language-support-matrix.md](references/language-support-matrix.md), [references/manual-sdk-quickstart.md](references/manual-sdk-quickstart.md), and [references/ebpf-obi-deployment.md](references/ebpf-obi-deployment.md).

## End-to-End Workload Onboarding Workflow

- [ ] **Step 1 — Discover Workloads & Current State**: Call `otel_survey_cluster(namespaces=[target_ns])` and `otel_list_workloads(namespace=target_ns, state="any")` (plus `otel_query_a2ui()` when an interactive topology overview is requested) to inspect `Deployment`, `StatefulSet`, and `DaemonSet` workloads, detected languages, and any `INST_CONFLICTING_ENV` or `INST_GO_TARGET_EXE_MISSING` findings.
- [ ] **Step 2 — Ensure Single Namespace `Instrumentation` CR**: Read `otel://instrumentations/{namespace}` and inspect individual CR details via `otel://instrumentation/{namespace}/{name}`. If duplicate conflicting `Instrumentation` CRs exist (`OP_MULTIPLE_INSTRUMENTATIONS`), verify no workload references the obsolete CR and remove it safely via `otel_delete_resource(kind="Instrumentation", namespace=target_ns, name=obsolete_cr, dry_run=True)` followed by `[GATE]` `dry_run=False, confirm=True`. If creating or updating the namespace CR, preview with `otel_patch_instrumentation(namespace=target_ns, name=cr_name, collector_endpoint=..., languages=[...], dry_run=True)`.
- [ ] **Step 3 — [GATE] Apply `Instrumentation` CR**: Present the `spec_yaml` and `language_protocol_mapping` (`:4317` gRPC for `java`/`go`, `:4318` HTTP for `python`/`nodejs`/`dotnet`). After confirmation, call `otel_patch_instrumentation(..., dry_run=False, confirm=True)` and verify via `otel://instrumentation/{namespace}/{name}`.
- [ ] **Step 4 — Preview Workload Annotation Patch / Rolling Restart**:
  - When onboarding a workload, call `otel_manage_workload_instrumentation(namespace=target_ns, workload_name=name, workload_kind=kind, action="enable", language=lang, injection_options={"container_names": [...], "go_target_exe": ..., "dotnet_runtime": ..., "strip_conflicting_env": True}, dry_run=True)`. Note and explain to the user that hardcoded container-level `OTEL_*` environment variables take precedence over and override Operator webhook-injected `Instrumentation` CR settings (`INST_CONFLICTING_ENV`), which is why `strip_conflicting_env=True` removes them.
  - When removing accidental auto-instrumentation, call `otel_manage_workload_instrumentation(..., action="disable", dry_run=True)`.
  - When a workload already has its `instrumentation.opentelemetry.io/inject-*` pod annotation set, yet running pods predate the `Instrumentation` CR (because mutating admission webhooks only fire at Pod `CREATE` time), call `otel_manage_workload_instrumentation(namespace=target_ns, workload_name=name, workload_kind=kind, action="restart", dry_run=True)` rather than `action="enable"`.
- [ ] **Step 5 — [GATE] Apply Workload Patch or Restart**: Review any `GITOPS_MANAGED` or `INST_CONFLICTING_ENV` findings with the user. After confirmation, call `otel_manage_workload_instrumentation(..., dry_run=False, confirm=True)`.
- [ ] **Step 6 — Verify End-to-End Injection**: Call `otel_verify_instrumentation(namespace=target_ns, workload_name=name, workload_kind=kind)` to confirm the `opentelemetry-auto-instrumentation-*` initContainer is injected, pods have restarted after CR creation, and no webhook errors occurred.

## Offline Scripts (Air-Gapped / GitOps Mode)

- `scripts/lint_workload_manifest.py`: Audits offline `Deployment`/`StatefulSet`/`DaemonSet` YAML manifests for unsupported kinds (`Job`/`CronJob`, noting `spec.jobTemplate.spec.template.metadata.annotations` + explicit `force_flush()`/`shutdown()` before exit), conflicting `OTEL_*` env vars, missing `otel-go-auto-target-exe`, `readOnlyRootFilesystem` without `/tmp`, and multi-container ambiguity.
- `scripts/render_instrumentation_cr.py`: Validates `--sampling-ratio` in `[0.0, 1.0]` and renders an `opentelemetry.io/v1alpha1` `Instrumentation` CR with per-language OTLP ports (`:4317` gRPC vs `:4318` HTTP).
- `scripts/render_obi_manifest.py`: Validates explicit `http://` or `https://` `--otlp-endpoint` scheme and renders a least-privilege `OBI` eBPF `DaemonSet` + read-only `ClusterRole`. Whenever user inputs fail CLI validation, explain the error and re-run the script with the corrected values so your response outputs the valid rendered YAML configurations.
- `scripts/render_instrumentation_cr.py`: Generates an `Instrumentation` CR YAML with pinned agent images and per-language OTLP protocol/port env vars.
- `scripts/render_obi_manifest.py`: Generates a least-privilege OpenTelemetry eBPF Instrumentation (`OBI` v1.0) DaemonSet YAML (`BPF`, `PERFMON`, `SYS_PTRACE` capabilities without `privileged: true`).
