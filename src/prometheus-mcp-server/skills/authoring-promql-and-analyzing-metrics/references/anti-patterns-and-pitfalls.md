# PromQL Anti-Patterns and Common Pitfalls

## 1. Wrapping `rate()` Around `sum()` (Counter Reset Bug)
- **Broken**: `rate(sum by (job) (http_requests_total)[5m:1m])`
  - When any single pod restarts and resets its counter to `0`, the `sum()` drops and `rate()` misinterprets the drop as a massive counter reset across the entire fleet, producing a huge false spike!
- **Correct**: Always take `rate()` first (per time series), then `sum()` across series:
  ```promql
  sum by (job) (rate(http_requests_total[5m]))
  ```

## 2. Omitting `by (le)` in Classic `histogram_quantile()`
- **Broken**: `histogram_quantile(0.95, sum by (job) (rate(http_request_duration_seconds_bucket[5m])))`
  - Returns `NaN` because `histogram_quantile` requires the `le` bucket boundary label.
- **Correct**: Always include `le` in the `by (...)` clause for classic `_bucket` histograms:
  ```promql
  histogram_quantile(0.95, sum by (le, job) (rate(http_request_duration_seconds_bucket[5m])))
  ```

## 3. Using `irate()` over Long Windows or Alerting Rules
- `irate()` only inspects the **last two samples** in the range vector, ignoring all earlier samples in `[5m]`.
- Use `rate()` for alerting rules, SLO calculations, and smooth trend analysis; reserve `irate()` for high-resolution volatile zoom-ins.

## 4. Division by Zero and Empty Vector Dropouts
- When dividing error rates by total request rates (`errors / total`), if `errors` has no matching series (0 errors), a binary `/` produces an **empty vector** instead of `0`.
- **Correct Pattern**: Use `or vector(0)` or `or on(job) (0 * sum by (job) (rate(total_metric[5m])))` and guard denominators with `clamp_min(..., 1e-9)`.
