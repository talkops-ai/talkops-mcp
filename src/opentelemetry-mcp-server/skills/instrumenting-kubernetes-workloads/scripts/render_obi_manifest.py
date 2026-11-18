#!/usr/bin/env python3
"""Offline generator for OpenTelemetry eBPF Instrumentation (OBI) DaemonSet & RBAC manifests.

Produces least-privilege Linux capabilities (BPF, PERFMON, SYS_PTRACE, NET_RAW,
CHECKPOINT_RESTORE, DAC_READ_SEARCH, SYS_RESOURCE) instead of privileged: true.

Usage:
    python scripts/render_obi_manifest.py --namespace opentelemetry-system \
        --otlp-endpoint http://otel-agent.opentelemetry-system.svc.cluster.local:4317
"""

from __future__ import annotations

import argparse
import sys

import yaml

LEAST_PRIVILEGE_CAPABILITIES = [
    "BPF",
    "PERFMON",
    "SYS_PTRACE",
    "NET_RAW",
    "CHECKPOINT_RESTORE",
    "DAC_READ_SEARCH",
    "SYS_RESOURCE",
]


def render_obi_bundle(
    name: str,
    namespace: str,
    otlp_endpoint: str,
    open_ports: str,
    image: str,
) -> list[dict]:
    labels = {
        "app.kubernetes.io/name": "obi",
        "app.kubernetes.io/Component": "ebpf-instrument",
        "app.kubernetes.io/part-of": "opentelemetry",
    }

    sa = {
        "apiVersion": "v1",
        "kind": "ServiceAccount",
        "metadata": {"name": name, "namespace": namespace, "labels": labels},
    }
    cluster_role = {
        "apiVersion": "rbac.authorization.k8s.io/v1",
        "kind": "ClusterRole",
        "metadata": {"name": f"{name}-{namespace}-reader", "labels": labels},
        "rules": [
            {
                "apiGroups": [""],
                "resources": ["pods", "nodes", "services"],
                "verbs": ["get", "list", "watch"],
            },
            {
                "apiGroups": ["apps"],
                "resources": ["replicasets", "deployments", "statefulsets", "daemonsets"],
                "verbs": ["get", "list", "watch"],
            },
        ],
    }
    binding = {
        "apiVersion": "rbac.authorization.k8s.io/v1",
        "kind": "ClusterRoleBinding",
        "metadata": {"name": f"{name}-{namespace}-reader", "labels": labels},
        "roleRef": {
            "apiGroup": "rbac.authorization.k8s.io",
            "kind": "ClusterRole",
            "name": f"{name}-{namespace}-reader",
        },
        "subjects": [
            {"kind": "ServiceAccount", "name": name, "namespace": namespace}
        ],
    }
    daemonset = {
        "apiVersion": "apps/v1",
        "kind": "DaemonSet",
        "metadata": {"name": name, "namespace": namespace, "labels": labels},
        "spec": {
            "selector": {"matchLabels": {"app.kubernetes.io/name": "obi"}},
            "template": {
                "metadata": {"labels": labels},
                "spec": {
                    "serviceAccountName": name,
                    "hostPID": True,
                    "containers": [
                        {
                            "name": "obi",
                            "image": image,
                            "securityContext": {
                                "privileged": False,
                                "runAsUser": 0,
                                "capabilities": {
                                    "drop": ["ALL"],
                                    "add": LEAST_PRIVILEGE_CAPABILITIES,
                                },
                            },
                            "env": [
                                {"name": "OTEL_EBPF_KUBE_METADATA_ENABLE", "value": "true"},
                                {"name": "OTEL_EBPF_OPEN_PORT", "value": open_ports},
                                {"name": "OTEL_EXPORTER_OTLP_ENDPOINT", "value": otlp_endpoint},
                            ],
                            "resources": {
                                "requests": {"cpu": "100m", "memory": "256Mi"},
                                "limits": {"cpu": "500m", "memory": "512Mi"},
                            },
                        }
                    ],
                },
            },
        },
    }
    return [sa, cluster_role, binding, daemonset]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Render least-privilege OpenTelemetry eBPF Instrumentation (OBI) manifests."
    )
    parser.add_argument("--name", default="otel-ebpf-obi", help="DaemonSet and RBAC base name.")
    parser.add_argument("--namespace", required=True, help="Target Kubernetes namespace.")
    parser.add_argument(
        "--otlp-endpoint",
        required=True,
        help="OTLP collector endpoint (e.g. http://otel-agent:4317).",
    )
    parser.add_argument(
        "--open-ports",
        default="80,443,8080-8090,9090",
        help="Comma-separated port ranges for OBI to inspect.",
    )
    parser.add_argument(
        "--image",
        default="ghcr.io/open-telemetry/opentelemetry-ebpf-instrumentation/obi:v0.2.0",
        help="Pinned OBI container image.",
    )
    args = parser.parse_args(argv)

    if not args.otlp_endpoint.startswith(("http://", "https://")):
        print("Error: --otlp-endpoint must start with http:// or https://", file=sys.stderr)
        return 1

    docs = render_obi_bundle(
        name=args.name,
        namespace=args.namespace,
        otlp_endpoint=args.otlp_endpoint,
        open_ports=args.open_ports,
        image=args.image,
    )
    print(yaml.safe_dump_all(docs, sort_keys=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
