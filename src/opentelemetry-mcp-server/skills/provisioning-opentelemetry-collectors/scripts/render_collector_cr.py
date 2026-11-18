#!/usr/bin/env python3
"""Offline OpenTelemetryCollector CRD and RBAC manifest renderer.

Renders a complete multi-document YAML manifest (OpenTelemetryCollector CR,
ClusterRole, and ClusterRoleBinding) for GitOps pull requests without any
cluster or network access.
"""

import argparse
import sys
from typing import Any, Dict, List
import yaml


def render_manifests(
    name: str,
    namespace: str,
    role: str,
    signals: List[str],
    traces_endpoint: str,
    metrics_endpoint: str,
    logs_endpoint: str,
    version: str = "0.152.1",
) -> List[Dict[str, Any]]:
    mode_map = {
        "agent": "daemonset",
        "gateway": "deployment",
        "tail-sampler": "statefulset",
        "all-in-one": "daemonset" if "logs" in signals else "deployment",
    }
    mode = mode_map.get(role, "deployment")

    receivers: Dict[str, Any] = {
        "otlp": {
            "protocols": {
                "grpc": {"endpoint": "0.0.0.0:4317"},
                "http": {"endpoint": "0.0.0.0:4318"},
            }
        }
    }
    processors: Dict[str, Any] = {
        "memory_limiter": {
            "check_interval": "1s",
            "limit_mib": 400,
            "spike_limit_mib": 100,
        },
        "batch": {
            "send_batch_size": 8192,
            "timeout": "200ms",
            "send_batch_max_size": 16384,
        },
    }
    k8s_attr: Dict[str, Any] = {
        "auth_type": "serviceAccount",
        "passthrough": False,
        "extract": {
            "metadata": [
                "k8s.pod.name",
                "k8s.pod.uid",
                "k8s.deployment.name",
                "k8s.namespace.name",
                "k8s.node.name",
            ]
        },
        "pod_association": [
            {"sources": [{"from": "resource_attribute", "name": "k8s.pod.ip"}]},
            {"sources": [{"from": "connection"}]},
        ],
    }
    if mode == "daemonset":
        k8s_attr["filter"] = {"node_from_env_var": "K8S_NODE_NAME"}
    processors["k8sattributes"] = k8s_attr

    exporters: Dict[str, Any] = {}
    pipelines: Dict[str, Any] = {}
    proc_chain = ["memory_limiter", "k8sattributes", "batch"]

    endpoint_map = {
        "traces": traces_endpoint,
        "metrics": metrics_endpoint,
        "logs": logs_endpoint,
    }
    for sig in signals:
        ep = endpoint_map.get(sig, "otel-gateway:4317")
        ep_low = ep.lower()
        if sig == "metrics" and "/api/v1/write" in ep_low:
            exp_key = "prometheusremotewrite/metrics"
            exporters[exp_key] = {
                "endpoint": ep if ep.startswith(("http://", "https://")) else f"http://{ep}",
                "tls": {"insecure": not ep.startswith("https://")},
                "remote_write_queue": {
                    "enabled": True,
                    "num_consumers": 4,
                    "queue_size": 1000,
                },
                "retry_on_failure": {
                    "enabled": True,
                    "initial_interval": "5s",
                    "max_interval": "30s",
                    "max_elapsed_time": "300s",
                },
            }
        elif ep.startswith(("http://", "https://")) or "/otlp" in ep_low:
            exp_key = "otlphttp/loki" if sig == "logs" and "loki" in ep_low else f"otlphttp/{sig}"
            exporters[exp_key] = {
                "endpoint": ep if ep.startswith(("http://", "https://")) else f"http://{ep}",
                "tls": {"insecure": not ep.startswith("https://")},
                "sending_queue": {
                    "enabled": True,
                    "num_consumers": 10,
                    "queue_size": 1000,
                },
                "retry_on_failure": {
                    "enabled": True,
                    "initial_interval": "5s",
                    "max_interval": "30s",
                    "max_elapsed_time": "300s",
                },
            }
        else:
            exp_key = f"otlp/{sig}"
            exporters[exp_key] = {
                "endpoint": ep,
                "tls": {"insecure": not ep.startswith("https://")},
                "sending_queue": {
                    "enabled": True,
                    "num_consumers": 10,
                    "queue_size": 1000,
                },
                "retry_on_failure": {
                    "enabled": True,
                    "initial_interval": "5s",
                    "max_interval": "30s",
                    "max_elapsed_time": "300s",
                },
            }
        pipelines[sig] = {
            "receivers": ["otlp"],
            "processors": list(proc_chain),
            "exporters": [exp_key],
        }

    collector_config = {
        "receivers": receivers,
        "processors": processors,
        "exporters": exporters,
        "service": {
            "pipelines": pipelines,
            "telemetry": {
                "metrics": {
                    "level": "normal",
                    "readers": [
                        {
                            "pull": {
                                "exporter": {
                                    "prometheus": {
                                        "host": "0.0.0.0",
                                        "port": 8888,
                                    }
                                }
                            }
                        }
                    ],
                }
            },
        },
    }

    env_list: List[Dict[str, Any]] = [
        {"name": "GOMEMLIMIT", "value": "400MiB"}
    ]
    if mode == "daemonset":
        env_list.append({
            "name": "K8S_NODE_NAME",
            "valueFrom": {"fieldRef": {"fieldPath": "spec.nodeName"}},
        })

    cr = {
        "apiVersion": "opentelemetry.io/v1beta1",
        "kind": "OpenTelemetryCollector",
        "metadata": {
            "name": name,
            "namespace": namespace,
            "labels": {
                "app.kubernetes.io/managed-by": "talkops-mcp",
                "app.kubernetes.io/component": role,
            },
        },
        "spec": {
            "mode": mode,
            "image": f"otel/opentelemetry-collector-contrib:{version}",
            "env": env_list,
            "resources": {
                "requests": {"cpu": "100m", "memory": "256Mi"},
                "limits": {"cpu": "500m", "memory": "512Mi"},
            },
            "config": collector_config,
        },
    }

    role_name = f"otel-k8sattr-{name}"
    cluster_role = {
        "apiVersion": "rbac.authorization.k8s.io/v1",
        "kind": "ClusterRole",
        "metadata": {"name": role_name},
        "rules": [
            {
                "apiGroups": [""],
                "resources": ["pods", "namespaces", "nodes"],
                "verbs": ["get", "list", "watch"],
            },
            {
                "apiGroups": ["apps"],
                "resources": ["replicasets"],
                "verbs": ["get", "list", "watch"],
            },
            {
                "apiGroups": ["batch"],
                "resources": ["jobs"],
                "verbs": ["get", "list", "watch"],
            },
        ],
    }
    cluster_role_binding = {
        "apiVersion": "rbac.authorization.k8s.io/v1",
        "kind": "ClusterRoleBinding",
        "metadata": {"name": role_name},
        "roleRef": {
            "apiGroup": "rbac.authorization.k8s.io",
            "kind": "ClusterRole",
            "name": role_name,
        },
        "subjects": [
            {
                "kind": "ServiceAccount",
                "name": f"{name}-collector",
                "namespace": namespace,
            }
        ],
    }
    return [cr, cluster_role, cluster_role_binding]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Render OpenTelemetryCollector CRD and RBAC manifests offline."
    )
    parser.add_argument("--name", type=str, required=True, help="Collector CR name")
    parser.add_argument(
        "--namespace", type=str, default="default", help="Target namespace"
    )
    parser.add_argument(
        "--role",
        type=str,
        default="all-in-one",
        choices=["agent", "gateway", "tail-sampler", "all-in-one"],
        help="Collector role",
    )
    parser.add_argument(
        "--signals",
        type=str,
        default="traces,metrics,logs",
        help="Comma-separated signals",
    )
    parser.add_argument(
        "--traces-endpoint",
        type=str,
        default="tempo.observability.svc:4317",
        help="OTLP traces backend endpoint",
    )
    parser.add_argument(
        "--metrics-endpoint",
        type=str,
        default="otel-gateway.observability.svc:4317",
        help="OTLP metrics backend endpoint",
    )
    parser.add_argument(
        "--logs-endpoint",
        type=str,
        default="otel-gateway.observability.svc:4317",
        help="OTLP logs backend endpoint",
    )
    parser.add_argument(
        "--version",
        type=str,
        default="0.152.1",
        help="Collector image version tag",
    )
    args = parser.parse_args()

    signals = [
        s.strip().lower() for s in args.signals.split(",") if s.strip()
    ]
    valid = {"traces", "metrics", "logs"}
    if not signals or any(s not in valid for s in signals):
        print(f"Error: invalid signals '{args.signals}'", file=sys.stderr)
        return 1

    docs = render_manifests(
        name=args.name,
        namespace=args.namespace,
        role=args.role,
        signals=signals,
        traces_endpoint=args.traces_endpoint,
        metrics_endpoint=args.metrics_endpoint,
        logs_endpoint=args.logs_endpoint,
        version=args.version,
    )
    print(yaml.safe_dump_all(docs, sort_keys=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
