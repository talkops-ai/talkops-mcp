# Latency Bottleneck Heuristics

Apply these quantitative rules to the factual fields returned by `tempo_summarize_trace` and `tempo_analyze_service_red`.

## 1. Tail Latency Shape (`duration_quantiles_seconds`)

- **Bimodal / Long-Tail Spike (`p99 / p50 >= 5.0`)**: Indicates cold starts, cache misses, GC pauses, lock contention, or retry storms affecting a small subset of requests. Use `tempo_compare_span_cohorts` with `selection='duration > <p95>'` to isolate the affected attribute cohort.
- **Uniform Shift (`p50` and `p99` both increase by `>= 50%`)**: Indicates a systemic downstream slowdown, CPU throttling across all pods, or an added synchronous RPC call on the hot path.

## 2. Self-Time Hotspot vs Downstream Wait (`self_time_hotspots` vs `critical_path`)

`tempo_summarize_trace` computes `self_time_ms = max(0.0, span_duration_ms - merged_child_intervals_ms)` for every span:
- **Local Compute / Uninstrumented I/O Bottleneck**: A span in `self_time_hotspots` has `self_time_ratio >= 0.40` (40% of total trace duration). The bottleneck is inside that service's own execution (CPU serialization, lock wait, or an uninstrumented synchronous client call).
- **Downstream Wait Bottleneck**: The entry span has high `duration_ms` (`>= 80%` of trace duration) but low `self_time_ms` (`self_time_ratio < 0.15`), while a leaf span in `critical_path` holds the highest `self_time_ms`. Pivot directly to the leaf span's `service_name`.

## 3. Uninstrumented Time Gaps (`TRACE_TIME_GAPS`)

When `observation_codes` includes `TRACE_TIME_GAPS` (`time_gap_note` is populated because `sum(critical_path_ms) < 0.5 * total_duration_ms`):
1. Check whether async message queues (Kafka/RabbitMQ) or thread-pool handoffs occur between parent and child spans.
2. Check whether an intermediate service or database driver lacks OpenTelemetry auto-instrumentation.
3. Check `tempo_get_diagnostics` for `SPANS_DISCARDED` in case child spans were dropped by rate limits or `max_bytes_per_trace`.
