"""Unit tests for KargoService N-to-1 diagnostics and freight tracing."""

from __future__ import annotations

from unittest.mock import AsyncMock

import httpx
import pytest
import respx

from kargo_mcp_server.config import KargoConfig, ServerConfig
from kargo_mcp_server.services import KargoService
from tests.conftest import (
    make_sample_project_config_dict,
    make_sample_stage_dict,
)


def _make_service() -> KargoService:
    return KargoService(
        ServerConfig(
            default_project="guestbook",
            kargo=KargoConfig(
                base_url="https://kargo.test:8443",
                admin_password="test-password",
            ),
        )
    )


@pytest.mark.asyncio
async def test_diagnose_stage_classifies_argocd_and_verification_failures() -> None:
    svc = _make_service()
    stage_dict = make_sample_stage_dict("dev", "guestbook")
    stage_dict["status"]["lastPromotion"] = {"name": "dev.01j9.fail"}
    failed_promo_dict = {
        "apiVersion": "kargo.akuity.io/v1alpha1",
        "kind": "Promotion",
        "metadata": {"name": "dev.01j9.fail", "namespace": "guestbook"},
        "spec": {"stage": "dev", "freight": "freight-120"},
        "status": {
            "phase": "Errored",
            "message": "step argocd-update failed: Application not authorized for stage",
            "stepExecutionMetadata": [
                {
                    "alias": "argocd-update",
                    "status": "Errored",
                    "message": "Application not authorized for stage guestbook:dev",
                }
            ],
        },
    }
    svc.get_stage = AsyncMock(return_value=stage_dict)
    svc.get_promotion = AsyncMock(return_value=failed_promo_dict)
    svc.get_project_config = AsyncMock(return_value=make_sample_project_config_dict("guestbook"))
    svc.list_project_events = AsyncMock(return_value=[])

    report = await svc.diagnose_stage("guestbook", "dev")
    assert "PROMOTION_STEP_FAILED" in report.diagnosis_codes
    assert "ARGOCD_SYNC_OR_AUTH_FAILED" in report.diagnosis_codes
    assert report.failed_promotion is not None


@pytest.mark.asyncio
async def test_diagnose_stage_detects_verification_failed_and_auto_promotion_holds() -> None:
    svc = _make_service()
    stage_dict = {
        "apiVersion": "kargo.akuity.io/v1alpha1",
        "kind": "Stage",
        "metadata": {"name": "dev", "namespace": "guestbook"},
        "spec": {"requestedFreight": []},
        "status": {
            "health": {"status": "Healthy"},
            "autoPromotionHolds": [{"origin": "main-warehouse"}],
            "freightHistory": [
                {
                    "id": "col-1",
                    "items": {"Warehouse/main-warehouse": {"name": "freight-110"}},
                    "verificationHistory": [
                        {"id": "v1", "phase": "Failed", "message": "HTTP 500 error rate > 5%"}
                    ],
                }
            ],
        },
    }
    svc.get_stage = AsyncMock(return_value=stage_dict)
    svc.get_project_config = AsyncMock(return_value={})
    svc.list_project_events = AsyncMock(return_value=[])

    report = await svc.diagnose_stage("guestbook", "dev")
    assert "VERIFICATION_FAILED" in report.diagnosis_codes
    assert "AUTO_PROMOTION_ON_HOLD" in report.diagnosis_codes
    assert len(report.auto_promotion_holds) == 1


