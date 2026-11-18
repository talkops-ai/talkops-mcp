#!/usr/bin/env python3
"""Offline generator for Argo Rollouts AnalysisTemplate / ClusterAnalysisTemplate YAML."""

import argparse
import sys
try:
    import yaml
except ModuleNotFoundError:
    import os as _os, shutil as _shutil, subprocess as _sp
    if _shutil.which("uv") and not _os.environ.get("_UV_YAML_BOOTSTRAPPED"):
        raise SystemExit(
            _sp.call(
                ["uv", "run", "--quiet", "--with", "pyyaml", "python3", *sys.argv],
                env={**_os.environ, "_UV_YAML_BOOTSTRAPPED": "1"},
            )
        )
    raise


def generate_analysis_template(
    service_name: str,
    prometheus_url: str = "http://prometheus:9090",
    namespace: str = "default",
    scope: str = "namespace",
    error_rate_threshold: float = 5.0,
    latency_p99_threshold: float = 2000.0,
    latency_p95_threshold: float = 1000.0,
    count: int = 3,
    interval: str = "60s",
) -> str:
    if not service_name:
        raise ValueError("service_name is required")
    if error_rate_threshold <= 0 or error_rate_threshold > 100:
        raise ValueError("error_rate_threshold must be between 0 and 100")

    err_dec = round(error_rate_threshold / 100.0, 4)
    p99_sec = round(latency_p99_threshold / 1000.0, 3)
    p95_sec = round(latency_p95_threshold / 1000.0, 3)

    metrics = [
        {
            "name": "error-rate",
            "interval": interval,
            "initialDelay": "30s",
            "failureLimit": 2,
            "count": count,
            "provider": {
                "prometheus": {
                    "address": prometheus_url,
                    "query": (
                        f'sum(rate(http_requests_total{{job="{service_name}",status=~"5.."}}[5m])) / '
                        f'sum(rate(http_requests_total{{job="{service_name}"}}[5m]))'
                    ),
                }
            },
            "successCondition": f"result[0] < {err_dec}",
        },
        {
            "name": "latency-p99",
            "interval": interval,
            "initialDelay": "30s",
            "failureLimit": 2,
            "count": count,
            "provider": {
                "prometheus": {
                    "address": prometheus_url,
                    "query": (
                        f'histogram_quantile(0.99, sum(rate(http_request_duration_seconds_bucket{{job="{service_name}"}}[5m])) by (le))'
                    ),
                }
            },
            "successCondition": f"result[0] < {p99_sec}",
        },
        {
            "name": "latency-p95",
            "interval": interval,
            "initialDelay": "30s",
            "failureLimit": 2,
            "count": count,
            "provider": {
                "prometheus": {
                    "address": prometheus_url,
                    "query": (
                        f'histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket{{job="{service_name}"}}[5m])) by (le))'
                    ),
                }
            },
            "successCondition": f"result[0] < {p95_sec}",
        },
    ]

    kind = "ClusterAnalysisTemplate" if scope == "cluster" else "AnalysisTemplate"
    meta: dict = {"name": f"{service_name}-analysis"}
    if scope == "namespace":
        meta["namespace"] = namespace

    doc = {
        "apiVersion": "argoproj.io/v1alpha1",
        "kind": kind,
        "metadata": meta,
        "spec": {"metrics": metrics},
    }
    return yaml.dump(doc, default_flow_style=False, sort_keys=False)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate an AnalysisTemplate or ClusterAnalysisTemplate YAML.")
    parser.add_argument("--service-name", required=True, help="Kubernetes Service name for Prometheus job selector")
    parser.add_argument("--prometheus-url", default="http://prometheus:9090")
    parser.add_argument("--namespace", default="default")
    parser.add_argument("--scope", choices=["namespace", "cluster"], default="namespace")
    parser.add_argument("--error-rate", type=float, default=5.0, help="Max error rate percent (default: 5.0)")
    parser.add_argument("--latency-p99", type=float, default=2000.0, help="Max P99 latency in ms (default: 2000.0)")
    parser.add_argument("--latency-p95", type=float, default=1000.0, help="Max P95 latency in ms (default: 1000.0)")
    parser.add_argument("--count", type=int, default=3, help="Number of measurements per metric (default: 3)")
    args = parser.parse_args()

    try:
        out = generate_analysis_template(
            service_name=args.service_name,
            prometheus_url=args.prometheus_url,
            namespace=args.namespace,
            scope=args.scope,
            error_rate_threshold=args.error_rate,
            latency_p99_threshold=args.latency_p99,
            latency_p95_threshold=args.latency_p95,
            count=args.count,
        )
        print(out, end="")
        return 0
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
