#!/usr/bin/env python3
"""Offline parser that summarizes Kargo v1.12 Promotion or AnalysisRun failure payloads.

Reads a Promotion or AnalysisRun JSON/YAML document from --input and outputs a structured
JSON failure report with failed steps/metrics, error messages, and recommended diagnosis codes.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml


def summarize_payload(doc: dict[str, Any]) -> dict[str, Any]:
    kind = str(doc.get("kind") or "Promotion")
    meta = doc.get("metadata") or {}
    name = str(meta.get("name") or "<unknown>")
    namespace = str(meta.get("namespace") or "<unknown>")
    status = doc.get("status") or {}
    phase = str(status.get("phase") or "Unknown")
    message = str(status.get("message") or "")

    failed_items: list[dict[str, Any]] = []
    diagnosis_code = "HEALTHY"

    if kind == "AnalysisRun":
        for metric in status.get("metricResults") or []:
            if isinstance(metric, dict) and metric.get("phase") in ("Failed", "Error"):
                failed_items.append(
                    {
                        "name": metric.get("name"),
                        "phase": metric.get("phase"),
                        "message": metric.get("message"),
                    }
                )
        if phase in ("Failed", "Error") or failed_items:
            diagnosis_code = "VERIFICATION_FAILED"
    else:
        for step in status.get("stepExecutionMetadata") or []:
            if isinstance(step, dict) and step.get("status") in ("Errored", "Failed"):
                failed_items.append(
                    {
                        "alias": step.get("alias"),
                        "status": step.get("status"),
                        "message": step.get("message"),
                    }
                )
        combined_msg = (
            message + " " + " ".join(str(i.get("message") or "") for i in failed_items)
        ).lower()
        if phase in ("Errored", "Failed") or failed_items:
            if any(
                tok in combined_msg
                for tok in (
                    "401",
                    "403",
                    "unauthorized",
                    "authentication",
                    "credentials",
                    "could not read username",
                    "could not read password",
                    "terminal prompts disabled",
                    "permission denied",
                )
            ):
                diagnosis_code = "GIT_OR_REGISTRY_AUTH_ERROR"
            elif "argocd" in combined_msg or "authorized-stage" in combined_msg:
                diagnosis_code = "ARGOCD_SYNC_OR_AUTH_FAILED"
            else:
                diagnosis_code = "PROMOTION_STEP_FAILED"

    return {
        "kind": kind,
        "name": name,
        "namespace": namespace,
        "phase": phase,
        "message": message,
        "diagnosis_code": diagnosis_code,
        "failed_items": failed_items,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Summarize a Kargo v1.12 Promotion or AnalysisRun JSON/YAML failure payload."
    )
    parser.add_argument(
        "--input",
        "-i",
        required=True,
        help="Path to Promotion or AnalysisRun JSON or YAML file.",
    )
    args = parser.parse_args(argv)

    raw = Path(args.input).read_text(encoding="utf-8")
    doc = yaml.safe_load(raw)
    if not isinstance(doc, dict):
        raise ValueError("Input file must contain a JSON/YAML object.")
    summary = summarize_payload(doc)
    sys.stdout.write(json.dumps(summary, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
