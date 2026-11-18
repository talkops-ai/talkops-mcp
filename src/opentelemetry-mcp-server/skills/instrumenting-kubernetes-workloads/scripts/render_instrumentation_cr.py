#!/usr/bin/env python3
"""Offline generator for OpenTelemetry Operator Instrumentation CR YAML (`v1alpha1`).

Aligns per-language OTLP protocol and collector ports automatically:
- python, nodejs, dotnet, apache-httpd -> http/protobuf (:4318)
- java, go, nginx -> grpc (:4317)

Usage:
    python scripts/render_instrumentation_cr.py --name default-inst --namespace default \
        --collector-service otel-agent.opentelemetry-system.svc.cluster.local \
        --languages java,python,nodejs,dotnet
"""

from __future__ import annotations

import argparse
import sys

import yaml

PINNED_IMAGES = {
    "java": "ghcr.io/open-telemetry/opentelemetry-operator/autoinstrumentation-java:2.11.0",
    "python": "ghcr.io/open-telemetry/opentelemetry-operator/autoinstrumentation-python:0.50b0",
    "nodejs": "ghcr.io/open-telemetry/opentelemetry-operator/autoinstrumentation-nodejs:0.56.0",
    "dotnet": "ghcr.io/open-telemetry/opentelemetry-operator/autoinstrumentation-dotnet:1.10.0",
    "go": "ghcr.io/open-telemetry/opentelemetry-go-instrumentation/autoinstrumentation-go:v0.19.0-alpha",
    "apache-httpd": "ghcr.io/open-telemetry/opentelemetry-operator/autoinstrumentation-apache-httpd:1.0.4",
    "nginx": "ghcr.io/open-telemetry/opentelemetry-operator/autoinstrumentation-nginx:1.0.4",
}

LANGUAGE_PROTOCOL = {
    "java": ("grpc", 4317),
    "python": ("http/protobuf", 4318),
    "nodejs": ("http/protobuf", 4318),
    "dotnet": ("http/protobuf", 4318),
    "go": ("grpc", 4317),
    "apache-httpd": ("http/protobuf", 4318),
    "nginx": ("grpc", 4317),
}


def build_instrumentation_cr(
    name: str,
    namespace: str,
    collector_host: str,
    languages: list[str],
    sampling_ratio: float,
) -> dict:
    spec: dict = {
        "exporter": {
            "endpoint": f"http://{collector_host}:4317",
        },
        "propagators": ["tracecontext", "baggage"],
        "sampler": {
            "type": "parentbased_traceidratio",
            "argument": str(sampling_ratio),
        },
    }

    for lang in languages:
        proto, port = LANGUAGE_PROTOCOL[lang]
        lang_key = "apacheHttpd" if lang == "apache-httpd" else lang
        spec[lang_key] = {
            "image": PINNED_IMAGES[lang],
            "env": [
                {
                    "name": "OTEL_EXPORTER_OTLP_ENDPOINT",
                    "value": f"http://{collector_host}:{port}",
                },
                {
                    "name": "OTEL_EXPORTER_OTLP_PROTOCOL",
                    "value": proto,
                },
            ],
        }

    return {
        "apiVersion": "opentelemetry.io/v1alpha1",
        "kind": "Instrumentation",
        "metadata": {
            "name": name,
            "namespace": namespace,
            "labels": {
                "app.kubernetes.io/managed-by": "opentelemetry-mcp-skill",
            },
        },
        "spec": spec,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Render a protocol-aligned OpenTelemetry Instrumentation CR (v1alpha1)."
    )
    parser.add_argument("--name", required=True, help="Instrumentation CR name.")
    parser.add_argument("--namespace", required=True, help="Target Kubernetes namespace.")
    parser.add_argument(
        "--collector-service",
        required=True,
        help="Collector service DNS hostname (without port).",
    )
    parser.add_argument(
        "--languages",
        default="java,python,nodejs,dotnet",
        help="Comma-separated languages (java,python,nodejs,dotnet,go,apache-httpd,nginx).",
    )
    parser.add_argument(
        "--sampling-ratio",
        type=float,
        default=1.0,
        help="Head sampling ratio between 0.0 and 1.0 (default: 1.0).",
    )
    args = parser.parse_args(argv)

    if not (0.0 <= args.sampling_ratio <= 1.0):
        print("Error: --sampling-ratio must be between 0.0 and 1.0", file=sys.stderr)
        return 1

    langs = [item.strip() for item in args.languages.split(",") if item.strip()]
    unknown = [l for l in langs if l not in PINNED_IMAGES]
    if unknown:
        print(f"Error: Unsupported languages: {', '.join(unknown)}", file=sys.stderr)
        return 1

    manifest = build_instrumentation_cr(
        name=args.name,
        namespace=args.namespace,
        collector_host=args.collector_service,
        languages=langs,
        sampling_ratio=args.sampling_ratio,
    )
    print(yaml.safe_dump(manifest, sort_keys=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
