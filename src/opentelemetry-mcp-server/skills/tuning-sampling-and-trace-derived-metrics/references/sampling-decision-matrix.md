# Sampling Decision Matrix & Trace-ID Routing Reference

## Table of Contents

1. [Head vs. Tail Sampling Comparison](#1-head-vs-tail-sampling-comparison)
2. [Why Tail Sampling Fails on DaemonSets (`CFG_TAIL_SAMPLING_ON_DAEMONSET`)](#2-why-tail-sampling-fails-on-daemonsets-cfg_tail_sampling_on_daemonset)
3. [Two-Tier Trace-ID Load-Balanced Architecture](#3-two-tier-trace-id-load-balanced-architecture)
4. [Recommended Composite Tail Sampling Policy Order](#4-recommended-composite-tail-sampling-policy-order)
5. [Memory Sizing Formulas for `tail_sampling`](#5-memory-sizing-formulas-for-tail_sampling)

---

## 1. Head vs. Tail Sampling Comparison

| Dimension | Head Sampling (`probabilistic` / SDK Sampler) | Tail Sampling (`tail_sampling` Processor) |
|---|---|---|
| **Decision Point** | At root span creation (SDK or Agent ingress) | After `decision_wait` window when full trace has arrived |
| **Captures 100% of Downstream Errors?** | No (drops error traces at the head if not sampled) | Yes (`status_code: [ERROR]` policy retains 100%) |
| **Captures 100% of High-Latency Traces?** | No | Yes (`latency` policy retains traces `> threshold_ms`) |
| **Memory & CPU Overhead** | Near zero (stateless hash of `trace_id`) | High (buffers active traces in memory for `decision_wait`) |
| **Topology Requirement** | Works on any `daemonset` or `deployment` | Requires single replica OR `loadbalancing` exporter (`routing_key: traceID`) |

---

## 2. Why Tail Sampling Fails on DaemonSets (`CFG_TAIL_SAMPLING_ON_DAEMONSET`)

In a Kubernetes cluster, a single distributed trace spans multiple microservices scheduled across different nodes.
- If `tail_sampling` runs on a node-local `daemonset` or behind a standard round-robin Kubernetes `Service`, spans belonging to the same `trace_id` land on different collector pods.
- Pod A sees the root span (`status=OK`) and drops it based on the 5% probabilistic rule, while Pod B sees the downstream database span (`status=ERROR`) and keeps only that single orphan span.
- The resulting trace in Jaeger/Tempo is broken and missing parent spans.
- Therefore, `otel_configure_sampling` and `otel_validate_collector_config` block `tail_sampling` on `daemonset` collectors with `CFG_TAIL_SAMPLING_ON_DAEMONSET`.

---

## 3. Two-Tier Trace-ID Load-Balanced Architecture

```
[App Pods]
   │ OTLP
   ▼
[Tier 1: DaemonSet Agent]
   ├─ processors: [memory_limiter, k8sattributes, batch]
   └─ exporters: [loadbalancing (routing_key: traceID)]
          │ consistent hash by trace_id -> headless Service
          ▼
[Tier 2: StatefulSet Tail-Sampler Gateway]
   ├─ connectors: [spanmetrics, servicegraph] (runs BEFORE tail_sampling!)
   ├─ processors: [memory_limiter, tail_sampling, batch]
   └─ exporters: [otlp (Tempo / Jaeger / SaaS)]
```

---

## 4. Recommended Composite Tail Sampling Policy Order

1. **Drop Health & Readiness Probes (`drop-noisy-healthchecks`)**: Match `/healthz`, `/readyz`, `/livez`, `/metrics` with `invert_match: true` or `drop` policy so probe traffic never consumes trace storage.
2. **Retain 100% of Errors (`errors-policy`)**: `type: status_code`, `status_code: {status_codes: [ERROR]}` plus HTTP `5xx` status codes.
3. **Retain 100% of High-Latency Traces (`latency-policy`)**: `type: latency`, `latency: {threshold_ms: 500}`.
4. **Probabilistic Baseline (`probabilistic-baseline`)**: `type: probabilistic`, `probabilistic: {sampling_percentage: 5.0}` for normal `200 OK` fast traces.

---

## 5. Memory Sizing Formulas for `tail_sampling`

Let:
- $R_{\text{spans}}$ = spans per second entering the tail-sampling tier
- $S_{\text{trace}}$ = average spans per trace
- $W$ = `decision_wait` in seconds (default `10s`)

$$\text{Active TracesPerSec} = \frac{R_{\text{spans}}}{S_{\text{trace}}}$$

$$\text{Min } \texttt{num\_traces} = \text{Active TracesPerSec} \times W \times 2.5 \text{ (safety headroom)}$$

$$\text{Estimated Buffer Memory} \approx \text{Min } \texttt{num\_traces} \times S_{\text{trace}} \times 2.0\text{ KiB}$$

Use `scripts/estimate_tail_sampling_capacity.py` to compute exact settings.

---

## 6. Emergency 100% Capture (`strategy="none"`) During Incidents

If an engineer requests disabling sampling (`strategy="none"`) to capture 100% of traces during active incident debugging:
1. Warn that removing `tail_sampling` multiplies downstream Tempo ingestion volume (risking `tempo_discarded_spans_total{reason="rate_limited"}` and exporter queue backpressure).
2. Preview via `otel_configure_sampling(..., strategy="none", dry_run=True)` without applying unconfirmed mutations.
3. **Always recommend restoring `tail` sampling (`strategy="tail"`) as soon as incident capture is complete** (or adding a temporary service-scoped `string_attribute` tail-sampling policy rather than disabling cluster-wide sampling).
