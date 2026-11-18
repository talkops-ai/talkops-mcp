#!/usr/bin/env python3
"""Offline CLI script to generate a Kubernetes PrometheusRule YAML for Tempo span-metrics alerts."""

import argparse
import sys
from typing import Any, Dict
import yaml


def build_prometheus_rule(
    service: str,
    namespace: str,
    error_ratio_threshold: float,
    p99_seconds_threshold: float,
) -> Dict[str, Any]:
    return {
        "apiVersion": "monitoring.coreos.com/v1",
        "kind": "PrometheusRule",
        "metadata": {
            "name": f"tempo-spanmetrics-{service}-alerts",
            "namespace": namespace,
            "labels": {"app.kubernetes.io/part-of": "tempo-observability"},
        },
        "spec": {
            "groups": [
                {
                    "name": f"tempo.{service}.slo.rules",
                    "rules": [
                        {
                            "alert": "TempoServiceHighErrorRatio",
                            "expr": (
                                f'(sum by (service) (rate(traces_spanmetrics_calls_total{{service="{service}", '
                                'span_kind="SPAN_KIND_SERVER", status_code="STATUS_CODE_ERROR"}[5m])) / '
                                f'clamp_min(sum by (service) (rate(traces_spanmetrics_calls_total{{service="{service}", '
                                'span_kind="SPAN_KIND_SERVER"}[5m])), 0.001)) '
                                f"> {error_ratio_threshold}"
                            ),
                            "for": "5m",
                            "labels": {"severity": "critical", "service": service},
                            "annotations": {
                                "summary": f"Error ratio above {error_ratio_threshold * 100:.1f}% for {service}"
                            },
                        },
                        {
                            "alert": "TempoServiceHighP99Latency",
                            "expr": (
                                "histogram_quantile(0.99, sum by (service, le) "
                                f'(rate(traces_spanmetrics_latency_bucket{{service="{service}", '
                                f'span_kind="SPAN_KIND_SERVER"}}[5m]))) > {p99_seconds_threshold}'
                            ),
                            "for": "5m",
                            "labels": {"severity": "warning", "service": service},
                            "annotations": {
                                "summary": f"p99 latency above {p99_seconds_threshold}s for {service}"
                            },
                        },
                    ],
                }
            ]
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate PrometheusRule YAML for Tempo span-metrics alerts."
    )
    parser.add_argument("--service", default="checkout", help="Target service name.")
    parser.add_argument("--namespace", default="observability", help="Kubernetes namespace.")
    parser.add_argument(
        "--error-ratio",
        type=float,
        default=0.05,
        help="Error ratio threshold (default 0.05).",
    )
    parser.add_argument(
        "--p99-seconds",
        type=float,
        default=1.0,
        help="p99 latency threshold in seconds (default 1.0).",
    )
    args = parser.parse_args()
    manifest = build_prometheus_rule(
        args.service, args.namespace, args.error_ratio, args.p99_seconds
    )
    print(yaml.safe_dump(manifest, sort_keys=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
