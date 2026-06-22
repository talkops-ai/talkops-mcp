# Sampling Test Guide — OpenTelemetry MCP Server

**Phase 4 of 5** in the OTel Demo end-to-end journey.
**Previous phase**: [Cardinality Audit](OTEL_CARDINALITY_AUDIT_TEST_GUIDE.md)
**Next phase**: [Security Audit](OTEL_SECURITY_AUDIT_TEST_GUIDE.md)

> Cardinality is under control (Phase 3). Now you need to optimize trace volume —
> the OTel Demo currently passes 100% of traces through, which is fine for demos
> but would overwhelm production storage. This phase inspects the current sampling
> configuration and generates patches for head and tail sampling strategies.

---

## Prerequisites (Completed in Phase 3)

| Component | Status |
|-----------|--------|
| ✅ Cardinality audited | ~500 series/service, no critical issues |
| ✅ SpanMetrics inspected | 5 dimensions, 16 histogram buckets |
| ✅ Traces flowing | All services → OTLP → collector → Jaeger |

---

## The Starting Point

The OTel Demo currently has **no sampling** — every trace from every service is exported.
This is manageable for a demo with a load generator, but in production with real traffic:

| Without Sampling | With Sampling |
|---|---|
| 100% of traces exported | Only important traces kept |
| High storage costs | Reduced storage (10-25% of original) |
| Slow Jaeger queries | Fast queries on curated data |
| Network saturation | Controlled bandwidth |

**Two sampling strategies:**
- **Head sampling** (SDK-level): Decide at trace creation whether to sample → lowest overhead
- **Tail sampling** (collector-level): Decide after full trace is collected → keeps errors and slow traces

---

## Phase 1: Inspect Current Sampling Configuration

### Step 1.1: Inspect Collector Sampling

| Field | Value |
|-------|-------|
| **Prompt** | `Inspect the sampling configuration for collector "otel-demo-collector" in "otel-demo".` |
| **Tool** | `otel_inspect_sampling_configuration` |
| **Parameters** | `{"namespace": "otel-demo", "collector_name": "otel-demo-collector"}` |
| **Internal action** | (1) Fetches collector CRD. (2) Searches for `tail_sampling` processor in config. (3) Searches for `probabilistic_sampler` processor. (4) Returns unified sampling view with mode classification. |
| **Expected output** | `mode: "none"` — no sampling configured, `head_sampling: null`, `tail_sampling: null`, `warnings: []` |

**Manual validation:**
```bash
# Verify no sampling processors exist
kubectl get opentelemetrycollectors -n otel-demo otel-demo-collector \
  -o jsonpath='{.spec.config.service.pipelines.traces.processors}'
# ["memory_limiter","k8sattributes","resourcedetection","resource","transform","batch"]
# No tail_sampling or probabilistic_sampler present
```

### Step 1.2: Cross-Reference with Instrumentation CR

| Field | Value |
|-------|-------|
| **Prompt** | `Check if there's a conflict between head and tail sampling for "otel-demo-collector" using Instrumentation CR "default".` |
| **Tool** | `otel_inspect_sampling_configuration` |
| **Parameters** | `{"namespace": "otel-demo", "collector_name": "otel-demo-collector", "instrumentation_cr_name": "default"}` |
| **Internal action** | Same as 1.1 + additionally reads `Instrumentation` CRD named "default" in `otel-demo` namespace. If CR has `spec.sampler`, populates `head_sampling`. If both head and tail are active, flags `mode: "combined"` with conflict warnings. |
| **Expected output** | No Instrumentation CRD named "default" in otel-demo (demo uses manual SDK) → `mode: "none"`, no head sampling data |

**Manual validation:**
```bash
kubectl get instrumentations -n otel-demo
# No resources found (OTel Demo uses manual SDK instrumentation)
```

---

## Phase 2: Configure Head Sampling

Head sampling is the simplest approach — decided at the SDK level before the trace
is created. Use when you want to reduce overall trace volume uniformly.

### Step 2.1: Generate Head Sampling at 100% (Default)

| Field | Value |
|-------|-------|
| **Prompt** | `Generate a config patch to switch to head sampling for "otel-demo-collector" in "otel-demo" — dry run.` |
| **Tool** | `otel_toggle_sampling_strategy` |
| **Parameters** | `{"namespace": "otel-demo", "collector_name": "otel-demo-collector", "target_mode": "head", "dry_run": true}` |
| **Internal action** | Generates an Instrumentation CR patch with `spec.sampler.type: parentbased_traceidratio` and `argument: "1.0"` (100% — no actual reduction). |
| **Expected output** | `target_mode: "head"`, config patch with sampler config, instructions for creating/updating Instrumentation CR |

### Step 2.2: Generate Head Sampling at 25%

| Field | Value |
|-------|-------|
| **Prompt** | `Generate head sampling at 25% rate for "otel-demo-collector" — dry run.` |
| **Tool** | `otel_toggle_sampling_strategy` |
| **Parameters** | `{"namespace": "otel-demo", "collector_name": "otel-demo-collector", "target_mode": "head", "sample_rate": 0.25, "dry_run": true}` |
| **Internal action** | Same but with `argument: "0.25"` — only 25% of new traces will be sampled |
| **Expected output** | Config patch with `parentbased_traceidratio` at 25% |

**What the generated patch looks like:**
```yaml
# Instrumentation CRD patch
spec:
  sampler:
    type: parentbased_traceidratio
    argument: "0.25"
```

