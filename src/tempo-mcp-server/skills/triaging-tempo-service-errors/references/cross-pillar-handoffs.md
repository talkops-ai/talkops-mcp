# Cross-Pillar Handoffs (Prometheus, Loki, Kubernetes)

## 1. Metrics Exemplar -> Tempo Trace Pivot

1. Call `tempo_get_exemplar_traces` with a TraceQL metrics query (for example `'{ resource.service.name = "checkout" && status = error } | rate()'` or `'{ resource.service.name = "checkout" } | quantile_over_time(duration, 0.99)'`), or if pivoting from Prometheus TSDB histograms call `prom_query_exemplars` first.
2. Inspect `trace_candidates[].trace_id`, `trace_candidates[].timestamp`, and `trace_candidates[].labels`.
3. Call `tempo_summarize_trace` on the candidate `trace_id` to pinpoint `error_origin_service` and `deepest_error_span`.

## 2. Loki / Application Logs -> Tempo Trace Pivot

1. Pass raw JSON, logfmt, or plaintext error lines to `tempo_get_trace_from_log`.
2. `tempo_get_trace_from_log` extracts W3C `traceparent` (`00-<32hex>-<16hex>-<2hex>`), JSON keys (`trace_id`, `traceId`, `otelTraceID`), or logfmt `trace_id=<32hex>`, rejects all-zero trace IDs, and returns `extracted_trace_id`, `extracted_span_id`, `format`, and `trace_summary`.
3. Once `error_origin_service` and `deepest_error_span.span_id` are identified in `tempo_summarize_trace`, pivot back to Loki using `{service_name="<error_origin_service>"} |= "<trace_id>"` to inspect stack traces emitted around `deepest_error_span.start_time_unix_nano`.

## 3. Tempo Span Attributes -> Kubernetes Pod Investigation

1. Call `tempo_get_trace` or read `tempo://traces/{backend_id}/{trace_id}` to inspect resource attributes on `error_origin_service`:
   - `k8s.namespace.name`
   - `k8s.pod.name`
   - `k8s.node.name`
   - `k8s.container.name`
2. Correlate the pod name and timestamp against Kubernetes pod restarts, OOMKills, or network policy drops.
