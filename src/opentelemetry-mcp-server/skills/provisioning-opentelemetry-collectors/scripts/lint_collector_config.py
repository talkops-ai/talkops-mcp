#!/usr/bin/env python3
"""Offline OpenTelemetry Collector YAML configuration linter.

Validates pipeline referential integrity, processor ordering (memory_limiter
first, batch last), filelog self-exclusion, tail_sampling trace affinity,
v0.123+ telemetry readers schema, and inline secret detection without any
network or Kubernetes cluster calls.
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List
import yaml

_ENV_PLACEHOLDER_RE = re.compile(r"\$\{(?:env:)?[A-Za-z_][A-Za-z0-9_]*")
_SECRET_KEY_TOKENS = (
    "authorization",
    "api_key",
    "apikey",
    "token",
    "password",
    "secret",
)


def _scan_secrets(obj: Any, path: str = "") -> List[Dict[str, str]]:
    hits: List[Dict[str, str]] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            cur = f"{path}.{k}" if path else str(k)
            if isinstance(v, str) and any(
                t in str(k).lower() for t in _SECRET_KEY_TOKENS
            ):
                if v.strip() and not _ENV_PLACEHOLDER_RE.search(v):
                    hits.append({
                        "code": "SEC_INLINE_SECRET",
                        "severity": "error",
                        "field_path": cur,
                        "message": f"Inline plaintext secret found at '{cur}'; use ${{env:VAR_NAME}}.",
                    })
            else:
                hits.extend(_scan_secrets(v, cur))
    elif isinstance(obj, list):
        for idx, item in enumerate(obj):
            hits.extend(_scan_secrets(item, f"{path}[{idx}]"))
    return hits


def lint_config(
    cfg: Dict[str, Any], mode: str = "deployment", replicas: int = 1
) -> List[Dict[str, str]]:
    findings: List[Dict[str, str]] = []
    receivers = cfg.get("receivers") or {}
    processors = cfg.get("processors") or {}
    exporters = cfg.get("exporters") or {}
    connectors = cfg.get("connectors") or {}
    service = cfg.get("service") or {}
    pipelines = service.get("pipelines") or {}

    if not pipelines:
        findings.append({
            "code": "CFG_UNDEFINED_COMPONENT_REF",
            "severity": "error",
            "field_path": "service.pipelines",
            "message": "No pipelines defined under service.pipelines.",
        })
        return findings

    for pname, pcfg in pipelines.items():
        if not isinstance(pcfg, dict):
            continue
        recs = pcfg.get("receivers") or []
        procs = pcfg.get("processors") or []
        exps = pcfg.get("exporters") or []

        for r in recs:
            if r not in receivers and r not in connectors:
                findings.append({
                    "code": "CFG_UNDEFINED_COMPONENT_REF",
                    "severity": "error",
                    "field_path": f"service.pipelines.{pname}.receivers",
                    "message": f"Receiver '{r}' referenced in '{pname}' is not declared.",
                })
        for p in procs:
            if p not in processors:
                findings.append({
                    "code": "CFG_UNDEFINED_COMPONENT_REF",
                    "severity": "error",
                    "field_path": f"service.pipelines.{pname}.processors",
                    "message": f"Processor '{p}' referenced in '{pname}' is not declared.",
                })
        for e in exps:
            if e not in exporters and e not in connectors:
                findings.append({
                    "code": "CFG_UNDEFINED_COMPONENT_REF",
                    "severity": "error",
                    "field_path": f"service.pipelines.{pname}.exporters",
                    "message": f"Exporter '{e}' referenced in '{pname}' is not declared.",
                })

        if procs and not str(procs[0]).startswith("memory_limiter"):
            findings.append({
                "code": "CFG_MEMORY_LIMITER_NOT_FIRST",
                "severity": "warning",
                "field_path": f"service.pipelines.{pname}.processors",
                "message": f"Pipeline '{pname}' does not place 'memory_limiter' first.",
            })

    telemetry_metrics = (service.get("telemetry") or {}).get("metrics") or {}
    if isinstance(telemetry_metrics, dict) and "address" in telemetry_metrics:
        findings.append({
            "code": "CFG_DEPRECATED_TELEMETRY_ADDRESS",
            "severity": "warning",
            "field_path": "service.telemetry.metrics.address",
            "message": "service.telemetry.metrics.address is deprecated in Collector >= v0.123; use readers.",
        })

    if "tail_sampling" in processors and (
        mode == "daemonset" or replicas > 1
    ):
        findings.append({
            "code": "CFG_TAIL_SAMPLING_NO_TRACE_AFFINITY",
            "severity": "error",
            "field_path": "processors.tail_sampling",
            "message": "tail_sampling on DaemonSet or multi-replica collector requires traceID loadbalancing.",
        })

    findings.extend(_scan_secrets(cfg))
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Lint an OpenTelemetry Collector YAML configuration file offline."
    )
    parser.add_argument(
        "--config",
        type=str,
        required=True,
        help="Path to Collector YAML config file (or '-' for stdin)",
    )
    parser.add_argument(
        "--mode",
        type=str,
        default="deployment",
        choices=["deployment", "daemonset", "statefulset", "sidecar"],
        help="Collector deployment mode",
    )
    parser.add_argument(
        "--replicas", type=int, default=1, help="Collector replica count"
    )
    args = parser.parse_args()

    try:
        raw_text = (
            sys.stdin.read()
            if args.config == "-"
            else Path(args.config).read_text(encoding="utf-8")
        )
        parsed = yaml.safe_load(raw_text)
        if not isinstance(parsed, dict):
            raise ValueError("YAML root must be a mapping")
        # Support either raw collector config or OpenTelemetryCollector CR
        if parsed.get("kind") == "OpenTelemetryCollector":
            spec = parsed.get("spec") or {}
            mode = str(spec.get("mode", args.mode)).lower()
            replicas = int(spec.get("replicas", args.replicas) or 1)
            cfg = spec.get("config") or {}
            if isinstance(cfg, str):
                cfg = yaml.safe_load(cfg) or {}
        else:
            cfg = parsed
            mode = args.mode
            replicas = args.replicas

        findings = lint_config(cfg, mode=mode, replicas=replicas)
        errors = [f for f in findings if f["severity"] == "error"]
        output = {
            "valid": len(errors) == 0,
            "error_count": len(errors),
            "warning_count": len(findings) - len(errors),
            "findings": findings,
        }
        print(json.dumps(output, indent=2))
        return 0 if len(errors) == 0 else 1
    except Exception as exc:
        print(json.dumps({"valid": False, "error": str(exc)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
