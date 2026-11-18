#!/usr/bin/env python3
"""Offline CLI script to render a structured JSON/Markdown incident report from RED and trace facts."""

import argparse
import json
import sys


def classify_severity(error_ratio: float, error_rate_per_sec: float) -> str:
    if error_ratio >= 0.05 or error_rate_per_sec >= 1.0:
        return "CRITICAL"
    if error_ratio >= 0.01:
        return "WARNING"
    if error_ratio >= 0.001:
        return "ELEVATED"
    return "NOMINAL"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Render a structured incident report from Tempo RED and trace summary facts."
    )
    parser.add_argument("--service", default="checkout-service", help="Service name.")
    parser.add_argument("--backend-id", default="default", help="Tempo backend ID.")
    parser.add_argument("--request-rate", type=float, default=120.0, help="Requests/sec.")
    parser.add_argument("--error-rate", type=float, default=8.4, help="Errors/sec.")
    parser.add_argument("--p99-seconds", type=float, default=1.42, help="p99 latency in seconds.")
    parser.add_argument(
        "--trace-id",
        default="4bf92f3577b34da6a3ce929d0e0e4736",
        help="Representative failing trace ID.",
    )
    parser.add_argument(
        "--error-origin-service",
        default="payment-service",
        help="Deepest error origin service.",
    )
    args = parser.parse_args()

    error_ratio = (args.error_rate / args.request_rate) if args.request_rate > 0 else 0.0
    severity = classify_severity(error_ratio, args.error_rate)
    report = {
        "service": args.service,
        "backend_id": args.backend_id,
        "severity": severity,
        "red_metrics": {
            "request_rate_per_sec": round(args.request_rate, 4),
            "error_rate_per_sec": round(args.error_rate, 4),
            "error_ratio": round(error_ratio, 6),
            "p99_seconds": round(args.p99_seconds, 4),
        },
        "representative_trace": {
            "trace_id": args.trace_id,
            "resource_uri": f"tempo://traces/{args.backend_id}/{args.trace_id}",
            "error_origin_service": args.error_origin_service,
        },
    }
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
