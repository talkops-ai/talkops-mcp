#!/usr/bin/env python3
"""Render validated Grafana Loki 3.x configuration or Kubernetes LokiStack CRD manifests."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

import yaml


def render_architecture(
    mode: str = "simple-scalable",
    size: str = "1x.small",
    storage: str = "s3",
    retention_days: int = 30,
    namespace: str = "logging",
    name: str = "loki-stack",
    bloom_filters: bool = False,
) -> dict[str, Any]:
    """Generate a validated Loki 3.x config or LokiStack CRD manifest."""
    mode = mode.lower().strip()
    retention_str = f"{int(retention_days) * 24}h"
    enable_blooms = bool(bloom_filters or mode == "microservices")

    if mode == "lokistack":
        manifest_obj = {
            "apiVersion": "loki.grafana.com/v1",
            "kind": "LokiStack",
            "metadata": {
                "name": name,
                "namespace": namespace,
            },
            "spec": {
                "size": size,
                "storage": {
                    "schemas": [
                        {
                            "version": "v13",
                            "effectiveDate": "2024-04-01",
                        }
                    ],
                    "secret": {
                        "name": f"{name}-{storage}-secret",
                        "type": storage,
                    },
                },
                "storageClassName": "gp3",
                "limits": {
                    "global": {
                        "retention": {
                            "days": int(retention_days),
                        }
                    }
                },
                "rules": {
                    "enabled": True,
                    "selector": {
                        "matchLabels": {
                            "loki.grafana.com/rules": "true",
                        }
                    },
                },
            },
        }
        target_components = ["distributor", "ingester", "querier", "query-frontend", "compactor", "ruler", "index-gateway"]
    else:
        replication_factor = 1 if mode == "monolithic" else 3
        zone_aware = mode != "monolithic"
        target_components = (
            ["all"]
            if mode == "monolithic"
            else ["read", "write", "backend"]
            if mode == "simple-scalable"
            else [
                "distributor",
                "ingester",
                "querier",
                "query-frontend",
                "query-scheduler",
                "index-gateway",
                "compactor",
                "ruler",
                *(
                    ["bloom-planner", "bloom-builder", "bloom-gateway"]
                    if enable_blooms
                    else []
                ),
            ]
        )
        ring_cfg: dict[str, Any] = {"kvstore": {"store": "memberlist"}}
        if zone_aware:
            ring_cfg["zone_awareness_enabled"] = True

        ingester_cfg: dict[str, Any] = {
            "chunk_encoding": "snappy",
            "chunk_target_size": 1572864,
            "chunk_idle_period": "30m",
            "max_chunk_age": "2h",
            "wal": {"enabled": True, "dir": "/var/loki/wal"},
        }
        if zone_aware:
            ingester_cfg["lifecycler"] = {
                "ring": {
                    "kvstore": {"store": "memberlist"},
                    "replication_factor": replication_factor,
                    "zone_awareness_enabled": True,
                }
            }

        limits_cfg: dict[str, Any] = {
            "allow_structured_metadata": True,
            "unordered_writes": True,
            "volume_enabled": True,
            "retention_period": retention_str,
            "ingestion_rate_mb": 32,
            "ingestion_burst_size_mb": 64,
            "per_stream_rate_limit": "5MB",
            "per_stream_rate_limit_burst": "15MB",
            "max_global_streams_per_user": 50000,
            "max_line_size_truncate": True,
        }
        if enable_blooms:
            limits_cfg["bloom_gateway_enable_filtering"] = True
            limits_cfg["bloom_creation_enabled"] = True

        manifest_obj = {
            "auth_enabled": True,
            "server": {"http_listen_port": 3100, "grpc_listen_port": 9095},
            "common": {
                "path_prefix": "/var/loki",
                "replication_factor": replication_factor,
                "ring": ring_cfg,
            },
            "schema_config": {
                "configs": [
                    {
                        "from": "2024-04-01",
                        "store": "tsdb",
                        "object_store": storage,
                        "schema": "v13",
                        "index": {"prefix": "loki_index_", "period": "24h"},
                    }
                ]
            },
            "ingester": ingester_cfg,
            "compactor": {
                "working_directory": "/var/loki/compactor",
                "compaction_interval": "10m",
                "retention_enabled": True,
                "retention_delete_delay": "2h",
                "delete_request_store": storage,
            },
            "limits_config": limits_cfg,
        }
        if enable_blooms:
            manifest_obj["bloom_build"] = {
                "enabled": True,
                "builder": {"planner_address": "loki-bloom-planner:9095"},
            }
            manifest_obj["bloom_gateway"] = {
                "enabled": True,
                "client": {"addresses": f"dnssrvnoa+_grpc._tcp.loki-bloom-gateway-headless.{namespace}.svc.cluster.local"},
            }

    rendered_yaml = yaml.safe_dump(manifest_obj, sort_keys=False)
    return {
        "mode": mode,
        "size": size,
        "storage": storage,
        "retention_days": int(retention_days),
        "target_components": target_components,
        "manifest": manifest_obj,
        "yaml": rendered_yaml,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render Loki 3.x config or Kubernetes LokiStack CRD.")
    parser.add_argument(
        "--mode",
        choices=["monolithic", "simple-scalable", "microservices", "lokistack"],
        default="simple-scalable",
        help="Deployment architecture mode",
    )
    parser.add_argument(
        "--size",
        choices=["1x.demo", "1x.extra-small", "1x.small", "1x.medium"],
        default="1x.small",
        help="LokiStack sizing tier",
    )
    parser.add_argument("--storage", choices=["s3", "gcs", "azure"], default="s3", help="Object storage backend")
    parser.add_argument("--retention-days", type=int, default=30, help="Log retention in days")
    parser.add_argument("--namespace", default="logging", help="Kubernetes namespace for LokiStack")
    parser.add_argument("--name", default="loki-stack", help="Resource name for LokiStack")
    parser.add_argument("--bloom-filters", action="store_true", help="Enable Loki 3.x Bloom filters")
    parser.add_argument("--json", action="store_true", help="Emit JSON output")
    args = parser.parse_args(argv)

    result = render_architecture(
        mode=args.mode,
        size=args.size,
        storage=args.storage,
        retention_days=args.retention_days,
        namespace=args.namespace,
        name=args.name,
        bloom_filters=args.bloom_filters,
    )
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(result["yaml"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
