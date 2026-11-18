#!/usr/bin/env python3
"""Deterministic CLI to build a `promtool test rules` unit test suite."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Dict, List


def parse_kv_pairs(raw: str) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for item in (raw or "").split(","):
        item = item.strip()
        if not item:
            continue
        if "=" not in item:
            raise ValueError(f"Invalid key=value pair '{item}'.")
        k, v = item.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def build_test_suite(
    alert: str,
    expr: str,
    for_duration: str,
    series: str,
    values: str,
    eval_time: str,
    exp_labels: Dict[str, str],
    interval: str = "1m",
) -> Dict[str, Any]:
    rule_group = {
        "name": f"{alert.lower()}-group",
        "interval": interval,
        "rules": [
            {
                "alert": alert,
                "expr": expr,
                "for": for_duration,
                "labels": {k: v for k, v in exp_labels.items() if k != "alertname"},
                "annotations": {
                    "summary": f"{alert} triggered",
                },
            }
        ],
    }
    unit_tests: List[Dict[str, Any]] = [
        {
            "interval": interval,
            "input_series": [{"series": series, "values": values}],
            "alert_rule_test": [
                {
                    "eval_time": eval_time,
                    "alertname": alert,
                    "exp_alerts": [{"exp_labels": exp_labels}],
                }
            ],
        }
    ]
    return {"rule_group": rule_group, "unit_tests": unit_tests}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a promtool rule_group and unit_tests payload."
    )
    parser.add_argument("--alert", required=True, help="Alert name (e.g. HighErrorRate)")
    parser.add_argument("--expr", required=True, help="PromQL alert expression")
    parser.add_argument("--for-duration", default="5m", help="Alert 'for' duration")
    parser.add_argument("--series", required=True, help="Input series selector")
    parser.add_argument("--values", required=True, help="Promtool series values (e.g. '10+0x10')")
    parser.add_argument("--eval-time", default="10m", help="Evaluation timestamp (e.g. '10m')")
    parser.add_argument(
        "--exp-labels",
        required=True,
        help="Comma-separated expected labels (e.g. 'alertname=HighErrorRate,severity=critical')",
    )
    args = parser.parse_args()

    try:
        labels = parse_kv_pairs(args.exp_labels)
        payload = build_test_suite(
            alert=args.alert,
            expr=args.expr,
            for_duration=args.for_duration,
            series=args.series,
            values=args.values,
            eval_time=args.eval_time,
            exp_labels=labels,
        )
    except ValueError as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 1

    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