@pytest.mark.asyncio
async def test_diagnose_stage_normalizes_v112_map_auto_promotion_holds() -> None:
    svc = _make_service()
    stage_dict = {
        "apiVersion": "kargo.akuity.io/v1alpha1",
        "kind": "Stage",
        "metadata": {"name": "staging-hold", "namespace": "otel-demo"},
        "spec": {"requestedFreight": []},
        "status": {
            "health": {"status": "Healthy"},
            "autoPromotionHolds": {
                "Warehouse/hold-wh": {
                    "actor": "admin",
                    "createdAt": "2026-11-15T17:37:08Z",
                    "freightName": "3e90956d73f53b505aa1570298b142b5be87c9e2",
                    "origin": {"kind": "Warehouse", "name": "hold-wh"},
                    "promotionName": "staging-hold.01m7g4hhqfkkpdr8e6e12rmskx.3e90956",
                }
            },
            "effectiveAutoPromotionHolds": {
                "Warehouse/hold-wh": {
                    "actor": "admin",
                    "createdAt": "2026-11-15T17:37:08Z",
                    "freightName": "3e90956d73f53b505aa1570298b142b5be87c9e2",
                    "origin": {"kind": "Warehouse", "name": "hold-wh"},
                    "promotionName": "staging-hold.01m7g4hhqfkkpdr8e6e12rmskx.3e90956",
                }
            },
            "freightHistory": [
                {
                    "id": "col-1",
                    "items": {"Warehouse/hold-wh": {"name": "3e90956d73f53b505aa1570298b142b5be87c9e2"}},
                }
            ],
        },
    }
    svc.get_stage = AsyncMock(return_value=stage_dict)
    svc.get_project_config = AsyncMock(return_value={})
    svc.list_project_events = AsyncMock(return_value=[])

    report = await svc.diagnose_stage("otel-demo", "staging-hold")
    assert "AUTO_PROMOTION_ON_HOLD" in report.diagnosis_codes
    assert len(report.auto_promotion_holds) == 1
    assert report.auto_promotion_holds[0]["originName"] == "hold-wh"
    assert any("origin_warehouse='hold-wh'" in rec for rec in report.recommendations)


@pytest.mark.asyncio
async def test_diagnose_warehouse_detects_deprecated_fields() -> None:
    svc = _make_service()
    wh_dict = {
        "apiVersion": "kargo.akuity.io/v1alpha1",
        "kind": "Warehouse",
        "metadata": {"name": "legacy-wh", "namespace": "guestbook"},
        "spec": {
            "subscriptions": [
                {
                    "image": {
                        "repoURL": "ghcr.io/example/app",
                        "semverConstraint": "^1.0.0",
                    }
                }
            ]
        },
        "status": {
            "conditions": [{"type": "Ready", "status": "True"}],
            "lastFreightID": "freight-120",
            "discoveredArtifacts": {
                "images": [{"repoURL": "ghcr.io/example/app", "references": [{"tag": "1.0.0"}]}]
            },
        },
    }
    svc.get_warehouse = AsyncMock(return_value=wh_dict)

    report = await svc.diagnose_warehouse("guestbook", "legacy-wh")
    assert "DEPRECATED_SUBSCRIPTION_FIELDS" in report.diagnosis_codes
    assert len(report.deprecated_fields) == 1


@pytest.mark.asyncio
@respx.mock
async def test_trace_freight_identifies_upstream_verification_blocker() -> None:
    respx.post("https://kargo.test:8443/v1beta1/login").mock(
        return_value=httpx.Response(200, json={"idToken": "test-jwt"})
    )
    respx.get("https://kargo.test:8443/v1beta1/projects/guestbook/freight/bold-tiger").mock(
        return_value=httpx.Response(
            200,
            json={
                "apiVersion": "kargo.akuity.io/v1alpha1",
                "kind": "Freight",
                "metadata": {"name": "freight-200", "namespace": "guestbook"},
                "alias": "bold-tiger",
                "origin": {"kind": "Warehouse", "name": "main-warehouse"},
                "status": {
                    "currentlyIn": {"dev": {}},
                    "verifiedIn": {},
                    "approvedFor": {},
                },
            },
        )
    )
    respx.get("https://kargo.test:8443/v1beta1/projects/guestbook/stages").mock(
        return_value=httpx.Response(
            200,
            json={
                "items": [
                    make_sample_stage_dict("dev", "guestbook"),
                    make_sample_stage_dict("prod", "guestbook"),
                ]
            },
        )
    )

    svc = _make_service()
    trace = await svc.trace_freight("guestbook", "bold-tiger")
    assert trace.freight_id == "freight-200"
    prod_entry = next(s for s in trace.stages if s["stage"] == "prod")
    assert prod_entry["eligible_for_promotion"] is False
    assert "requires upstream verification" in (prod_entry["blocker_reason"] or "")
