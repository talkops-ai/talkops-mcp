# OpenTelemetry MCP Server — Execution Contract

This server executes live Kubernetes and OpenTelemetry Operator (`opentelemetry.io`) operations for a single bound cluster context. Domain playbooks, decision matrices, and offline generators live in the companion Agent Skills (`skills/*/SKILL.md`).

## Safety & Write Gate Rules
1. **Read-Only Default**: Write tools are only registered when `--allow-write` (`MCP_ALLOW_WRITE=true`) is enabled and `--read-only` is not set. Check `otel://server/capabilities` first.
2. **Two-Phase Mutation (`dry_run=True`)**: Every mutating tool defaults to `dry_run=True`. Always inspect the returned `spec_yaml`, `config_diff`, and `findings` before calling with `dry_run=False`.
3. **Destructive Confirmation**: Full resource overwrites (`overwrite=True`), deletions (`otel_delete_resource`), rollbacks (`otel_revert_collector_config`), disabling instrumentation, and mutating GitOps-managed (`Argo CD` / `Flux` / `Helm`) resources require MCP elicitation or `confirm=True`.
4. **Secret Hygiene**: Never pass plaintext credentials in `config_yaml` or `exporter_overrides`. Reference Kubernetes Secrets via `${env:VAR_NAME}` and `credentials_secret_refs`. All outputs redact inline secrets (`***REDACTED***`).

## Tool & Resource Routing
- **Cluster Survey & Discovery**: Call `otel_survey_cluster` for a single-call snapshot of Operator health, Collectors, Instrumentations, TargetAllocators, OpAMPBridges, eBPF agents, and backends. Call `otel_list_workloads` to inspect workload instrumentation state across `Deployment`, `StatefulSet`, and `DaemonSet`.
- **Collector Lifecycle**: Use `otel_provision_collector` for intent-based `agent`, `gateway`, `tail-sampler`, or `all-in-one` collectors; `otel_patch_collector` for raw YAML patches; `otel_revert_collector_config` for one-level snapshot undo; `otel_delete_resource` for CR deletion.
- **Workload Instrumentation**: Use `otel_patch_instrumentation` (auto-aligns gRPC `:4317` for Java/Go and HTTP `:4318` for Python/Node.js/.NET), `otel_manage_workload_instrumentation` (`enable`, `disable`, `restart`), and `otel_verify_instrumentation`.
- **Pipeline Configuration**: Use `otel_configure_receivers`, `otel_configure_processing` (OTTL / PII masking / noise filtering), `otel_configure_sampling`, and `otel_configure_connectors` (`spanmetrics`, `servicegraph`).
- **Diagnostics & Governance**: Use `otel_diagnose_collector`, `otel_validate_collector_config`, and `otel_audit_security_posture`.
- **Live Resources**: Read `otel://server/capabilities`, `otel://cluster/contexts`, `otel://operator/status`, `otel://collectors/{namespace}`, `otel://collector/{namespace}/{name}`, `otel://collector/{namespace}/{name}/config`, `otel://collector/{namespace}/{name}/history`, `otel://k8s-enrichment/{namespace}/{collector}`, `otel://logs-profile/{namespace}/{collector}`, `otel://spanmetrics/{namespace}/{collector}`, `otel://sampling/{namespace}/{collector}`, `otel://instrumentations/{namespace}`, `otel://instrumentation/{namespace}/{name}`, and `otel://target-allocator/{namespace}/{name}`.
