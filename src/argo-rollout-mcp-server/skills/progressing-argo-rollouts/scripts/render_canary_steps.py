#!/usr/bin/env python3
"""Offline generator for Argo Rollouts canary step arrays."""

import argparse
import json
import sys


PROFILES = {
    "conservative": [5, 10, 25, 50, 75],
    "standard": [5, 25, 50],
    "fast": [20, 50],
    "cost-optimized": [5, 25, 50],
}


def render_steps(
    profile: str = "standard",
    pause_duration: str = "5m",
    analysis_template: str | None = None,
    use_canary_scale: bool = False,
) -> list[dict]:
    if profile not in PROFILES:
        raise ValueError(f"Unknown profile '{profile}'. Choose from: {', '.join(PROFILES)}")

    weights = PROFILES[profile]
    cost_mode = use_canary_scale or profile == "cost-optimized"
    steps: list[dict] = []

    for idx, weight in enumerate(weights):
        if cost_mode and idx == 0:
            steps.append({"setCanaryScale": {"replicas": 1}})
        elif cost_mode and idx == 1:
            steps.append({"setCanaryScale": {"matchTrafficWeight": True}})

        steps.append({"setWeight": weight})
        if idx == len(weights) - 1:
            steps.append({"pause": {}})
        else:
            steps.append({"pause": {"duration": pause_duration}})

        if analysis_template:
            steps.append(
                {
                    "analysis": {
                        "templates": [{"templateName": analysis_template}],
                    }
                }
            )

    return steps


def main() -> int:
    parser = argparse.ArgumentParser(description="Render an Argo Rollouts canary steps JSON array.")
    parser.add_argument(
        "--profile",
        choices=list(PROFILES.keys()),
        default="standard",
        help="Canary progression profile",
    )
    parser.add_argument("--pause-duration", type=str, default="5m", help="Pause duration between steps (e.g. '2m', '5m')")
    parser.add_argument("--analysis-template", type=str, default=None, help="Optional AnalysisTemplate name to inline after each pause")
    parser.add_argument("--use-canary-scale", action="store_true", help="Include setCanaryScale steps for cost optimization")
    args = parser.parse_args()

    try:
        steps = render_steps(
            profile=args.profile,
            pause_duration=args.pause_duration,
            analysis_template=args.analysis_template,
            use_canary_scale=args.use_canary_scale,
        )
        print(json.dumps(steps, indent=2))
        return 0
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