**Key detail:** Head sampling is configured via the **Instrumentation CRD** (not the collector config).
It's an SDK-level decision — the `parentbased_traceidratio` sampler propagates the sampling
decision through the trace context, so child spans respect the parent's decision.

---

## Phase 3: Configure Tail Sampling

Tail sampling is more intelligent — the collector waits for the entire trace to arrive,
then decides based on policies (keep errors, keep slow traces, sample the rest).

### Step 3.1: Generate Tail Sampling with Default Policies

| Field | Value |
|-------|-------|
| **Prompt** | `Generate tail sampling config with default policies for "otel-demo-collector" — dry run.` |
| **Tool** | `otel_toggle_sampling_strategy` |
| **Parameters** | `{"namespace": "otel-demo", "collector_name": "otel-demo-collector", "target_mode": "tail", "dry_run": true}` |
| **Internal action** | Generates a collector config patch with `tail_sampling` processor and 3 default policies: (1) Keep all error traces, (2) Keep traces > 5 seconds, (3) Probabilistic fallback at 10% for the rest. Returns YAML patch and integration instructions. |
| **Expected output** | Config patch with 3 policies, `decision_wait: 10s` |

**Generated policies (default):**
```yaml
processors:
  tail_sampling:
    decision_wait: 10s
    policies:
      - name: error-sampling
        type: status_code
        status_code:
          status_codes: [ERROR]
      - name: slow-traces
        type: latency
        latency:
          threshold_ms: 5000
      - name: probabilistic-fallback
        type: probabilistic
        probabilistic:
          sampling_percentage: 10
```

**What this achieves:**
| Policy | Effect | Why |
|--------|--------|-----|
| `error-sampling` | Keeps 100% of error traces | Never lose error visibility |
| `slow-traces` | Keeps all traces > 5s | Catch performance issues |
| `probabilistic-fallback` | Keeps 10% of remaining traces | Baseline visibility |

**Integration warning:** Tail sampling requires **trace-ID-aware routing** when running
multiple collector replicas. All spans from the same trace must reach the same tail sampler
instance. The tool's instructions include this warning.

### Step 3.2: Generate Tail Sampling with Custom Policies

| Field | Value |
|-------|-------|
| **Prompt** | `Generate tail sampling that keeps all errors and samples 5% of the rest — dry run.` |
| **Tool** | `otel_toggle_sampling_strategy` |
| **Parameters** | `{"namespace": "otel-demo", "collector_name": "otel-demo-collector", "target_mode": "tail", "tail_policies": [{"name": "errors", "type": "status_code", "status_code": {"status_codes": ["ERROR"]}}, {"name": "baseline", "type": "probabilistic", "probabilistic": {"sampling_percentage": 5}}], "dry_run": true}` |
| **Internal action** | Uses only the user-provided policies (no defaults) |
| **Expected output** | Config patch with exactly the 2 specified policies |

---

## Phase 4: Disable Sampling

### Step 4.1: Generate Remove Sampling Config

| Field | Value |
|-------|-------|
| **Prompt** | `Generate a config patch to disable all sampling for "otel-demo-collector" in "otel-demo".` |
| **Tool** | `otel_toggle_sampling_strategy` |
| **Parameters** | `{"namespace": "otel-demo", "collector_name": "otel-demo-collector", "target_mode": "none", "dry_run": true}` |
| **Internal action** | Generates removal instructions for both head and tail sampling |
| **Expected output** | Instructions to: (1) Remove `spec.sampler` from Instrumentation CRD, (2) Remove `tail_sampling` processor from collector config and pipeline |

---

## Phase 5: Error Handling

### Step 5.1: Invalid Target Mode

| Field | Value |
|-------|-------|
| **Prompt** | `Switch to adaptive sampling for "otel-demo-collector" — dry run.` |
| **Tool** | `otel_toggle_sampling_strategy` |
| **Parameters** | `{"namespace": "otel-demo", "collector_name": "otel-demo-collector", "target_mode": "adaptive", "dry_run": true}` |
| **Expected output** | Error: `Invalid target_mode: 'adaptive'. Use 'head', 'tail', or 'none'.` |

---

## Sampling Decision Guide

| Your Situation | Recommended Strategy | Tool Call |
|---|---|---|
| Want to reduce overall volume uniformly | Head sampling (25-50%) | `target_mode="head", sample_rate=0.25` |
| Must keep all errors and slow traces | Tail sampling | `target_mode="tail"` (default policies) |
| Want both SDK-level and collector-level control | Combined (head + tail) | Create Instrumentation CR + add tail_sampling processor |
| Demo/development — keep everything | No sampling | `target_mode="none"` |

---

## Phase Summary

At the end of this phase, you've:

| What | Tool | Status |
|------|------|--------|
| ✅ Current sampling inspected | `otel_inspect_sampling_configuration` | `mode: "none"` (demo passes 100%) |
| ✅ Instrumentation CR cross-referenced | Same tool with `instrumentation_cr_name` | No CR exists (manual SDK) |
| ✅ Head sampling patch generated | `otel_toggle_sampling_strategy(target_mode="head")` | 25% ratio ready to apply |
| ✅ Tail sampling patch generated | `otel_toggle_sampling_strategy(target_mode="tail")` | Error + slow + 10% baseline policies |
| ✅ Removal patch generated | `otel_toggle_sampling_strategy(target_mode="none")` | Instructions to remove both |

**Next step →** [Security Audit](OTEL_SECURITY_AUDIT_TEST_GUIDE.md): Final phase — audit the security posture of all OTel components: eBPF privileges, RBAC, TLS, and endpoint exposure.
