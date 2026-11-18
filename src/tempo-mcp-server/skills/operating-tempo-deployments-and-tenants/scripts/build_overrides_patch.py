#!/usr/bin/env python3
"""Offline CLI script to build a validated per-tenant /api/overrides merge_patch payload."""

import argparse
import json
import sys
from typing import Any, Dict


def build_patch(
    rate_limit_mb: float,
    burst_multiplier: float,
    max_trace_mb: float,
    max_live_traces: int,
    block_retention: str,
    enable_metrics_generator: bool,
    use_mib: bool = True,
) -> Dict[str, Any]:
    unit = 1_048_576 if use_mib else 1_000_000
    rate_bytes = int(rate_limit_mb * unit)
    effective_mult = max(1.5, burst_multiplier) if burst_multiplier < 1.0 else burst_multiplier
    burst_bytes = max(rate_bytes, int(rate_bytes * effective_mult))
    patch: Dict[str, Any] = {
        "ingestion_rate_limit_bytes": rate_bytes,
        "ingestion_burst_size_bytes": burst_bytes,
        "max_bytes_per_trace": int(max_trace_mb * unit),
        "max_traces_per_user": max_live_traces,
        "block_retention": block_retention,
    }
    if enable_metrics_generator:
        patch["metrics_generator"] = {
            "processors": ["service-graphs", "span-metrics", "local-blocks"]
        }
    return patch


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a per-tenant /api/overrides JSON merge_patch payload."
    )
    parser.add_argument(
        "--rate-limit-mb",
        type=float,
        default=25.0,
        help="Sustained ingestion rate limit in MB/s (default 25.0).",
    )
    parser.add_argument(
        "--burst-multiplier",
        type=float,
        default=1.5,
        help="Burst multiplier over rate limit (default 1.5).",
    )
    parser.add_argument(
        "--max-trace-mb",
        type=float,
        default=10.0,
        help="Maximum bytes per trace in MB (default 10.0).",
    )
    parser.add_argument(
        "--max-live-traces",
        type=int,
        default=25000,
        help="Maximum live traces per tenant (default 25000).",
    )
    parser.add_argument(
        "--block-retention",
        default="336h",
        help="Per-tenant block retention duration (default 336h).",
    )
    parser.add_argument(
        "--enable-metrics-generator",
        action="store_true",
        default=True,
        help="Include service-graphs, span-metrics, and local-blocks processors.",
    )
    args = parser.parse_args()
    warnings = []
    if args.burst_multiplier < 1.5:
        warnings.append(
            f"burst_multiplier ({args.burst_multiplier}) is below recommended >= 1.5x threshold; "
            "OTel Collector batch flushes may hit rate_limited drops."
        )
    patch = build_patch(
        args.rate_limit_mb,
        args.burst_multiplier,
        args.max_trace_mb,
        args.max_live_traces,
        args.block_retention,
        args.enable_metrics_generator,
    )
    out: Dict[str, Any] = {"merge_patch": patch}
    if warnings:
        out["warnings"] = warnings
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
