#!/usr/bin/env python3
"""Offline analyzer for OpenTelemetry Collector Prometheus internal metrics (:8888/metrics).

Parses raw Prometheus text format from a file and emits structured JSON with
accepted, refused, sent, failed, enqueue_failed counters, queue utilization,
and deterministic RT_* findings.

Usage:
    python scripts/analyze_internal_metrics.py --file metrics.txt
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

METRIC_LINE_RE = re.compile(
    r"^(?P<name>[a-zA-Z_:][a-zA-Z0-9_:]*)(?:\{[^}]*\})?\s+(?P<value>[-+]?[0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?)$"
)


def parse_prometheus_text(text: str) -> dict[str, float]:
    totals: dict[str, float] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = METRIC_LINE_RE.match(line)
        if not match:
            continue
        name = match.group("name")
        if name.endswith("_total"):
            base = name[: -len("_total")]
            totals[base] = totals.get(base, 0.0) + float(match.group("value"))
        totals[name] = totals.get(name, 0.0) + float(match.group("value"))
    return totals


def evaluate_metrics(totals: dict[str, float], memory_limit_mib: int | None = None) -> dict:
    accepted = (
        totals.get("otelcol_receiver_accepted_spans", 0.0)
        + totals.get("otelcol_receiver_accepted_metric_points", 0.0)
        + totals.get("otelcol_receiver_accepted_log_records", 0.0)
    )
    refused = (
        totals.get("otelcol_receiver_refused_spans", 0.0)
        + totals.get("otelcol_receiver_refused_metric_points", 0.0)
        + totals.get("otelcol_receiver_refused_log_records", 0.0)
        + totals.get("otelcol_processor_refused_spans", 0.0)
        + totals.get("otelcol_processor_refused_metric_points", 0.0)
        + totals.get("otelcol_processor_refused_log_records", 0.0)
    )
    sent = (
        totals.get("otelcol_exporter_sent_spans", 0.0)
        + totals.get("otelcol_exporter_sent_metric_points", 0.0)
        + totals.get("otelcol_exporter_sent_log_records", 0.0)
    )
    send_failed = (
        totals.get("otelcol_exporter_send_failed_spans", 0.0)
        + totals.get("otelcol_exporter_send_failed_metric_points", 0.0)
        + totals.get("otelcol_exporter_send_failed_log_records", 0.0)
    )
    enqueue_failed = (
        totals.get("otelcol_exporter_enqueue_failed_spans", 0.0)
        + totals.get("otelcol_exporter_enqueue_failed_metric_points", 0.0)
        + totals.get("otelcol_exporter_enqueue_failed_log_records", 0.0)
    )

    queue_size = totals.get("otelcol_exporter_queue_size", 0.0)
    queue_capacity = totals.get("otelcol_exporter_queue_capacity", 0.0)
    queue_utilization = (queue_size / queue_capacity) if queue_capacity > 0 else 0.0

    rss_bytes = totals.get("otelcol_process_memory_rss", 0.0)
    rss_mib = round(rss_bytes / (1024 * 1024), 2)

    findings: list[dict[str, str]] = []
    if send_failed > 0 or enqueue_failed > 0:
        findings.append(
            {
                "code": "RT_EXPORTER_DROPPING_DATA",
                "severity": "ERROR",
                "message": (
                    f"Exporter dropped data: send_failed={int(send_failed)}, "
                    f"enqueue_failed={int(enqueue_failed)}."
                ),
            }
        )
    if refused > 0:
        findings.append(
            {
                "code": "RT_RECEIVER_REFUSING_DATA",
                "severity": "ERROR",
                "message": f"Receiver/processor refused {int(refused)} items due to backpressure.",
            }
        )
    if queue_utilization > 0.80:
        findings.append(
            {
                "code": "RT_QUEUE_SATURATED",
                "severity": "WARNING",
                "message": f"Exporter sending queue is {queue_utilization * 100:.1f}% full.",
            }
        )
    if memory_limit_mib and rss_mib > 0.85 * memory_limit_mib:
        findings.append(
            {
                "code": "RT_MEMORY_PRESSURE",
                "severity": "WARNING",
                "message": (
                    f"Process RSS ({rss_mib} MiB) exceeds 85% of limit ({memory_limit_mib} MiB)."
                ),
            }
        )

    return {
        "summary": {
            "accepted_total": int(accepted),
            "refused_total": int(refused),
            "sent_total": int(sent),
            "send_failed_total": int(send_failed),
            "enqueue_failed_total": int(enqueue_failed),
            "queue_size": int(queue_size),
            "queue_capacity": int(queue_capacity),
            "queue_utilization_ratio": round(queue_utilization, 4),
            "memory_rss_mib": rss_mib,
        },
        "findings": findings,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Analyze OpenTelemetry Collector internal Prometheus metrics offline."
    )
    parser.add_argument("--file", required=True, help="Path to Prometheus metrics text file.")
    parser.add_argument(
        "--memory-limit-mib",
        type=int,
        default=None,
        help="Optional container memory limit in MiB for RT_MEMORY_PRESSURE calculation.",
    )
    args = parser.parse_args(argv)

    path = Path(args.file)
    if not path.exists():
        print(json.dumps({"error": f"File not found: {path}"}), file=sys.stderr)
        return 1

    text = path.read_text(encoding="utf-8")
    totals = parse_prometheus_text(text)
    if not totals:
        print(json.dumps({"error": "No valid Prometheus metrics found in file"}), file=sys.stderr)
        return 1

    report = evaluate_metrics(totals, args.memory_limit_mib)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
