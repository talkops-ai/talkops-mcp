#!/usr/bin/env python3
"""Offline generator for ArgoCD Application ignoreDifferences YAML snippets."""

import argparse
import sys
try:
    import yaml
except ModuleNotFoundError:
    import os as _os, shutil as _shutil, subprocess as _sp
    if _shutil.which("uv") and not _os.environ.get("_UV_YAML_BOOTSTRAPPED"):
        raise SystemExit(
            _sp.call(
                ["uv", "run", "--quiet", "--with", "pyyaml", "python3", *sys.argv],
                env={**_os.environ, "_UV_YAML_BOOTSTRAPPED": "1"},
            )
        )
    raise


def build_ignore_differences(
    include_traefik_service: bool = True,
    include_rollout_status: bool = True,
    include_rollout_traffic_routing: bool = False,
    include_analysis_run: bool = False,
    include_deployment_replicas: bool = False,
    deployment_name: str | None = None,
    traefik_api_group: str = "traefik.io",
) -> str:
    ignore_diffs = []
    if include_deployment_replicas:
        dep_entry: dict = {
            "group": "apps",
            "kind": "Deployment",
            "jsonPointers": ["/spec/replicas"],
        }
        if deployment_name:
            dep_entry["name"] = deployment_name
        ignore_diffs.append(dep_entry)

    if include_traefik_service:
        ignore_diffs.append(
            {
                "group": traefik_api_group,
                "kind": "TraefikService",
                "jsonPointers": ["/spec/weighted/services"],
            }
        )

    if include_rollout_status:
        ignore_diffs.append(
            {
                "group": "argoproj.io",
                "kind": "Rollout",
                "jsonPointers": ["/status"],
            }
        )

    if include_rollout_traffic_routing:
        ignore_diffs.append(
            {
                "group": "argoproj.io",
                "kind": "Rollout",
                "jsonPointers": [
                    "/spec/strategy/canary/trafficRouting",
                    "/spec/strategy/blueGreen/trafficRouting",
                ],
            }
        )

    if include_analysis_run:
        ignore_diffs.append(
            {
                "group": "argoproj.io",
                "kind": "AnalysisRun",
                "jsonPointers": ["/status"],
            }
        )

    if not ignore_diffs:
        raise ValueError("At least one ignoreDifferences option must be enabled")

    snippet = {
        "apiVersion": "argoproj.io/v1alpha1",
        "kind": "Application",
        "spec": {"ignoreDifferences": ignore_diffs},
    }
    return yaml.dump(snippet, default_flow_style=False, sort_keys=False)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate ArgoCD Application ignoreDifferences YAML snippet.")
    parser.add_argument("--include-traefik-service", action="store_true", default=True)
    parser.add_argument("--no-traefik-service", action="store_false", dest="include_traefik_service")
    parser.add_argument("--include-rollout-status", action="store_true", default=True)
    parser.add_argument("--include-rollout-traffic-routing", action="store_true", default=False)
    parser.add_argument("--include-analysis-run", action="store_true", default=False)
    parser.add_argument("--include-deployment-replicas", action="store_true", default=False)
    parser.add_argument("--deployment-name", type=str, default=None)
    parser.add_argument("--traefik-api-group", type=str, default="traefik.io")
    args = parser.parse_args()

    try:
        out = build_ignore_differences(
            include_traefik_service=args.include_traefik_service,
            include_rollout_status=args.include_rollout_status,
            include_rollout_traffic_routing=args.include_rollout_traffic_routing,
            include_analysis_run=args.include_analysis_run,
            include_deployment_replicas=args.include_deployment_replicas,
            deployment_name=args.deployment_name,
            traefik_api_group=args.traefik_api_group,
        )
        print(out, end="")
        return 0
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
