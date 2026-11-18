#!/usr/bin/env python3
"""Offline collector topology and resource sizing planner.

Computes recommended OpenTelemetry Collector architecture (single-tier,
two-tier Agent+Gateway, or three-tier with StatefulSet tail-sampler),
Kubernetes resource requests/limits, GOMEMLIMIT, and memory_limiter
settings from cluster node count, workload count, and signal requirements.
"""

import argparse
import json
import sys
from typing import Any, Dict, List


def plan_topology(
    nodes: int,
    workloads: int,
    signals: List[str],
    tail_sampling: bool = False,
    prometheus_scrape: bool = False,
) -> Dict[str, Any]:
    """Compute recommended collector topology and resource sizing."""
    if nodes < 1:
        raise ValueError("Node count must be >= 1")

    if nodes < 20:
        scale = "small"
        sizing = {
            "cpu_request": "100m",
            "cpu_limit": "500m",
            "memory_request": "256Mi",
            "memory_limit": "512Mi",
            "gomemlimit": "400MiB",
            "memory_limiter_mib": 400,
            "spike_limit_mib": 100,
        }
    elif nodes <= 100:
        scale = "medium"
        sizing = {
            "cpu_request": "250m",
            "cpu_limit": "1000m",
            "memory_request": "512Mi",
            "memory_limit": "1Gi",
            "gomemlimit": "800MiB",
            "memory_limiter_mib": 800,
            "spike_limit_mib": 200,
        }
    else:
        scale = "large"
        sizing = {
            "cpu_request": "500m",
            "cpu_limit": "2000m",
            "memory_request": "1Gi",
            "memory_limit": "2Gi",
            "gomemlimit": "1600MiB",
            "memory_limiter_mib": 1600,
            "spike_limit_mib": 400,
        }

    tiers: List[Dict[str, Any]] = []
    if tail_sampling:
        pattern = "three-tier-tail-sampling"
        tiers.append({
            "role": "agent",
            "mode": "daemonset",
            "signals": signals,
            "notes": "Forwards traces via loadbalancing exporter (routing_key: traceID) to tail-sampler StatefulSet.",
        })
        tiers.append({
            "role": "tail-sampler",
            "mode": "statefulset",
            "replicas": max(2, min(nodes // 10, 8)),
            "signals": ["traces"],
            "notes": "Evaluates tail_sampling policies with trace affinity.",
        })
        tiers.append({
            "role": "gateway",
            "mode": "deployment",
            "replicas": max(2, min(nodes // 15, 6)),
            "signals": signals,
            "notes": "Performs batching, OTTL redaction, and backend export.",
        })
    elif nodes >= 10 or workloads >= 30 or "logs" in signals:
        pattern = "two-tier-agent-gateway"
        tiers.append({
            "role": "agent",
            "mode": "daemonset",
            "signals": signals,
            "notes": "Node-local OTLP + filelog + kubeletstats + k8sattributes (K8S_NODE_NAME filter).",
        })
        tiers.append({
            "role": "gateway",
            "mode": "statefulset" if prometheus_scrape else "deployment",
            "replicas": max(2, min(nodes // 15, 6)),
            "signals": signals,
            "target_allocator_enabled": prometheus_scrape,
            "notes": "Central aggregation, connectors, and resilient export.",
        })
    else:
        pattern = "single-tier"
        mode = (
            "statefulset"
            if prometheus_scrape
            else ("daemonset" if "logs" in signals else "deployment")
        )
        tiers.append({
            "role": "all-in-one",
            "mode": mode,
            "replicas": 1 if mode == "daemonset" else 2,
            "signals": signals,
            "target_allocator_enabled": prometheus_scrape,
            "notes": "Single-tier collector for small cluster footprint.",
        })

    return {
        "cluster_scale": scale,
        "nodes": nodes,
        "workloads": workloads,
        "signals": signals,
        "recommended_pattern": pattern,
        "sizing": sizing,
        "tiers": tiers,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Plan OpenTelemetry Collector topology and resource sizing offline."
    )
    parser.add_argument(
        "--nodes", type=int, default=10, help="Number of Kubernetes nodes"
    )
    parser.add_argument(
        "--workloads",
        type=int,
        default=20,
        help="Number of workloads in cluster",
    )
    parser.add_argument(
        "--signals",
        type=str,
        default="traces,metrics,logs",
        help="Comma-separated signals (traces,metrics,logs)",
    )
    parser.add_argument(
        "--tail-sampling",
        action="store_true",
        help="Whether tail_sampling is required",
    )
    parser.add_argument(
        "--prometheus-scrape",
        action="store_true",
        help="Whether Prometheus ServiceMonitor/PodMonitor scraping is required",
    )
    args = parser.parse_args()

    signals = [
        s.strip().lower() for s in args.signals.split(",") if s.strip()
    ]
    valid = {"traces", "metrics", "logs"}
    if not signals or any(s not in valid for s in signals):
        print(
            json.dumps(
                {
                    "error": f"Invalid signals '{args.signals}'. Valid: traces,metrics,logs"
                }
            ),
            file=sys.stderr,
        )
        return 1

    try:
        plan = plan_topology(
            nodes=args.nodes,
            workloads=args.workloads,
            signals=signals,
            tail_sampling=args.tail_sampling,
            prometheus_scrape=args.prometheus_scrape,
        )
        print(json.dumps(plan, indent=2))
        return 0
    except Exception as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
