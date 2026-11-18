"""Unit tests for Kargo v1.12 CRD models, Warehouse subscription builder, and DAG/step validators."""

from __future__ import annotations

import pytest

from kargo_mcp_server.utils import (
    build_warehouse_spec,
    detect_deprecated_warehouse_fields,
    validate_no_dag_cycles,
    validate_promotion_steps,
)
from tests.conftest import make_sample_freight, make_sample_promotion, make_sample_stage


def test_freight_v112_helpers_extract_alias_and_stage_maps() -> None:
    freight = make_sample_freight("freight-120", "vivid-falcon", "guestbook", "1.2.0")
    assert freight.get_alias() == "vivid-falcon"
    summary = freight.to_summary()
    assert summary.currently_in == ["dev"]
    assert summary.verified_in == ["dev"]
    assert summary.approved_for == []


def test_stage_v112_freight_history_and_rollback_candidate() -> None:
    stage = make_sample_stage("dev", "guestbook")
    assert stage.get_current_freight_id() == "freight-120"
    assert stage.get_previous_verified_freight_id() == "freight-110"
    assert stage.get_health_status() == "Healthy"


def test_promotion_v112_phase_and_step_metadata() -> None:
    promo = make_sample_promotion(phase="Succeeded")
    assert promo.get_phase() == "Succeeded"
    assert promo.spec.stage == "dev"
    assert promo.spec.freight == "freight-120"
    assert promo.status is not None
    assert len(promo.status.step_execution_metadata) == 5


def test_warehouse_builder_emits_v112_constraint_and_regex_lists() -> None:
    """Regression test for B4: emit constraint and allowTagsRegexes/ignoreTagsRegexes."""
    spec = build_warehouse_spec(
        subscriptions=[
            {
                "image": {
                    "repoURL": "ghcr.io/org/app",
                    "semverConstraint": "^1.0.0",
                    "allowTags": "^v1\\..*",
                    "ignoreTags": ["v1.0.0-alpha"],
                }
            }
        ],
        interval="5m0s",
    )
    img = spec["subscriptions"][0]["image"]
    assert img["constraint"] == "^1.0.0"
    assert "semverConstraint" not in img
    assert img["allowTagsRegexes"] == ["^v1\\..*"]
    assert "allowTags" not in img
    assert img["ignoreTagsRegexes"] == ["v1.0.0-alpha"]
    assert "ignoreTags" not in img


def test_detect_deprecated_warehouse_fields() -> None:
    raw_spec = {
        "subscriptions": [
            {
                "image": {
                    "repoURL": "ghcr.io/org/app",
                    "semverConstraint": "^1.0.0",
                    "allowTags": "^v1\\..*",
                }
            }
        ]
    }
    issues = detect_deprecated_warehouse_fields(raw_spec)
    assert len(issues) == 2
    assert any("semverConstraint" in i for i in issues)
    assert any("allowTags" in i for i in issues)


def test_validate_promotion_steps_rejects_removed_steps_and_fields() -> None:
    """Regression test for B5: reject helm-update-image, fromOrigin, and git-commit.author."""
    errs1, _ = validate_promotion_steps([{"uses": "helm-update-image"}])
    assert any("helm-update-image" in e for e in errs1)

    errs2, _ = validate_promotion_steps(
        [{"uses": "yaml-update", "config": {"fromOrigin": {"name": "wh"}}}]
    )
    assert any("fromOrigin" in e for e in errs2)

    errs3, _ = validate_promotion_steps(
        [{"uses": "git-commit", "config": {"path": "./out", "author": {"name": "Bot"}}}]
    )
    assert any("author" in e for e in errs3)

    errs4, _ = validate_promotion_steps(
        [{"uses": "git-push", "config": {"path": "./out", "maxRetries": 5}}]
    )
    assert any("maxAttempts" in e for e in errs4)

    errs5, _ = validate_promotion_steps(
        [{"uses": "git-open-pr", "config": {"repoURL": "https://example.com/a.git", "createTargetBranch": True}}]
    )
    assert any("createTargetBranch" in e for e in errs5)

    errs6, _ = validate_promotion_steps([{"uses": "helm-chart-update"}])
    assert any("helm-update-chart" in e for e in errs6)

    # Valid v1.12 step passes with zero errors
    errs_ok, warns_ok = validate_promotion_steps(
        [
            {
                "uses": "yaml-update",
                "as": "update-image",
                "config": {
                    "path": "./out/values.yaml",
                    "updates": [{"key": "image.tag", "value": "1.0"}],
                },
            }
        ]
    )
    assert errs_ok == []
    assert warns_ok == []


def test_validate_no_dag_cycles_detects_direct_and_indirect_cycles() -> None:
    """Regression test for B7: prevent Stage DAG cycles."""
    dev_stage = make_sample_stage("dev", "guestbook")
    prod_stage = make_sample_stage("prod", "guestbook")
    existing_stages = [dev_stage, prod_stage]

    # Valid update: qa depends on dev
    validate_no_dag_cycles(
        existing_stages,
        "qa",
        {
            "requestedFreight": [
                {
                    "origin": {"kind": "Warehouse", "name": "main-warehouse"},
                    "sources": {"direct": False, "stages": ["dev"]},
                }
            ]
        },
    )

    # Self-dependency
    with pytest.raises(ValueError, match="cannot list itself"):
        validate_no_dag_cycles(
            existing_stages,
            "dev",
            {
                "requestedFreight": [
                    {
                        "origin": {"kind": "Warehouse", "name": "main-warehouse"},
                        "sources": {"direct": False, "stages": ["dev"]},
                    }
                ]
            },
        )

    # Indirect cycle: dev -> prod -> dev
    with pytest.raises(ValueError, match="cycle"):
        validate_no_dag_cycles(
            existing_stages,
            "dev",
            {
                "requestedFreight": [
                    {
                        "origin": {"kind": "Warehouse", "name": "main-warehouse"},
                        "sources": {"direct": False, "stages": ["prod"]},
                    }
                ]
            },
        )
