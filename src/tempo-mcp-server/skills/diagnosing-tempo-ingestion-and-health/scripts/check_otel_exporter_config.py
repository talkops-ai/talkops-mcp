#!/usr/bin/env python3
"""Offline CLI script to validate OpenTelemetry Collector OTLP exporter configuration for Tempo."""

import argparse
import json
import sys
from typing import Any, Dict, List
import yaml

SAMPLE_OTEL_CONFIG = """
exporters:
  otlp/tempo:
    endpoint: tempo-distributor.observability.svc.cluster.local:4317
    tls:
      insecure: true
    headers:
      X-Scope-OrgID: default
service:
  pipelines:
    traces:
      exporters: [otlp/tempo]
"""


def check_config(cfg: Dict[str, Any]) -> Dict[str, Any]:
    exporters = cfg.get("exporters", {}) or {}
    pipelines = (cfg.get("service", {}) or {}).get("pipelines", {}) or {}
    traces_pipeline = pipelines.get("traces", {}) or {}
    enabled_exporters = traces_pipeline.get("exporters", []) or []

    findings: List[Dict[str, str]] = []
    checked_exporters: List[str] = []

    for exp_name, exp_cfg in exporters.items():
        if not str(exp_name).startswith(("otlp", "otlphttp")):
            continue
        checked_exporters.append(exp_name)
        exp_dict = exp_cfg or {}
        endpoint = str(exp_dict.get("endpoint", ""))
        headers = exp_dict.get("headers", {}) or {}

        if not endpoint:
            findings.append(
                {
                    "exporter": exp_name,
                    "issue": "MISSING_ENDPOINT",
                    "detail": "Exporter is missing 'endpoint'.",
                }
            )
        is_grpc_otlp = str(exp_name) == "otlp" or str(exp_name).startswith("otlp/")
        if is_grpc_otlp and ":4318" in endpoint:
            findings.append(
                {
                    "exporter": exp_name,
                    "issue": "PORT_PROTOCOL_MISMATCH",
                    "detail": "gRPC 'otlp' exporter points to HTTP port 4318 (expected 4317).",
                }
            )
        if str(exp_name).startswith("otlphttp") and ":4317" in endpoint:
            findings.append(
                {
                    "exporter": exp_name,
                    "issue": "PORT_PROTOCOL_MISMATCH",
                    "detail": "HTTP 'otlphttp' exporter points to gRPC port 4317 (expected 4318).",
                }
            )
        if "X-Scope-OrgID" not in headers and "x-scope-orgid" not in {
            k.lower() for k in headers
        }:
            findings.append(
                {
                    "exporter": exp_name,
                    "issue": "NO_TENANT_HEADER",
                    "detail": "No X-Scope-OrgID header configured (required when multitenancy_enabled=true).",
                }
            )
        if exp_name not in enabled_exporters:
            findings.append(
                {
                    "exporter": exp_name,
                    "issue": "NOT_IN_TRACES_PIPELINE",
                    "detail": f"Exporter '{exp_name}' is not listed in service.pipelines.traces.exporters.",
                }
            )

    return {
        "valid": len(findings) == 0,
        "checked_exporters": checked_exporters,
        "findings": findings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate OTel Collector OTLP exporter config for Tempo."
    )
    parser.add_argument("--file", help="Path to OTel Collector YAML config file (optional).")
    parser.add_argument("--yaml", dest="yaml_str", help="Inline OTel Collector YAML string (optional).")
    args = parser.parse_args()
    if args.yaml_str:
        raw = args.yaml_str
    elif args.file:
        with open(args.file, "r", encoding="utf-8") as fh:
            raw = fh.read()
    else:
        raw = SAMPLE_OTEL_CONFIG
    cfg = yaml.safe_load(raw) or {}
    print(json.dumps(check_config(cfg), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
