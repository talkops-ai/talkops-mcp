# OpenTelemetry MCP Server — Natural Language Prompt Reference

**For every tool, resource, and prompt documented in [WORKFLOW_JOURNEYS.md](WORKFLOW_JOURNEYS.md), this guide provides ready-to-use natural language prompts you can give to an AI agent.**

Copy any prompt below exactly or adapt it for your namespace, collector, and service names.

> **Design**: Read-only context uses **resources** (`otel://...`). State-changing actions use **tools** with `dry_run=True` by default.

---

## Table of Contents

1. [Discovery](#discovery)
2. [Smart Provisioning (NEW)](#smart-provisioning)
3. [Instrumentation](#instrumentation)
4. [Pipeline Validation](#pipeline-validation)
5. [Metric Cardinality Governance](#metric-cardinality-governance)
6. [Sampling](#sampling)
7. [SpanMetrics](#spanmetrics)
8. [Guided Workflow Prompts](#guided-workflow-prompts)
9. [Resource Reads](#resource-reads)

---

## Discovery

> **Tool**: `otel_list_collectors`

```
List all OTel collectors in the cluster.
```
```
List OTel collectors in the "monitoring" namespace.
```
```
Show me all collectors with the label "app=otel-gateway".
```

> **Tool**: `otel_get_collector`

```
Show me the full configuration of the collector "otel-gateway" in the "monitoring" namespace.
```
```
Get details for collector "otel-traces" in "monitoring" with full raw YAML.
```
```
Show me the pipeline topology of collector "otel-daemonset" in "default".
```

> **Tool**: `otel_list_instrumented_services`

```
List all instrumented services in the "production" namespace.
```
```
Show me which deployments in "default" have OTel auto-instrumentation configured.
```
```
Check if any services in "staging" have auto-instrumentation annotations but missing init containers.
```

> **Tool**: `otel_patch_collector`

```
Create a new OTel collector named "otel-gateway" in the "monitoring" namespace with deployment mode — dry run first.
```
```
Replace the collector "otel-gateway" in "monitoring" with a completely new config — overwrite the entire CRD, dry run first.
```
```
Patch the collector "otel-traces" in "monitoring" to scale up to 3 replicas — dry run first.
```
```
Create a collector with custom labels team=platform and env=staging — dry run.
```

---


## Smart Provisioning

> **Tool**: `otel_provision_collector`

```
Provision a collector for traces and metrics in the "payments" namespace — dry run first.
```
```
Set up OTel collection for traces, metrics, and logs in the "production" namespace. Auto-discover where to send the data.
```
```
Create a collector in "staging" for traces only, with spanmetrics enabled to generate RED metrics.
```
```
Provision a log collector in "production" with filelog enabled for container log collection — dry run.
```
```
Set up an OTel collector in "monitoring" for metrics with Prometheus scraping enabled.
```
```
Provision a collector in "default" for traces, sending to jaeger:4317, and metrics to prometheus:9090.
```
```
Create a collector in "otel-demo" for all three signals. I don't know where the backends are — auto-discover them.
```

---


## Instrumentation

> **Tool**: `otel_lookup_instrumentation`

```
Is auto-instrumentation available for Python?
```
```
Check OTel instrumentation support for Java with Spring Boot.
```
```
What instrumentation options are available for Go?
```
```
Look up OTel instrumentation support for Node.js with Express.
```
```
Is there auto-instrumentation for Rust?
```

> **Tool**: `otel_patch_instrumentation`

```
Create an Instrumentation CR named "default" in the "production" namespace with endpoint "http://otel-collector:4317" — dry run first.
```
```
Create an Instrumentation profile with a sampler set to parentbased_traceidratio at 25% in the "staging" namespace.
```
```
Patch the Instrumentation CR "default" in "production" to add Java and Python language configs.
```

> **Tool**: `otel_annotate_deployment`

```
Enable Python auto-instrumentation on the deployment "api-server" in the "production" namespace — dry run first.
```
```
Annotate the deployment "checkout-service" in "default" for Java auto-instrumentation.
```
```
Apply auto-instrumentation annotation for Node.js on deployment "frontend" in "staging" with Instrumentation CR name "custom-instr".
```

---

## Pipeline Validation

> **Tool**: `otel_validate_k8sattributes_order`

```
Validate the processor ordering for collector "otel-gateway" in the "monitoring" namespace.
```
```
Check if the processors in the traces pipeline of "otel-traces" in "monitoring" are in the correct order.
```
```
Are the processors in "otel-daemonset" following the recommended memory_limiter → k8sattributes → batch order?
```

> **Tool**: `otel_check_filelog_safety`

```
Check if the filelog receiver in "otel-daemonset" in "monitoring" has any safety issues.
```
```
Is the log collector "otel-logs" in "monitoring" at risk of self-collection feedback loops?
```
```
Audit the filelog configuration of "otel-daemonset" for checkpoint storage and self-collection issues.
```

> **Tool**: `otel_inspect_target_allocator_state`

```
Inspect the Target Allocator state for collector "otel-metrics" in "monitoring".
```
```
What allocation strategy is the Target Allocator using for "otel-gateway"?
```
```
Is the Target Allocator enabled for collector "otel-metrics" in "monitoring"? What are its ServiceMonitor selectors?
```

> **Tool**: `otel_recommend_collector_topology`

```
Recommend a collector topology for traces and logs on a medium-sized cluster with 30 workloads.
```
```
What deployment mode should I use for collecting metrics and traces with Prometheus scrape targets on a large cluster?
```
```
Recommend an OTel Collector topology for logs-only collection on a small cluster with 10 workloads.
```

---

## Metric Cardinality Governance

> **Tool**: `otel_detect_cardinality`

```
Detect metric cardinality issues in collector "otel-metrics" in the "monitoring" namespace.
```
```
Are there any high-cardinality dimensions in the SpanMetrics connector of "otel-gateway"?
```
```
Estimate the total metric series count generated by collector "otel-traces" in "monitoring".
```

> **Tool**: `otel_gen_drop_attribute_rules`

```
Generate a transform processor to drop the attributes "http.user_agent" and "url.full" from metrics.
```
```
Create a transform rule to drop "db.statement" from traces.
```
```
Generate YAML to drop "http.user_agent", "http.request.header.x-forwarded-for", and "url.full" from logs.
```

> **Tool**: `otel_analyze_ebpf_footprint`

```
Scan for eBPF instrumentation pods in the "production" namespace and assess their security posture.
```
```
Are there any eBPF agents running with privileged mode in the cluster?
```
```
Audit eBPF instrumentation across all namespaces for elevated privileges and host access.
```

---

## Sampling

> **Tool**: `otel_inspect_sampling_configuration`

```
Inspect the sampling configuration for collector "otel-traces" in the "monitoring" namespace.
```
```
Check if there's a conflict between head and tail sampling for "otel-traces" in "monitoring" using Instrumentation CR "default".
```
```
What sampling strategy is currently active for collector "otel-gateway"?
```

> **Tool**: `otel_toggle_sampling_strategy`

```
Generate a config patch to switch to head sampling at 25% rate for "otel-traces" in "monitoring" — dry run.
```
```
Generate tail sampling config for collector "otel-gateway" in "monitoring" with default policies — dry run.
```
```
Generate custom tail sampling policies: keep all errors and traces longer than 2 seconds, with 5% probabilistic fallback.
```
```
Generate a config patch to disable all sampling for "otel-traces" in "monitoring".
```

---

## SpanMetrics

> **Tool**: `otel_inspect_spanmetrics_config`

```
Inspect the SpanMetrics connector configuration for collector "otel-gateway" in "monitoring".
```
```
What dimensions and histogram buckets are configured for SpanMetrics in "otel-traces"?
```

> **Tool**: `otel_enable_spanmetrics_for_service`

```
Generate SpanMetrics connector config for collector "otel-traces" in "monitoring" with dimensions http.method and http.status_code — dry run.
```
```
Enable SpanMetrics for "otel-gateway" with custom histogram buckets [5, 10, 25, 50, 100, 250, 500, 1000, 5000].
```
```
Generate SpanMetrics YAML for "otel-traces" in "monitoring" with default dimensions and include pipeline wiring instructions.
```

---

## Guided Workflow Prompts

These invoke MCP prompts that return structured multi-step workflows:

> **Prompt**: `otel_onboard_service`

```
Guide me through onboarding my Python app "api-server" in the "production" namespace to OpenTelemetry.
```
```
Onboard the Java service "payment-service" in "default" to OTel auto-instrumentation.
```

> **Prompt**: `otel_investigate_pipeline`

```
Investigate the OTel collector "otel-gateway" in the "monitoring" namespace — check processor ordering, filelog safety, and sampling.
```
```
Run a full pipeline investigation for collector "otel-daemonset" in "monitoring".
```

> **Prompt**: `otel_cardinality_audit`

```
Audit metric cardinality for collector "otel-metrics" in the "monitoring" namespace.
```
```
Check for high-cardinality dimensions in "otel-gateway" and generate remediation YAML.
```

> **Prompt**: `otel_sampling_review`

```
Review the sampling strategy for collector "otel-traces" in "monitoring" and recommend optimizations.
```
```
Is my sampling configuration optimal for "otel-gateway"? Check for head/tail conflicts.
```

> **Prompt**: `otel_security_audit`

```
Audit the OTel security posture in the "production" namespace.
```
```
Run a security audit across all OTel components in "monitoring" — check eBPF privileges, RBAC, and sensitive attributes.
```

---

## Resource Reads

> **Resource**: `otel://system/health`

```
Check if the OTel MCP server can connect to Kubernetes and see OTel CRDs.
```
```
Show me the server health status.
```

> **Resource**: `otel://collector/{namespace}/{name}`

```
Show me the full config of collector "otel-gateway" in "monitoring".
```

> **Resource**: `otel://k8s-enrichment/{namespace}/{collector}`

```
Show me the k8sattributes enrichment profile for collector "otel-gateway" in "monitoring".
```

> **Resource**: `otel://logs-profile/{namespace}/{collector}`

```
Show me the filelog receiver configuration for collector "otel-daemonset" in "monitoring".
```

> **Resource**: `otel://spanmetrics/{namespace}/{collector}`

```
Show me the SpanMetrics connector profile for "otel-gateway" in "monitoring".
```

> **Resource**: `otel://instrumentation/{namespace}/{name}`

```
Show me the Instrumentation CRD "default" in the "production" namespace.
```

> **Resource**: `otel://target-allocator/{namespace}/{name}`

```
Show me the Target Allocator state for collector "otel-metrics" in "monitoring".
```

> **Resource**: `otel://lang/{language}`

```
Show me OTel instrumentation capabilities for Python.
```
```
What signals does Java auto-instrumentation support?
```

> **Resource**: `otel://registry/languages`

```
Show me the full language support catalog for OTel instrumentation.
```
```
Which languages support auto-instrumentation?
```

---

*Document Version: 1.2 | Updated for otel_provision_collector prompts | Companion to [WORKFLOW_JOURNEYS.md](WORKFLOW_JOURNEYS.md)*
