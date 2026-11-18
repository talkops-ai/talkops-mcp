#!/usr/bin/env python3
"""Deterministic local CLI to generate Prometheus FinOps relabel and remote_write configs."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Dict

import yaml


def generate_relabel_config(
    action: str,
    regex: str,
    source_labels: list[str],
    target_label: str | None = None,
    replacement: str | None = None,
) -> Dict[str, Any]:
    rule: Dict[str, Any] = {"action": action, "regex": regex}
    if action in ("labeldrop", "labelkeep"):
        pass
    else:
        rule["source_labels"] = source_labels
        if target_label:
            rule["target_label"] = target_label
        if replacement is not None:
            rule["replacement"] = replacement

    crd_rule: Dict[str, Any] = {"action": action, "regex": regex}
    if "source_labels" in rule:
        crd_rule["sourceLabels"] = rule["source_labels"]
    if target_label:
        crd_rule["targetLabel"] = target_label
    if replacement is not None:
        crd_rule["replacement"] = replacement

    return {
        "prometheus_yaml": {"metric_relabel_configs": [rule]},
        "operator_crd_spec": {"metricRelabelings": [crd_rule]},
    }


def generate_remote_write_config(
    remote_url: str,
    keep_regex: str | None,
    max_shards: int = 50,
    max_samples_per_send: int = 2000,
) -> Dict[str, Any]:
    entry: Dict[str, Any] = {
        "url": remote_url,
        "queue_config": {
            "capacity": max_samples_per_send * 5,
            "max_shards": max_shards,
            "min_shards": 1,
            "max_samples_per_send": max_samples_per_send,
            "batch_send_deadline": "5s",
        },
    }
    if keep_regex:
        entry["write_relabel_configs"] = [
            {
                "source_labels": ["__name__"],
                "regex": keep_regex,
                "action": "keep",
            }
        ]
    return {"remote_write": [entry]}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate Prometheus metric_relabel_configs or remote_write YAML."
    )
    parser.add_argument(
        "--mode",
        choices=["relabel", "remote_write"],
        required=True,
        help="Configuration mode: relabel or remote_write",
    )
    parser.add_argument(
        "--action",
        choices=["drop", "keep", "labeldrop", "labelkeep", "replace", "hashmod"],
        default="drop",
        help="Relabel action (for --mode relabel)",
    )
    parser.add_argument("--regex", default=".*", help="Regex pattern for relabeling")
    parser.add_argument(
        "--source-labels",
        default="__name__",
        help="Comma-separated source labels (default: __name__)",
    )
    parser.add_argument("--target-label", default=None, help="Optional target_label")
    parser.add_argument("--replacement", default=None, help="Optional replacement string")
    parser.add_argument("--remote-url", default=None, help="Remote write endpoint URL")
    parser.add_argument("--keep-regex", default=None, help="Regex of metrics to keep in remote_write")
    parser.add_argument(
        "--format",
        choices=["yaml", "json"],
        default="yaml",
        help="Output format (yaml or json)",
    )
    args = parser.parse_args()

    if args.mode == "relabel":
        src_labels = [s.strip() for s in args.source_labels.split(",") if s.strip()]
        payload = generate_relabel_config(
            action=args.action,
            regex=args.regex,
            source_labels=src_labels,
            target_label=args.target_label,
            replacement=args.replacement,
        )
    else:
        if not args.remote_url or not args.remote_url.startswith(("http://", "https://")):
            print(
                json.dumps({"error": "--remote-url must be a valid http(s):// URL"}),
                file=sys.stderr,
            )
            return 1
        payload = generate_remote_write_config(
            remote_url=args.remote_url,
            keep_regex=args.keep_regex,
        )

    if args.format == "json":
        print(json.dumps(payload, indent=2))
    else:
        print(yaml.safe_dump(payload, sort_keys=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
