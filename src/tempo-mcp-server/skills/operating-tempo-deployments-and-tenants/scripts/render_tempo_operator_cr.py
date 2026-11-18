#!/usr/bin/env python3
"""Offline CLI script to render TempoStack or TempoMonolithic (tempo.grafana.com/v1alpha1) manifests."""

import argparse
import sys
from typing import Any, Dict
import yaml

PROFILES: Dict[str, Dict[str, Any]] = {
    "dev": {
        "kind": "TempoMonolithic",
        "cpu": "1000m",
        "memory": "2Gi",
        "storage_size": "10Gi",
        "retention": "72h",
    },
    "small-prod": {
        "kind": "TempoStack",
        "cpu": "6000m",
        "memory": "12Gi",
        "storage_size": "50Gi",
        "replication_factor": 2,
        "retention": "336h",
        "replicas": {"distributor": 2, "ingester": 3, "querier": 2, "queryFrontend": 2, "compactor": 1},
    },
    "large-prod": {
        "kind": "TempoStack",
        "cpu": "24000m",
        "memory": "48Gi",
        "storage_size": "200Gi",
        "replication_factor": 3,
        "retention": "720h",
        "replicas": {"distributor": 4, "ingester": 6, "querier": 4, "queryFrontend": 3, "compactor": 2},
    },
}


def render_cr(
    profile: str,
    name: str,
    namespace: str,
    storage_secret: str,
    storage_type: str,
) -> Dict[str, Any]:
    spec_profile = PROFILES[profile]
    kind = spec_profile["kind"]
    if kind == "TempoMonolithic":
        traces_storage: Dict[str, Any] = {
            "backend": storage_type,
            "size": spec_profile["storage_size"],
        }
        if storage_type in ("s3", "gcs", "azure"):
            traces_storage[storage_type] = {"secret": storage_secret}
        return {
            "apiVersion": "tempo.grafana.com/v1alpha1",
            "kind": "TempoMonolithic",
            "metadata": {"name": name, "namespace": namespace},
            "spec": {
                "resources": {
                    "limits": {
                        "cpu": spec_profile["cpu"],
                        "memory": spec_profile["memory"],
                    }
                },
                "storage": {
                    "traces": traces_storage,
                },
                "extraConfig": {
                    "tempo": {
                        "compactor": {
                            "compaction": {
                                "block_retention": spec_profile["retention"],
                            }
                        }
                    }
                },
            },
        }

    replicas = spec_profile["replicas"]
    return {
        "apiVersion": "tempo.grafana.com/v1alpha1",
        "kind": "TempoStack",
        "metadata": {"name": name, "namespace": namespace},
        "spec": {
            "storage": {"secret": {"name": storage_secret, "type": storage_type}},
            "storageSize": spec_profile["storage_size"],
            "replicationFactor": spec_profile["replication_factor"],
            "retention": {"global": {"traces": spec_profile["retention"]}},
            "resources": {
                "total": {
                    "limits": {
                        "cpu": spec_profile["cpu"],
                        "memory": spec_profile["memory"],
                    }
                }
            },
            "template": {
                comp: {"replicas": count} for comp, count in replicas.items()
            },
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Render a TempoStack or TempoMonolithic v1alpha1 YAML manifest."
    )
    parser.add_argument(
        "--profile",
        choices=sorted(PROFILES.keys()),
        default="small-prod",
        help="Sizing profile (dev, small-prod, large-prod).",
    )
    parser.add_argument("--name", default="tempo-prod", help="CR metadata.name.")
    parser.add_argument("--namespace", default="observability", help="CR metadata.namespace.")
    parser.add_argument(
        "--storage-secret",
        default="tempo-s3-credentials",
        help="Kubernetes Secret name for object storage.",
    )
    parser.add_argument(
        "--storage-type",
        default="s3",
        choices=["s3", "gcs", "azure", "pv"],
        help="Storage backend type (s3, gcs, azure, or pv for dev TempoMonolithic).",
    )
    parser.add_argument(
        "--retention",
        default=None,
        help="Optional trace retention override (e.g. '72h', '336h', '720h').",
    )
    args = parser.parse_args()
    manifest = render_cr(
        args.profile,
        args.name,
        args.namespace,
        args.storage_secret,
        args.storage_type,
    )
    if args.retention:
        if manifest["kind"] == "TempoStack":
            manifest["spec"]["retention"] = {"global": {"traces": args.retention}}
        else:
            manifest["spec"]["extraConfig"]["tempo"]["compactor"]["compaction"]["block_retention"] = args.retention
    print(yaml.safe_dump(manifest, sort_keys=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
