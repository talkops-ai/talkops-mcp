#!/usr/bin/env python3
"""Offline generator for OpenTelemetry Collector tail_sampling processor configuration.

Usage:
    python scripts/render_tail_sampling_policies.py \
        --sampling-percentage 5.0 --latency-threshold-ms 500 --num-traces 50000
"""

from __future__ import annotations

import argparse
import sys

import yaml


def render_tail_sampling_block(
    sampling_percentage: float,
    latency_threshold_ms: int,
    decision_wait_sec: int,
    num_traces: int,
    drop_healthchecks: bool,
) -> dict:
    policies: list[dict] = []
    if drop_healthchecks:
        policies.append(
            {
                "name": "drop-noisy-healthchecks",
                "type": "drop",
                "drop": {
                    "drop_sub_policy": [
                        {
                            "name": "health-endpoints",
                            "type": "string_attribute",
                            "string_attribute": {
                                "key": "url.path",
                                "values": ["/health", "/healthz", "/readyz", "/livez", "/metrics"],
                                "enabled_regex_matching": False,
                            },
                        }
                    ]
                },
            }
        )

    policies.extend(
        [
            {
                "name": "retain-errors",
                "type": "status_code",
                "status_code": {"status_codes": ["ERROR"]},
            },
            {
                "name": "retain-slow-traces",
                "type": "latency",
                "latency": {"threshold_ms": latency_threshold_ms},
            },
            {
                "name": "probabilistic-baseline",
                "type": "probabilistic",
                "probabilistic": {"sampling_percentage": sampling_percentage},
            },
        ]
    )

    return {
        "processors": {
            "tail_sampling": {
                "decision_wait": f"{decision_wait_sec}s",
                "num_traces": num_traces,
                "expected_new_traces_per_sec": max(100, num_traces // max(decision_wait_sec * 2, 1)),
                "policies": policies,
            }
        }
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Render a production tail_sampling processor YAML block."
    )
    parser.add_argument(
        "--sampling-percentage",
        type=float,
        default=10.0,
        help="Baseline probabilistic sampling percentage (0.0 to 100.0).",
    )
    parser.add_argument(
        "--latency-threshold-ms",
        type=int,
        default=500,
        help="Latency threshold in milliseconds to retain 100%% of slow traces.",
    )
    parser.add_argument(
        "--decision-wait-sec",
        type=int,
        default=10,
        help="Wait time in seconds before making a sampling decision.",
    )
    parser.add_argument(
        "--num-traces",
        type=int,
        default=50000,
        help="Maximum traces buffered in memory.",
    )
    parser.add_argument(
        "--no-drop-healthchecks",
        action="store_true",
        help="Disable the healthcheck drop sub-policy.",
    )
    args = parser.parse_args(argv)

    if not (0.0 <= args.sampling_percentage <= 100.0):
        print("Error: --sampling-percentage must be between 0.0 and 100.0", file=sys.stderr)
        return 1
    if args.latency_threshold_ms <= 0 or args.num_traces <= 0:
        print("Error: --latency-threshold-ms and --num-traces must be > 0", file=sys.stderr)
        return 1

    block = render_tail_sampling_block(
        sampling_percentage=args.sampling_percentage,
        latency_threshold_ms=args.latency_threshold_ms,
        decision_wait_sec=args.decision_wait_sec,
        num_traces=args.num_traces,
        drop_healthchecks=not args.no_drop_healthchecks,
    )
    print(yaml.safe_dump(block, sort_keys=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
