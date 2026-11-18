# Prometheus Analysis Queries & `AnalysisTemplate` Rules

## 1. Standard PromQL Metric Definitions

### HTTP 5xx Error Rate (`error-rate`)
```promql
sum(rate(http_requests_total{job="{{args.service-name}}",status=~"5.."}[5m]))
/
sum(rate(http_requests_total{job="{{args.service-name}}"}[5m]))
```
- **Recommended `successCondition`**: `result[0] < 0.05` (or `isNaN(result[0]) || result[0] < 0.05` for low-traffic services where `0/0` produces `NaN`).

### HTTP P99 Latency (`latency-p99`)
```promql
histogram_quantile(0.99,
  sum(rate(http_request_duration_seconds_bucket{job="{{args.service-name}}"}[5m])) by (le)
)
```
- **Recommended `successCondition`**: `result[0] < 2.0` (seconds).

### HTTP P95 Latency (`latency-p95`)
```promql
histogram_quantile(0.95,
  sum(rate(http_request_duration_seconds_bucket{job="{{args.service-name}}"}[5m])) by (le)
)
```
- **Recommended `successCondition`**: `result[0] < 1.0` (seconds).

## 2. Critical `AnalysisTemplate` Rules

1. **Finite `count` Required for Blue-Green**:
   `prePromotionAnalysis` and `postPromotionAnalysis` on `blueGreen` Rollouts block promotion until the `AnalysisRun` finishes. If `interval` is set without `count`, the `AnalysisRun` runs forever and the Rollout never promotes. Always set `count: 3` (or another finite integer) when `interval` is specified.
2. **Never Attach `canary.analysis` to a Blue-Green Rollout**:
   Adding `spec.strategy.canary.analysis` to a Rollout that uses `spec.strategy.blueGreen` causes an `InvalidSpec` controller error (`INVALID_SPEC_STRATEGY_CONFLICT`). `argo_configure_analysis_template` automatically detects the Rollout's strategy and links to `prePromotionAnalysis` for blue-green or `canary.analysis` for canary.
3. **Handling `Inconclusive` / `NaN` Results**:
   When a canary service receives zero requests during `initialDelay`, Prometheus `rate(...) / rate(...)` evaluates `0 / 0 = NaN`, causing Argo Rollouts to mark the measurement `Inconclusive`. Guard low-traffic gates with `isNaN(result[0]) || result[0] < threshold` (or PromQL `or vector(0)`), **and always warn** that `NaN` guards pass vacuously when zero requests hit `{service}-canary`—when real traffic validation is required, ensure canary traffic weight (`setWeight` > 0) is active before `initialDelay` elapses or run synthetic probe traffic against `{service}-canary` during quiet windows.
