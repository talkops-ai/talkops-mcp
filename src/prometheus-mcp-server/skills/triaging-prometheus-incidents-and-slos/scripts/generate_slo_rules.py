#!/usr/bin/env python3
"""Deterministic local CLI to generate Google SRE multi-window multi-burn-rate SLO rules."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Dict, List

import yaml


def build_slo_rule_group(
    service: str,
    slo_target: float,
    error_metric: str,
    total_metric: str,
    interval: str = "30s",
) -> Dict[str, Any]:
    if not (0.5 < slo_target < 1.0):
        raise ValueError("slo_target must be between 0.5 and 1.0 (e.g. 0.999).")

    error_budget = round(1.0 - slo_target, 8)
    windows = ["5m", "30m", "1h", "2h", "6h", "24h", "72h"]

    rules: List[Dict[str, Any]] = []
    for w in windows:
        rules.append(
            {
                "record": f"job:slo_error_ratio:rate{w}",
                "expr": (
                    f"sum(rate({error_metric}[{w}])) / "
                    f"clamp_min(sum(rate({total_metric}[{w}])), 1e-9)"
                ),
                "labels": {"service": service, "slo_window": w},
            }
        )

    burn_tiers = [
        ("CriticalFastBurn", "1h", "5m", 14.4, "2m", "critical"),
        ("HighSustainedBurn", "6h", "30m", 6.0, "15m", "critical"),
        ("SlowDaytimeBurn", "24h", "2h", 3.0, "1h", "warning"),
        ("ChronicBudgetBurn", "72h", "6h", 1.0, "3h", "warning"),
    ]
    for suffix, long_w, short_w, factor, for_dur, severity in burn_tiers:
        threshold = round(factor * error_budget, 8)
        rules.append(
            {
                "alert": f"{service.capitalize()}SLO{suffix}",
                "expr": (
                    f'job:slo_error_ratio:rate{long_w}{{service="{service}"}} > {threshold} '
                    f"and "
                    f'job:slo_error_ratio:rate{short_w}{{service="{service}"}} > {threshold}'
                ),
                "for": for_dur,
                "labels": {
                    "service": service,
                    "severity": severity,
                    "burn_rate": f"{factor}x",
                },
                "annotations": {
                    "summary": (
                        f"Service {service} is burning SLO error budget at >={factor}x "
                        f"over {long_w}/{short_w} windows"
                    ),
                    "runbook_url": f"https://runbooks.example.com/slo/{service}",
                },
            }
        )

    return {
        "name": f"{service}-slo-multiwindow-rules",
        "interval": interval,
        "rules": rules,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate Google SRE multi-window SLO recording and alerting rules."
    )
    parser.add_argument("--service", required=True, help="Service name (e.g. checkout)")
    parser.add_argument(
        "--slo-target",
        type=float,
        default=0.999,
        help="Target SLO availability between 0.5 and 1.0 (default: 0.999)",
    )
    parser.add_argument(
        "--error-metric",
        required=True,
        help='Selector for error counter (e.g. http_requests_total{job="checkout",status=~"5.."})',
    )
    parser.add_argument(
        "--total-metric",
        required=True,
        help='Selector for total counter (e.g. http_requests_total{job="checkout"})',
    )
    parser.add_argument(
        "--format",
        choices=["yaml", "json"],
        default="yaml",
        help="Output format (yaml or json)",
    )
    args = parser.parse_args()

    try:
        group = build_slo_rule_group(
            service=args.service,
            slo_target=args.slo_target,
            error_metric=args.error_metric,
            total_metric=args.total_metric,
        )
    except ValueError as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 1

    if args.format == "json":
        print(json.dumps({"group": group}, indent=2))
    else:
        print(yaml.safe_dump({"groups": [group]}, sort_keys=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
