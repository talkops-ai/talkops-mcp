#!/usr/bin/env python3
"""Offline canary traffic weight progression schedule generator."""

import argparse
import json
import sys


PROFILES = {
    "standard": {"steps": [5, 25, 50, 100], "bake_minutes": 10, "max_5xx_pct": 1.0, "max_p95_delta_pct": 25.0},
    "critical": {"steps": [1, 5, 15, 35, 65, 100], "bake_minutes": 15, "max_5xx_pct": 0.5, "max_p95_delta_pct": 15.0},
    "fast": {"steps": [10, 50, 100], "bake_minutes": 5, "max_5xx_pct": 2.0, "max_p95_delta_pct": 30.0},
}


def build_schedule(args: argparse.Namespace) -> dict:
    prof = PROFILES[args.profile]
    steps_out = []
    for idx, canary_w in enumerate(prof["steps"], start=1):
        stable_w = 100 - canary_w
        steps_out.append({
            "step": idx,
            "weights": {args.stable_service: stable_w, args.canary_service: canary_w},
            "bake_minutes": prof["bake_minutes"] if canary_w < 100 else 0,
            "preview_call": {
                "tool": "traefik_set_traffic_weights",
                "arguments": {
                    "name": args.traefik_service,
                    "namespace": args.namespace,
                    "weights": {args.stable_service: stable_w, args.canary_service: canary_w},
                    "dry_run": True,
                },
            },
            "abort_if": {
                "error_rate_5xx_pct_gt": prof["max_5xx_pct"],
                "latency_p95_delta_pct_gt": prof["max_p95_delta_pct"],
            },
        })
    return {
        "traefik_service": args.traefik_service,
        "namespace": args.namespace,
        "profile": args.profile,
        "rollback_weights": {args.stable_service: 100, args.canary_service: 0},
        "schedule": steps_out,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate a preview-first canary traffic weight progression schedule."
    )
    parser.add_argument("--traefik-service", default="app-wrr", help="TraefikService name")
    parser.add_argument("--namespace", default="default", help="Kubernetes namespace")
    parser.add_argument("--stable-service", default="app-stable", help="Stable backend Service name")
    parser.add_argument("--canary-service", default="app-canary", help="Canary backend Service name")
    parser.add_argument(
        "--profile",
        choices=("standard", "critical", "fast"),
        default="standard",
        help="Risk profile for weight progression",
    )
    args = parser.parse_args()
    sys.stdout.write(json.dumps(build_schedule(args), indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
