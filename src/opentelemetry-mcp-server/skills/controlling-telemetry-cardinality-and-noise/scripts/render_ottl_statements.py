#!/usr/bin/env python3
"""Offline generator for OpenTelemetry Collector OTTL transform and filter processor blocks.

Usage:
    python scripts/render_ottl_statements.py \
        --parse-json-logs --redact-pii \
        --drop-attributes url.query,client.port,user.id \
        --drop-noise-paths /healthz,/readyz,/metrics
"""

from __future__ import annotations

import argparse
import sys

import yaml


def render_ottl_processors(
    parse_json_logs: bool,
    redact_pii: bool,
    drop_attributes: list[str],
    drop_noise_paths: list[str],
) -> dict:
    processors: dict = {}

    trace_statements: list[str] = []
    metric_statements: list[str] = []
    log_statements: list[str] = []

    for attr in drop_attributes:
        trace_statements.append(f'delete_key(attributes, "{attr}")')
        metric_statements.append(f'delete_key(attributes, "{attr}")')
        log_statements.append(f'delete_key(attributes, "{attr}")')

    if redact_pii:
        pii_patterns = [
            (r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", "[REDACTED_EMAIL]"),
            (r"\b\d{3}-\d{2}-\d{4}\b", "[REDACTED_SSN]"),
            (r"(?i)bearer\s+[a-zA-Z0-9_\-\.=]+", "Bearer [REDACTED_TOKEN]"),
        ]
        trace_statements.append('delete_key(attributes, "http.request.header.authorization")')
        trace_statements.append('delete_key(attributes, "http.request.header.cookie")')
        for pattern, replacement in pii_patterns:
            escaped = pattern.replace("\\", "\\\\")
            log_statements.append(
                f'replace_pattern(body.string, "{escaped}", "{replacement}") where body.string != nil'
            )

    if parse_json_logs:
        log_statements.extend(
            [
                'merge_maps(attributes, ParseJSON(body.string), "upsert") where IsMatch(body.string, "^\\\\{.*\\\\}$")',
                'set(severity_text, attributes["level"]) where attributes["level"] != nil',
                'set(trace_id.string, attributes["trace_id"]) where attributes["trace_id"] != nil',
                'set(span_id.string, attributes["span_id"]) where attributes["span_id"] != nil',
            ]
        )

    if trace_statements or metric_statements or log_statements:
        transform_cfg: dict = {"error_mode": "ignore"}
        if trace_statements:
            transform_cfg["trace_statements"] = [{"context": "span", "statements": trace_statements}]
        if metric_statements:
            transform_cfg["metric_statements"] = [
                {"context": "datapoint", "statements": metric_statements}
            ]
        if log_statements:
            transform_cfg["log_statements"] = [{"context": "log", "statements": log_statements}]
        processors["transform/ottl"] = transform_cfg

    if drop_noise_paths:
        span_conds = []
        log_conds = []
        for path in drop_noise_paths:
            span_conds.append(f'attributes["url.path"] == "{path}"')
            span_conds.append(f'attributes["http.target"] == "{path}"')
            log_conds.append(f'IsMatch(body.string, "{path}")')
        processors["filter/drop_noise"] = {
            "error_mode": "ignore",
            "traces": {"span": span_conds},
            "logs": {"log_record": log_conds},
        }

    return {"processors": processors}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Render OTTL transform and filter processor configurations offline."
    )
    parser.add_argument(
        "--parse-json-logs",
        action="store_true",
        help="Include OTTL statements to parse JSON log bodies and extract trace/span IDs.",
    )
    parser.add_argument(
        "--redact-pii",
        action="store_true",
        help="Include OTTL statements to scrub emails, SSNs, auth headers, and Bearer tokens.",
    )
    parser.add_argument(
        "--drop-attributes",
        default="",
        help="Comma-separated attribute keys to delete across spans, datapoints, and logs.",
    )
    parser.add_argument(
        "--drop-noise-paths",
        default="",
        help="Comma-separated URL paths (e.g. /healthz,/readyz,/metrics) to drop.",
    )
    args = parser.parse_args(argv)

    drop_attrs = [a.strip() for a in args.drop_attributes.split(",") if a.strip()]
    drop_paths = [p.strip() for p in args.drop_noise_paths.split(",") if p.strip()]

    if not (args.parse_json_logs or args.redact_pii or drop_attrs or drop_paths):
        print(
            "Error: Specify at least one of --parse-json-logs, --redact-pii, "
            "--drop-attributes, or --drop-noise-paths.",
            file=sys.stderr,
        )
        return 1

    result = render_ottl_processors(
        parse_json_logs=args.parse_json_logs,
        redact_pii=args.redact_pii,
        drop_attributes=drop_attrs,
        drop_noise_paths=drop_paths,
    )
    print(yaml.safe_dump(result, sort_keys=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
