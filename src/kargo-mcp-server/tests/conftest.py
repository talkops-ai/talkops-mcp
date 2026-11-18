"""Shared pytest fixtures for the Kargo MCP Server v0.2.0 test suite."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from kargo_mcp_server.config import KargoConfig, ServerConfig
from kargo_mcp_server.models import (
    Freight,
    FreightTraceReport,
    Project,
    ProjectConfig,
    ProjectSummary,
    Promotion,
    PromotionSummary,
    PromotionTask,
    Stage,
    StageDiagnosisReport,
    Warehouse,
    WarehouseDiagnosisReport,
    WarehouseSummary,
)
from kargo_mcp_server.server import ServerBootstrap
from kargo_mcp_server.services import KargoService
from kargo_mcp_server.utils import build_stage_dag, stages_to_summaries

SERVER_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def server_root() -> Path:
    """Return the root directory of kargo-mcp-server."""
    return SERVER_ROOT


@pytest.fixture
def fixtures_dir() -> Path:
    """Return the tests/fixtures directory."""
    return Path(__file__).resolve().parent / "fixtures"


def make_sample_project_dict(name: str = "guestbook") -> dict[str, Any]:
    return {
        "apiVersion": "kargo.akuity.io/v1alpha1",
        "kind": "Project",
        "metadata": {"name": name, "creationTimestamp": "2026-01-01T00:00:00Z"},
        "status": {"conditions": [{"type": "Ready", "status": "True"}]},
    }


def make_sample_project(name: str = "guestbook") -> Project:
    return Project.model_validate(make_sample_project_dict(name))


def make_sample_project_config_dict(name: str = "guestbook") -> dict[str, Any]:
    return {
        "apiVersion": "kargo.akuity.io/v1alpha1",
        "kind": "ProjectConfig",
        "metadata": {"name": name, "namespace": name},
        "spec": {
            "promotionPolicies": [
                {"stageSelector": {"name": "dev"}, "autoPromotionEnabled": True}
            ]
        },
        "status": {"conditions": [{"type": "Ready", "status": "True"}]},
    }


def make_sample_project_config(name: str = "guestbook") -> ProjectConfig:
    return ProjectConfig.model_validate(make_sample_project_config_dict(name))


def make_sample_warehouse_dict(
    name: str = "main-warehouse", project: str = "guestbook"
) -> dict[str, Any]:
    return {
        "apiVersion": "kargo.akuity.io/v1alpha1",
        "kind": "Warehouse",
        "metadata": {"name": name, "namespace": project},
        "spec": {
            "interval": "5m0s",
            "subscriptions": [
                {
                    "image": {
                        "repoURL": "ghcr.io/example/guestbook",
                        "imageSelectionStrategy": "SemVer",
                        "constraint": "^1.0.0",
                        "allowTagsRegexes": ["^v?[0-9]+\\.[0-9]+\\.[0-9]+$"],
                    }
                }
            ],
        },
        "status": {
            "conditions": [
                {"type": "Ready", "status": "True"},
                {"type": "Healthy", "status": "True"},
            ],
            "lastFreightID": "freight-120",
            "discoveredArtifacts": {
                "images": [
                    {
                        "repoURL": "ghcr.io/example/guestbook",
                        "references": [{"tag": "1.2.0", "digest": "sha256:abc123"}],
                    }
                ]
            },
        },
    }


def make_sample_warehouse(
    name: str = "main-warehouse", project: str = "guestbook"
) -> Warehouse:
    return Warehouse.model_validate(make_sample_warehouse_dict(name, project))


def make_sample_freight_dict(
    name: str = "freight-120",
    alias: str = "vivid-falcon",
    project: str = "guestbook",
    tag: str = "1.2.0",
) -> dict[str, Any]:
    return {
        "apiVersion": "kargo.akuity.io/v1alpha1",
        "kind": "Freight",
        "metadata": {
            "name": name,
            "namespace": project,
            "creationTimestamp": "2026-01-02T00:00:00Z",
            "labels": {"kargo.akuity.io/alias": alias},
        },
        "alias": alias,
        "origin": {"kind": "Warehouse", "name": "main-warehouse"},
        "images": [
            {
                "repoURL": "ghcr.io/example/guestbook",
                "tag": tag,
                "digest": f"sha256:{name}",
            }
        ],
        "status": {
            "currentlyIn": {"dev": {}},
            "verifiedIn": {"dev": {}},
            "approvedFor": {},
        },
    }


def make_sample_freight(
    name: str = "freight-120",
    alias: str = "vivid-falcon",
    project: str = "guestbook",
    tag: str = "1.2.0",
) -> Freight:
    return Freight.model_validate(make_sample_freight_dict(name, alias, project, tag))


def make_sample_stage_dict(name: str = "dev", project: str = "guestbook") -> dict[str, Any]:
    return {
        "apiVersion": "kargo.akuity.io/v1alpha1",
        "kind": "Stage",
        "metadata": {"name": name, "namespace": project},
        "spec": {
            "requestedFreight": [
                {
                    "origin": {"kind": "Warehouse", "name": "main-warehouse"},
                    "sources": {
                        "direct": name == "dev",
                        "stages": [] if name == "dev" else ["dev"],
                    },
                }
            ],
            "promotionTemplate": {
                "spec": {"steps": [{"task": {"name": "promote-task"}}]}
            },
        },
        "status": {
            "conditions": [
                {"type": "Ready", "status": "True"},
                {"type": "Healthy", "status": "True"},
            ],
            "health": {"status": "Healthy", "issues": []},
            "freightHistory": [
                {
                    "id": "col-120",
                    "items": {
                        "Warehouse/main-warehouse": {
                            "name": "freight-120",
                            "origin": {"kind": "Warehouse", "name": "main-warehouse"},
                        }
                    },
                    "verificationHistory": [
                        {
                            "id": "ver-120",
                            "phase": "Succeeded",
                            "analysisRun": {"name": "dev-verify-120", "namespace": project},
                        }
                    ],
                },
                {
                    "id": "col-110",
                    "items": {
                        "Warehouse/main-warehouse": {
                            "name": "freight-110",
                            "origin": {"kind": "Warehouse", "name": "main-warehouse"},
                        }
                    },
                    "verificationHistory": [
                        {
                            "id": "ver-110",
                            "phase": "Succeeded",
                        }
                    ],
                },
            ],
            "autoPromotionHolds": [],
        },
    }


def make_sample_stage(name: str = "dev", project: str = "guestbook") -> Stage:
    return Stage.model_validate(make_sample_stage_dict(name, project))


def make_sample_promotion_dict(
    name: str = "dev.01j9.freight-120",
    stage: str = "dev",
    freight: str = "freight-120",
    project: str = "guestbook",
    phase: str = "Succeeded",
) -> dict[str, Any]:
    return {
        "apiVersion": "kargo.akuity.io/v1alpha1",
        "kind": "Promotion",
        "metadata": {
            "name": name,
            "namespace": project,
            "creationTimestamp": "2026-01-02T00:05:00Z",
        },
        "spec": {"stage": stage, "freight": freight},
        "status": {
            "phase": phase,
            "message": "Promotion succeeded",
            "stepExecutionMetadata": [
                {"alias": "git-clone", "status": "Succeeded"},
                {"alias": "update-image", "status": "Succeeded"},
                {"alias": "commit", "status": "Succeeded"},
                {"alias": "git-push", "status": "Succeeded"},
                {"alias": "argocd-update", "status": "Succeeded"},
            ],
        },
    }


def make_sample_promotion(
    name: str = "dev.01j9.freight-120",
    stage: str = "dev",
    freight: str = "freight-120",
    project: str = "guestbook",
    phase: str = "Succeeded",
) -> Promotion:
    return Promotion.model_validate(
        make_sample_promotion_dict(name, stage, freight, project, phase)
    )


def make_sample_promotion_task_dict(
    name: str = "promote-task", project: str = "guestbook", cluster_scoped: bool = False
) -> dict[str, Any]:
    return {
        "apiVersion": "kargo.akuity.io/v1alpha1",
        "kind": "ClusterPromotionTask" if cluster_scoped else "PromotionTask",
        "metadata": (
            {"name": name}
            if cluster_scoped
            else {"name": name, "namespace": project}
        ),
        "spec": {
            "vars": [{"name": "gitopsRepo", "value": "https://github.com/example/gitops.git"}],
            "steps": [
                {"uses": "git-clone", "config": {"repoURL": "${{ vars.gitopsRepo }}"}},
                {
                    "uses": "yaml-update",
                    "as": "update-image",
                    "config": {
                        "path": "./out/values.yaml",
                        "updates": [{"key": "image.tag", "value": "1.2.0"}],
                    },
                },
            ],
        },
    }


def make_sample_promotion_task(
    name: str = "promote-task", project: str = "guestbook", cluster_scoped: bool = False
) -> PromotionTask:
    return PromotionTask.model_validate(
        make_sample_promotion_task_dict(name, project, cluster_scoped)
    )


def make_sample_credentials_dict(
    name: str = "github-creds", project: str = "guestbook"
) -> dict[str, Any]:
    return {
        "apiVersion": "v1",
        "kind": "Secret",
        "metadata": {
            "name": name,
            "namespace": project,
            "labels": {"kargo.akuity.io/cred-type": "git"},
        },
        "type": "Opaque",
        "stringData": {
            "repoURL": "https://github.com/example/gitops.git",
            "username": "octocat",
            "password": "***REDACTED***",
        },
    }


@pytest.fixture
def fake_kargo_service() -> MagicMock:
    """Create a mocked KargoService with realistic Kargo v1.12 return values."""
    svc = MagicMock(spec=KargoService)

    project_dict = make_sample_project_dict("guestbook")
    project_obj = make_sample_project("guestbook")
    project_cfg_dict = make_sample_project_config_dict("guestbook")
    project_cfg_obj = make_sample_project_config("guestbook")
    warehouse_dict = make_sample_warehouse_dict("main-warehouse", "guestbook")
    warehouse_obj = make_sample_warehouse("main-warehouse", "guestbook")
    freight_120_dict = make_sample_freight_dict("freight-120", "vivid-falcon", "guestbook", "1.2.0")
    freight_120 = make_sample_freight("freight-120", "vivid-falcon", "guestbook", "1.2.0")
    freight_110 = make_sample_freight("freight-110", "calm-otter", "guestbook", "1.1.0")
    dev_stage_dict = make_sample_stage_dict("dev", "guestbook")
    dev_stage = make_sample_stage("dev", "guestbook")
    prod_stage = make_sample_stage("prod", "guestbook")
    promo_dict = make_sample_promotion_dict()
    promo_obj = make_sample_promotion()
    task_dict = make_sample_promotion_task_dict()
    task_obj = make_sample_promotion_task()
    cluster_task_dict = make_sample_promotion_task_dict("global-task", cluster_scoped=True)
    cred_dict = make_sample_credentials_dict()

    up_map, down_map = build_stage_dag([dev_stage, prod_stage])
    stage_summaries = stages_to_summaries(
        [dev_stage, prod_stage], up_map, down_map, auto_promo_stages={"dev"}
    )

    svc.get_server_capabilities = AsyncMock(
        return_value={
            "server_name": "kargo-mcp-server",
            "server_version": "0.2.0",
            "allow_write": True,
            "toolsets": ["all"],
            "kargo_connected": True,
            "kargo_url": "https://localhost:8443",
            "kargo_version": "v1.12.5",
            "auth_mode": "admin",
            "default_project": "guestbook",
        }
    )
    svc.get_cluster_config = AsyncMock(
        return_value={"apiVersion": "kargo.akuity.io/v1alpha1", "kind": "ClusterConfig"}
    )
    svc.refresh_cluster_config = AsyncMock(return_value=None)
    svc.get_controller_heartbeats = AsyncMock(return_value=[])

    # Projects & ProjectConfig
    svc.list_projects = AsyncMock(
        return_value=[
            ProjectSummary(
                name="guestbook",
                ready=True,
                phase="Ready",
                creation_timestamp="2026-01-01T00:00:00Z",
            )
        ]
    )
    svc.get_project = AsyncMock(return_value=project_dict)
    svc.create_project = AsyncMock(return_value=project_obj)
    svc.delete_project = AsyncMock(return_value={"message": "Deleted"})
    svc.get_project_config = AsyncMock(return_value=project_cfg_dict)
    svc.upsert_project_config = AsyncMock(return_value=project_cfg_obj)
    svc.delete_project_config = AsyncMock(return_value={"message": "Deleted"})
    svc.refresh_project_config = AsyncMock(return_value=None)
    svc.list_project_events = AsyncMock(
        return_value=[
            {
                "type": "Normal",
                "reason": "PromotionSucceeded",
                "message": "Promoted freight-120 to dev",
            }
        ]
    )

    # Warehouses
    svc.list_warehouses = AsyncMock(
        return_value=[
            WarehouseSummary(
                name="main-warehouse",
                namespace="guestbook",
                subscription_types=["image"],
                subscriptions_count=1,
                freight_creation_policy="Automatic",
                interval="5m0s",
                ready=True,
                last_freight_id="freight-120",
            )
        ]
    )
    svc.get_warehouse = AsyncMock(return_value=warehouse_dict)
    svc.upsert_warehouse = AsyncMock(return_value=warehouse_obj)
    svc.delete_warehouse = AsyncMock(return_value={"message": "Deleted"})
    svc.refresh_warehouse = AsyncMock(return_value=None)

    # Freight
    svc.list_freight = AsyncMock(
        return_value=[freight_120.to_summary(), freight_110.to_summary()]
    )
    svc.get_freight = AsyncMock(return_value=freight_120_dict)
    svc.approve_freight = AsyncMock(return_value=freight_120)
    svc.update_freight_alias = AsyncMock(return_value=freight_120_dict)
    svc.delete_freight = AsyncMock(return_value={"message": "Deleted"})
    svc.create_freight = AsyncMock(return_value=freight_120_dict)

    # Stages
    svc.list_stages = AsyncMock(return_value=stage_summaries)
    svc.get_stage = AsyncMock(return_value=dev_stage_dict)
    svc.build_merged_stage_manifest = AsyncMock(
        side_effect=lambda project, stage, spec_updates, merge_existing=True: {
            "apiVersion": "kargo.akuity.io/v1alpha1",
            "kind": "Stage",
            "metadata": {"name": stage, "namespace": project},
            "spec": {
                "requestedFreight": spec_updates.get("requestedFreight")
                or [
                    {
                        "origin": {"kind": "Warehouse", "name": "main-warehouse"},
                        "sources": {"direct": True},
                    }
                ],
                "promotionTemplate": spec_updates.get("promotionTemplate")
                or {"spec": {"steps": [{"task": {"name": "promote-task"}}]}},
                **(
                    {"verification": spec_updates["verification"]}
                    if "verification" in spec_updates
                    else {}
                ),
            },
        }
    )
    svc.upsert_stage = AsyncMock(return_value=dev_stage)
    svc.delete_stage = AsyncMock(return_value={"message": "Deleted"})
    svc.refresh_stage = AsyncMock(return_value=None)
    svc.reverify_stage = AsyncMock(return_value=dev_stage)
    svc.abort_stage_verification = AsyncMock(return_value=dev_stage)

    # Promotions
    svc.list_promotions = AsyncMock(
        return_value=[
            PromotionSummary(
                name="dev.01j9.freight-120",
                stage="dev",
                freight="freight-120",
                phase="Succeeded",
                message="Promotion succeeded",
            )
        ]
    )
    svc.get_promotion = AsyncMock(return_value=promo_dict)
    svc.promote_to_stage = AsyncMock(return_value=promo_obj)
    svc.promote_downstream = AsyncMock(return_value=[promo_obj])
    svc.abort_promotion = AsyncMock(return_value=promo_obj)
    svc.refresh_promotion = AsyncMock(return_value=None)

    # PromotionTasks
    svc.list_promotion_tasks = AsyncMock(return_value=[task_dict])
    svc.get_promotion_task = AsyncMock(return_value=task_dict)
    svc.upsert_promotion_task = AsyncMock(return_value=task_obj)
    svc.delete_promotion_task = AsyncMock(return_value={"message": "Deleted"})
    svc.list_cluster_promotion_tasks = AsyncMock(return_value=[cluster_task_dict])
    svc.get_cluster_promotion_task = AsyncMock(return_value=cluster_task_dict)

    # Verification / AnalysisTemplates / AnalysisRuns
    sample_template = {
        "apiVersion": "argoproj.io/v1alpha1",
        "kind": "AnalysisTemplate",
        "metadata": {"name": "smoke-test", "namespace": "guestbook"},
        "spec": {"metrics": [{"name": "web-check", "provider": {"web": {"url": "http://app/healthz"}}}]},
    }
    sample_run = {
        "apiVersion": "argoproj.io/v1alpha1",
        "kind": "AnalysisRun",
        "metadata": {"name": "dev-verify-120", "namespace": "guestbook"},
        "status": {"phase": "Succeeded", "metricResults": [{"name": "web-check", "phase": "Succeeded"}]},
    }
    svc.list_analysis_templates = AsyncMock(
        return_value={
            "analysis_templates": [sample_template],
            "cluster_analysis_templates": [],
        }
    )
    svc.get_analysis_template = AsyncMock(return_value=sample_template)
    svc.upsert_analysis_template = AsyncMock(return_value=sample_template)
    svc.delete_analysis_template = AsyncMock(return_value={"message": "Deleted"})
    svc.get_analysis_run = AsyncMock(return_value=sample_run)
    svc.get_analysis_run_logs = AsyncMock(return_value="2026-01-02T00:05:10Z smoke-test passed\n")

    # Credentials & ConfigMaps
    svc.list_repo_credentials = AsyncMock(return_value=[cred_dict])
    svc.get_repo_credentials = AsyncMock(return_value=cred_dict)
    svc.list_generic_credentials = AsyncMock(return_value=[])
    svc.list_configmaps = AsyncMock(
        return_value=[
            {
                "apiVersion": "v1",
                "kind": "ConfigMap",
                "metadata": {"name": "env-vars", "namespace": "guestbook"},
                "data": {"LOG_LEVEL": "info"},
            }
        ]
    )
    svc.create_or_update_credentials = AsyncMock(return_value=cred_dict)
    svc.delete_credentials = AsyncMock(return_value={"message": "Deleted"})

    # RBAC
    sample_role = {
        "apiVersion": "rbac.authorization.k8s.io/v1",
        "kind": "Role",
        "metadata": {
            "name": "dev-promoter",
            "namespace": "guestbook",
            "annotations": {"rbac.kargo.akuity.io/claims": '{"groups":["devs"]}'},
        },
        "rules": [
            {
                "apiGroups": ["kargo.akuity.io"],
                "resources": ["stages"],
                "resourceNames": ["dev"],
                "verbs": ["promote"],
            }
        ],
    }
    svc.list_roles = AsyncMock(return_value=[sample_role])
    svc.get_role = AsyncMock(return_value=sample_role)
    svc.create_role = AsyncMock(return_value=sample_role)
    svc.delete_role = AsyncMock(return_value={"message": "Deleted"})
    svc.grant_role = AsyncMock(return_value=sample_role)
    svc.revoke_role = AsyncMock(return_value=sample_role)

    # Topology & N-to-1 Diagnostics
    svc.describe_topology = AsyncMock(
        return_value={
            "stage_count": 2,
            "warehouses": ["main-warehouse"],
            "roots": ["dev"],
            "leaves": ["prod"],
            "warehouse_edges": [{"from_warehouse": "main-warehouse", "to_stage": "dev"}],
            "edges": [{"from": "dev", "to": "prod"}],
            "stages": [{"name": "dev"}, {"name": "prod"}],
        }
    )
    svc.trace_freight = AsyncMock(
        return_value=FreightTraceReport(
            project="guestbook",
            freight_id="freight-120",
            alias="vivid-falcon",
            origin="main-warehouse",
            summary="Freight 'vivid-falcon' is deployed and verified in dev.",
            artifacts=[{"type": "image", "repo_url": "ghcr.io/example/guestbook", "version": "1.2.0"}],
            stages=[
                {
                    "stage": "dev",
                    "currently_in": True,
                    "verified": True,
                    "approved": False,
                    "eligible_for_promotion": True,
                    "blocker_reason": None,
                },
                {
                    "stage": "prod",
                    "currently_in": False,
                    "verified": False,
                    "approved": False,
                    "eligible_for_promotion": True,
                    "blocker_reason": None,
                },
            ],
            blockers=[],
            resource_uri="kargo://projects/guestbook/freight/freight-120",
        )
    )
    svc.diagnose_stage = AsyncMock(
        return_value=StageDiagnosisReport(
            project="guestbook",
            stage="dev",
            phase="Ready",
            health_status="Healthy",
            current_freight="freight-120",
            auto_promotion_enabled=True,
            auto_promotion_holds=[],
            summary="Stage 'dev' is in phase 'Ready' (health='Healthy', codes=['HEALTHY']).",
            diagnosis_codes=["HEALTHY"],
            conditions=[{"type": "Ready", "status": "True"}],
            failed_promotion=None,
            verification={"id": "ver-120", "phase": "Succeeded", "analysis_run": "dev-verify-120"},
            warning_events=[],
            recommendations=[],
        )
    )
    svc.diagnose_warehouse = AsyncMock(
        return_value=WarehouseDiagnosisReport(
            project="guestbook",
            warehouse="main-warehouse",
            ready=True,
            last_freight_id="freight-120",
            summary="Warehouse 'main-warehouse' is healthy.",
            diagnosis_codes=["HEALTHY"],
            subscriptions_count=1,
            discovered_counts={"git": 0, "images": 1, "charts": 0},
            deprecated_fields=[],
            conditions=[{"type": "Ready", "status": "True"}],
            recommendations=[],
        )
    )
    return svc


def make_test_server(
    allow_write: bool = True,
    toolsets: set[str] | list[str] | None = None,
    kargo_service: Any | None = None,
):
    """Build an in-memory FastMCP server instance with injected fake KargoService."""
    cfg = ServerConfig(
        allow_write=allow_write,
        toolsets=list(toolsets) if toolsets is not None else ["all"],
        default_project="guestbook",
        kargo=KargoConfig(base_url="https://localhost:8443"),
    )
    services = (
        {"kargo_service": kargo_service, "config": cfg}
        if kargo_service is not None
        else None
    )
    mcp, _ = ServerBootstrap.build(config=cfg, services=services)
    return mcp
