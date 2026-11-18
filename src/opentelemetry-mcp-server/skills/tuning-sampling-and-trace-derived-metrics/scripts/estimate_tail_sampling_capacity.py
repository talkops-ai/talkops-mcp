#!/usr/bin/env python3
"""Offline capacity estimator for OpenTelemetry Collector tail_sampling processor.

Calculates required num_traces, expected in-memory span buffer size, container
memory limits, memory_limiter settings, and StatefulSet replica count.

Usage:
    python scripts/estimate_tail_sampling_capacity.py \
        --spans-per-sec 25000 --avg-spans-per-trace 20 --decision-wait-sec 10
"""

from __future__ import annotations

import argparse
import json
import math
import sys


def estimate_capacity(
    spans_per_sec: int,
    avg_spans_per_trace: int,
    decision_wait_sec: int,
    bytes_per_span: int = 2048,
    max_memory_mib_per_pod: int = 4096,
) -> dict:
    traces_per_sec = spans_per_sec / max(avg_spans_per_trace, 1)
    active_traces_window = traces_per_sec * decision_wait_sec
    recommended_num_traces = int(math.ceil(active_traces_window * 2.5))

    buffered_spans = recommended_num_traces * avg_spans_per_trace
    buffer_mib = (buffered_spans * bytes_per_span) / (1024 * 1024)
    # Add 512 MiB base overhead for Go runtime, receivers, queues, and connectors
    total_memory_mib = int(math.ceil((buffer_mib + 512) * 1.3))

    replicas = max(2, int(math.ceil(total_memory_mib / max_memory_mib_per_pod)))
    per_pod_num_traces = int(math.ceil(recommended_num_traces / replicas))
    per_pod_memory_mib = max(1024, int(math.ceil(total_memory_mib / replicas)))
    memory_limiter_mib = int(per_pod_memory_mib * 0.80)
    gomemlimit_mib = int(per_pod_memory_mib * 0.80)

    return {
        "inputs": {
            "spans_per_sec": spans_per_sec,
            "avg_spans_per_trace": avg_spans_per_trace,
            "decision_wait_sec": decision_wait_sec,
            "bytes_per_span": bytes_per_span,
        },
        "cluster_totals": {
            "traces_per_sec": round(traces_per_sec, 2),
            "active_traces_in_window": int(math.ceil(active_traces_window)),
            "total_num_traces": recommended_num_traces,
            "estimated_total_memory_mib": total_memory_mib,
        },
        "per_pod_recommendations": {
            "mode": "statefulset",
            "replicas": replicas,
            "num_traces": per_pod_num_traces,
            "expected_new_traces_per_sec": int(math.ceil(traces_per_sec / replicas)),
            "container_memory_limit": f"{per_pod_memory_mib}Mi",
            "memory_limiter_limit_mib": memory_limiter_mib,
            "gomemlimit": f"{gomemlimit_mib}MiB",
            "requires_trace_id_loadbalancer": True,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Estimate tail_sampling memory, num_traces, and replica sizing."
    )
    parser.add_argument(
        "--spans-per-sec",
        type=int,
        required=True,
        help="Total cluster spans per second entering tail sampling.",
    )
    parser.add_argument(
        "--avg-spans-per-trace",
        type=int,
        default=20,
        help="Average number of spans per trace (default: 20).",
    )
    parser.add_argument(
        "--decision-wait-sec",
        type=int,
        default=10,
        help="tail_sampling decision_wait in seconds (default: 10).",
    )
    parser.add_argument(
        "--max-memory-mib-per-pod",
        type=int,
        default=4096,
        help="Maximum memory MiB per collector pod before scaling replicas (default: 4096).",
    )
    args = parser.parse_args(argv)

    if args.spans_per_sec <= 0 or args.avg_spans_per_trace <= 0 or args.decision_wait_sec <= 0:
        print(
            "Error: --spans-per-sec, --avg-spans-per-trace, and --decision-wait-sec must be > 0",
            file=sys.stderr,
        )
        return 1

    result = estimate_capacity(
        spans_per_sec=args.spans_per_sec,
        avg_spans_per_trace=args.avg_spans_per_trace,
        decision_wait_sec=args.decision_wait_sec,
        max_memory_mib_per_pod=args.max_memory_mib_per_pod,
    )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
