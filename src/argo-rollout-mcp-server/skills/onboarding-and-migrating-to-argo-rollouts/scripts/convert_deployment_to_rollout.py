#!/usr/bin/env python3
"""Offline Deployment-to-Rollout YAML converter (plus stable/canary or active/preview Services)."""

import argparse
import sys
from pathlib import Path
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

CONTROLLER_ANNOTATIONS = {
    "deployment.kubernetes.io/revision",
    "rollout.argoproj.io/revision",
    "kubectl.kubernetes.io/last-applied-configuration",
}


def extract_container_port(pod_spec: dict) -> int:
    for container in (pod_spec or {}).get("containers", []):
        for p in container.get("ports", []):
            if p.get("containerPort") is not None:
                return int(p["containerPort"])
    return 80


def convert_deployment(
    dep: dict,
    strategy: str = "canary",
    migration_mode: str = "direct",
    scale_down: str = "onsuccess",
    traefik_service: str | None = None,
    include_services: bool = False,
    service_port: int = 80,
) -> str:
    if not isinstance(dep, dict) or dep.get("kind") != "Deployment":
        raise ValueError(f"Input must be kind: Deployment, got: {dep.get('kind') if isinstance(dep, dict) else type(dep).__name__}")

    raw_meta = dep.get("metadata") or {}
    app_name = raw_meta.get("name")
    if not app_name:
        raise ValueError("Deployment metadata.name is required")
    namespace = raw_meta.get("namespace", "default")

    clean_annotations = {
        k: v
        for k, v in (raw_meta.get("annotations") or {}).items()
        if k not in CONTROLLER_ANNOTATIONS
    }
    clean_meta = {"name": app_name, "namespace": namespace}
    if raw_meta.get("labels"):
        clean_meta["labels"] = raw_meta["labels"]
    if clean_annotations:
        clean_meta["annotations"] = clean_annotations

    spec = dep.get("spec") or {}
    rollout: dict = {
        "apiVersion": "argoproj.io/v1alpha1",
        "kind": "Rollout",
        "metadata": clean_meta,
        "spec": {
            "replicas": spec.get("replicas", 1),
            "selector": spec.get("selector"),
            "template": spec.get("template"),
        },
    }

    if strategy == "canary":
        canary_spec: dict = {
            "stableService": f"{app_name}-stable",
            "canaryService": f"{app_name}-canary",
            "steps": [
                {"setWeight": 5},
                {"pause": {}},
                {"setWeight": 25},
                {"pause": {}},
                {"setWeight": 50},
                {"pause": {}},
            ],
        }
        if traefik_service:
            canary_spec["trafficRouting"] = {
                "traefik": {"weightedTraefikServiceName": traefik_service}
            }
        rollout["spec"]["strategy"] = {"canary": canary_spec}
    elif strategy == "bluegreen":
        rollout["spec"]["strategy"] = {
            "blueGreen": {
                "activeService": f"{app_name}-active",
                "previewService": f"{app_name}-preview",
                "autoPromotionEnabled": False,
            }
        }
    else:
        raise ValueError(f"Unsupported strategy '{strategy}'. Choose 'canary' or 'bluegreen'.")

    if migration_mode == "workload_ref":
        rollout["spec"]["workloadRef"] = {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "name": app_name,
            "scaleDown": scale_down,
        }
        rollout["spec"].pop("template", None)
        rollout["spec"].pop("selector", None)
    elif migration_mode != "direct":
        raise ValueError(f"Unsupported migration_mode '{migration_mode}'. Choose 'direct' or 'workload_ref'.")

    docs = [yaml.dump(rollout, default_flow_style=False, sort_keys=False)]

    if include_services:
        pod_spec = (spec.get("template") or {}).get("spec") or {}
        target_port = extract_container_port(pod_spec)
        selector = (spec.get("selector") or {}).get("matchLabels") or {"app": app_name}
        suffixes = ("stable", "canary") if strategy == "canary" else ("active", "preview")
        for suffix in suffixes:
            svc = {
                "apiVersion": "v1",
                "kind": "Service",
                "metadata": {"name": f"{app_name}-{suffix}", "namespace": namespace},
                "spec": {
                    "selector": selector,
                    "ports": [{"port": service_port, "targetPort": target_port, "protocol": "TCP"}],
                },
            }
            docs.append(yaml.dump(svc, default_flow_style=False, sort_keys=False))

    return "---\n".join(docs)


def main() -> int:
    parser = argparse.ArgumentParser(description="Convert a Kubernetes Deployment YAML to an Argo Rollout YAML.")
    parser.add_argument("--input", "-i", type=str, help="Path to Deployment YAML file (defaults to stdin)")
    parser.add_argument("--strategy", choices=["canary", "bluegreen"], default="canary")
    parser.add_argument("--migration-mode", choices=["direct", "workload_ref"], default="direct")
    parser.add_argument("--scale-down", choices=["never", "onsuccess", "progressively"], default="onsuccess")
    parser.add_argument("--traefik-service", type=str, default=None)
    parser.add_argument("--include-services", action="store_true", help="Also emit stable/canary or active/preview Services")
    parser.add_argument("--service-port", type=int, default=80)
    args = parser.parse_args()

    try:
        raw = Path(args.input).read_text(encoding="utf-8") if args.input else sys.stdin.read()
        doc = yaml.safe_load(raw)
        out = convert_deployment(
            doc,
            strategy=args.strategy,
            migration_mode=args.migration_mode,
            scale_down=args.scale_down,
            traefik_service=args.traefik_service,
            include_services=args.include_services,
            service_port=args.service_port,
        )
        print(out, end="")
        return 0
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
