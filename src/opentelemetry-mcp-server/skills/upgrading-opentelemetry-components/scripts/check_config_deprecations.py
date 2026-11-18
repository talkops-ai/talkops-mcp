#!/usr/bin/env python3
"""Offline scanner for deprecated/removed OpenTelemetry Collector configuration fields.

Detects removed components and syntax across Collector v0.100 - v0.152+:
- logging exporter (replaced by debug exporter)
- memory_ballast extension (replaced by GOMEMLIMIT + memory_limiter)
- service.telemetry.metrics.address (replaced by service.telemetry.metrics.readers)
- legacy HTTP semantic conventions in spanmetrics dimensions

Usage:
    python scripts/check_config_deprecations.py --file collector-config.yaml
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml


def scan_deprecations(cfg: dict) -> list[dict[str, str]]:
    deprecations: list[dict[str, str]] = []

    exporters = cfg.get("exporters") or {}
    for exp_name in exporters:
        base_type = exp_name.split("/")[0]
        if base_type == "logging":
            deprecations.append(
                {
                    "code": "DEP_LOGGING_EXPORTER_REMOVED",
                    "severity": "ERROR",
                    "field_path": f"exporters.{exp_name}",
                    "message": (
                        f"Exporter '{exp_name}' uses removed 'logging' exporter (removed in v0.111.0)."
                    ),
                    "replacement": "Replace 'logging' with 'debug: {verbosity: normal}'.",
                }
            )
        if base_type == "opencensus":
            deprecations.append(
                {
                    "code": "DEP_OPENCENSUS_DEPRECATED",
                    "severity": "WARNING",
                    "field_path": f"exporters.{exp_name}",
                    "message": f"Exporter '{exp_name}' uses deprecated 'opencensus' exporter.",
                    "replacement": "Migrate to 'otlp' or 'otlphttp' exporter.",
                }
            )

    extensions = cfg.get("extensions") or {}
    for ext_name in extensions:
        base_type = ext_name.split("/")[0]
        if base_type == "memory_ballast":
            deprecations.append(
                {
                    "code": "DEP_MEMORY_BALLAST_REMOVED",
                    "severity": "ERROR",
                    "field_path": f"extensions.{ext_name}",
                    "message": (
                        f"Extension '{ext_name}' uses removed 'memory_ballast' extension."
                    ),
                    "replacement": "Remove 'memory_ballast' and set GOMEMLIMIT=80% of container memory limit.",
                }
            )

    service = cfg.get("service") or {}
    telemetry = service.get("telemetry") or {}
    metrics = telemetry.get("metrics") or {}
    if isinstance(metrics, dict) and "address" in metrics:
        deprecations.append(
            {
                "code": "DEP_TELEMETRY_METRICS_ADDRESS_REMOVED",
                "severity": "ERROR",
                "field_path": "service.telemetry.metrics.address",
                "message": (
                    "'service.telemetry.metrics.address' is removed in Collector v0.120.0+ "
                    "and causes startup failure."
                ),
                "replacement": (
                    "Use 'service.telemetry.metrics.readers: [{pull: {exporter: "
                    "{prometheus: {host: 0.0.0.0, port: 8888}}}}]'."
                ),
            }
        )

    connectors = cfg.get("connectors") or {}
    spanmetrics = connectors.get("spanmetrics") or {}
    if isinstance(spanmetrics, dict):
        dims = spanmetrics.get("dimensions") or []
        legacy_dims = {"http.method": "http.request.method", "http.status_code": "http.response.status_code"}
        for item in dims:
            dname = item.get("name") if isinstance(item, dict) else str(item)
            if dname in legacy_dims:
                deprecations.append(
                    {
                        "code": "DEP_LEGACY_SEMCONV_DIMENSION",
                        "severity": "WARNING",
                        "field_path": f"connectors.spanmetrics.dimensions.{dname}",
                        "message": f"Dimension '{dname}' uses legacy HTTP semantic convention.",
                        "replacement": f"Use stable attribute '{legacy_dims[dname]}'.",
                    }
                )

    return deprecations


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check OpenTelemetry Collector YAML for removed or deprecated syntax."
    )
    parser.add_argument("--file", required=True, help="Path to Collector YAML configuration file.")
    args = parser.parse_args(argv)

    path = Path(args.file)
    if not path.exists():
        print(json.dumps({"compatible": False, "error": f"File not found: {path}"}), file=sys.stderr)
        return 1

    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(json.dumps({"compatible": False, "error": f"Invalid YAML: {exc}"}), file=sys.stderr)
        return 1

    if not isinstance(raw, dict):
        print(
            json.dumps({"compatible": False, "error": "YAML root must be a mapping"}),
            file=sys.stderr,
        )
        return 1

    cfg = raw.get("spec", {}).get("config", raw) if "spec" in raw else raw
    if isinstance(cfg, str):
        try:
            cfg = yaml.safe_load(cfg)
        except Exception as exc:
            print(json.dumps({"compatible": False, "error": f"Invalid spec.config YAML string: {exc}"}), file=sys.stderr)
            return 1
    if not isinstance(cfg, dict):
        print(
            json.dumps({"compatible": False, "error": "Config section must be a mapping"}),
            file=sys.stderr,
        )
        return 1

    deprecations = scan_deprecations(cfg)
    errors = [d for d in deprecations if d["severity"] == "ERROR"]
    report = {
        "compatible": len(errors) == 0,
        "error_count": len(errors),
        "warning_count": len(deprecations) - len(errors),
        "deprecations": deprecations,
    }
    print(json.dumps(report, indent=2))
    return 0 if len(errors) == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
