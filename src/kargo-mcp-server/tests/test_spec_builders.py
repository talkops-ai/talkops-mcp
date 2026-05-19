"""Tests for warehouse and promotion task spec builders.

Validates that the spec builder utilities correctly translate user-friendly
parameters into valid Kargo CRD spec structures.
"""

import pytest

from kargo_mcp_server.exceptions import KargoValidationError
from kargo_mcp_server.utils.warehouse_spec_builder import build_warehouse_spec
from kargo_mcp_server.utils.promotion_task_spec_builder import (
    build_promotion_task_spec,
    AVAILABLE_PRESETS,
)


# ============================================================
# Warehouse Spec Builder Tests
# ============================================================


class TestBuildWarehouseSpec:
    """Tests for build_warehouse_spec utility."""

    # ---- Happy paths ----

    def test_single_image_subscription(self) -> None:
        """Image subscription with semver constraint."""
        spec = build_warehouse_spec([
            {"type": "image", "repo_url": "ghcr.io/org/app", "semver_constraint": "^1.0.0"},
        ])

        assert len(spec["subscriptions"]) == 1
        img = spec["subscriptions"][0]["image"]
        assert img["repoURL"] == "ghcr.io/org/app"
        assert img["semverConstraint"] == "^1.0.0"
        assert spec["freightCreationPolicy"] == "Automatic"

    def test_single_git_subscription(self) -> None:
        """Git subscription with branch."""
        spec = build_warehouse_spec([
            {"type": "git", "repo_url": "https://github.com/org/repo.git", "branch": "main"},
        ])

        assert len(spec["subscriptions"]) == 1
        git = spec["subscriptions"][0]["git"]
        assert git["repoURL"] == "https://github.com/org/repo.git"
        assert git["branch"] == "main"

    def test_single_chart_subscription(self) -> None:
        """Chart subscription with OCI URL."""
        spec = build_warehouse_spec([
            {"type": "chart", "repo_url": "oci://registry/chart", "semver_constraint": "^2.0.0"},
        ])

        assert len(spec["subscriptions"]) == 1
        chart = spec["subscriptions"][0]["chart"]
        assert chart["repoURL"] == "oci://registry/chart"
        assert chart["semverConstraint"] == "^2.0.0"

    def test_chart_with_name(self) -> None:
        """HTTP chart subscription with explicit chart name."""
        spec = build_warehouse_spec([
            {
                "type": "chart",
                "repo_url": "https://charts.example.com",
                "chart_name": "my-chart",
                "semver_constraint": "^1.0.0",
            },
        ])

        chart = spec["subscriptions"][0]["chart"]
        assert chart["name"] == "my-chart"

    def test_multiple_subscriptions(self) -> None:
        """Multiple mixed subscription types."""
        spec = build_warehouse_spec([
            {"type": "image", "repo_url": "docker.io/nginx", "semver_constraint": "^1.26.0"},
            {"type": "git", "repo_url": "https://github.com/org/config.git", "branch": "main"},
            {"type": "chart", "repo_url": "oci://registry/app-chart"},
        ])

        assert len(spec["subscriptions"]) == 3
        assert "image" in spec["subscriptions"][0]
        assert "git" in spec["subscriptions"][1]
        assert "chart" in spec["subscriptions"][2]

    def test_image_with_all_optional_fields(self) -> None:
        """Image subscription with all optional fields populated."""
        spec = build_warehouse_spec([
            {
                "type": "image",
                "repo_url": "docker.io/library/nginx",
                "semver_constraint": "^1.0.0",
                "image_selection_strategy": "SemVer",
                "platform": "linux/amd64",
                "allow_tags": "^v\\d+",
                "ignore_tags": ["latest", "dev"],
            },
        ])

        img = spec["subscriptions"][0]["image"]
        assert img["imageSelectionStrategy"] == "SemVer"
        assert img["platform"] == "linux/amd64"
        assert img["allowTags"] == "^v\\d+"
        assert img["ignoreTags"] == ["latest", "dev"]

    def test_git_with_path_filters(self) -> None:
        """Git subscription with include/exclude paths."""
        spec = build_warehouse_spec([
            {
                "type": "git",
                "repo_url": "https://github.com/org/repo.git",
                "branch": "main",
                "include_paths": ["manifests/"],
                "exclude_paths": ["docs/"],
            },
        ])

        git = spec["subscriptions"][0]["git"]
        assert git["includePaths"] == ["manifests/"]
        assert git["excludePaths"] == ["docs/"]

    def test_manual_freight_creation_policy(self) -> None:
        """Manual freight creation policy."""
        spec = build_warehouse_spec(
            [{"type": "image", "repo_url": "docker.io/nginx"}],
            freight_creation_policy="Manual",
        )
        assert spec["freightCreationPolicy"] == "Manual"

    def test_custom_interval(self) -> None:
        """Custom polling interval."""
        spec = build_warehouse_spec(
            [{"type": "image", "repo_url": "docker.io/nginx"}],
            interval="2m30s",
        )
        assert spec["interval"] == "2m30s"

    def test_no_interval_omits_key(self) -> None:
        """When no interval is provided, the key should be absent (Kargo defaults to 5m0s)."""
        spec = build_warehouse_spec(
            [{"type": "image", "repo_url": "docker.io/nginx"}],
        )
        assert "interval" not in spec

    # ---- Validation errors ----

    def test_empty_subscriptions_raises(self) -> None:
        """Empty subscription list should fail."""
        with pytest.raises(KargoValidationError, match="At least one subscription"):
            build_warehouse_spec([])

    def test_invalid_type_raises(self) -> None:
        """Invalid subscription type should fail."""
        with pytest.raises(KargoValidationError, match="Invalid subscription type"):
            build_warehouse_spec([{"type": "s3", "repo_url": "s3://bucket"}])

    def test_missing_repo_url_image_raises(self) -> None:
        """Missing repo_url for image subscription."""
        with pytest.raises(KargoValidationError, match="repo_url"):
            build_warehouse_spec([{"type": "image"}])

    def test_missing_repo_url_git_raises(self) -> None:
        """Missing repo_url for git subscription."""
        with pytest.raises(KargoValidationError, match="repo_url"):
            build_warehouse_spec([{"type": "git"}])

    def test_missing_repo_url_chart_raises(self) -> None:
        """Missing repo_url for chart subscription."""
        with pytest.raises(KargoValidationError, match="repo_url"):
            build_warehouse_spec([{"type": "chart"}])

    def test_invalid_image_selection_strategy_raises(self) -> None:
        """Invalid image selection strategy should fail."""
        with pytest.raises(KargoValidationError, match="image_selection_strategy"):
            build_warehouse_spec([
                {"type": "image", "repo_url": "docker.io/nginx", "image_selection_strategy": "Random"},
            ])

    def test_invalid_freight_policy_raises(self) -> None:
        """Invalid freight creation policy should fail."""
        with pytest.raises(KargoValidationError, match="freight_creation_policy"):
            build_warehouse_spec(
                [{"type": "image", "repo_url": "docker.io/nginx"}],
                freight_creation_policy="OnDemand",
            )


# ============================================================
# PromotionTask Spec Builder Tests
# ============================================================


class TestBuildPromotionTaskSpec:
    """Tests for build_promotion_task_spec utility."""

    # ---- Preset: gitops-image-update ----

    def test_gitops_image_update_preset(self) -> None:
        """Verify gitops-image-update generates the correct step sequence."""
        spec = build_promotion_task_spec(
            preset="gitops-image-update",
            git_repo_url="https://github.com/org/repo.git",
            image_repo_url="ghcr.io/org/app",
        )

        assert "steps" in spec
        assert "vars" in spec

        step_uses = [s["uses"] for s in spec["steps"]]
        assert step_uses == [
            "git-clone", "yaml-update", "git-commit", "git-push", "argocd-update"
        ]

        # Verify variables
        var_names = {v["name"] for v in spec["vars"]}
        assert {"repoURL", "image", "branch"} == var_names

        # Verify variable values
        var_map = {v["name"]: v["value"] for v in spec["vars"]}
        assert var_map["repoURL"] == "https://github.com/org/repo.git"
        assert var_map["image"] == "ghcr.io/org/app"
        assert var_map["branch"] == "main"

    def test_gitops_image_update_custom_branch(self) -> None:
        """Custom branch in gitops-image-update."""
        spec = build_promotion_task_spec(
            preset="gitops-image-update",
            git_repo_url="https://github.com/org/repo.git",
            image_repo_url="ghcr.io/org/app",
            target_branch="develop",
        )

        var_map = {v["name"]: v["value"] for v in spec["vars"]}
        assert var_map["branch"] == "develop"

    def test_gitops_image_update_custom_values_path(self) -> None:
        """Custom values path pattern."""
        spec = build_promotion_task_spec(
            preset="gitops-image-update",
            git_repo_url="https://github.com/org/repo.git",
            image_repo_url="ghcr.io/org/app",
            values_path_pattern="deploy/${{ ctx.stage }}/chart/values.yaml",
        )

        yaml_update_step = spec["steps"][1]
        assert "deploy/${{ ctx.stage }}/chart/values.yaml" in yaml_update_step["config"]["path"]

    def test_gitops_image_update_custom_image_key(self) -> None:
        """Custom image key."""
        spec = build_promotion_task_spec(
            preset="gitops-image-update",
            git_repo_url="https://github.com/org/repo.git",
            image_repo_url="ghcr.io/org/app",
            image_key="spec.containers[0].image",
        )

        yaml_update_step = spec["steps"][1]
        assert yaml_update_step["config"]["updates"][0]["key"] == "spec.containers[0].image"

    def test_gitops_image_update_custom_argocd_app(self) -> None:
        """Custom ArgoCD app name pattern."""
        spec = build_promotion_task_spec(
            preset="gitops-image-update",
            git_repo_url="https://github.com/org/repo.git",
            image_repo_url="ghcr.io/org/app",
            argocd_app_name_pattern="myapp-${{ ctx.stage }}",
        )

        argocd_step = spec["steps"][-1]
        assert argocd_step["config"]["apps"][0]["name"] == "myapp-${{ ctx.stage }}"

    # ---- Preset: gitops-kustomize ----

    def test_gitops_kustomize_preset(self) -> None:
        """Verify gitops-kustomize generates the correct step sequence."""
        spec = build_promotion_task_spec(
            preset="gitops-kustomize",
            git_repo_url="https://github.com/org/repo.git",
            image_repo_url="ghcr.io/org/app",
            kustomization_path_pattern="overlays/${{ ctx.stage }}",
        )

        step_uses = [s["uses"] for s in spec["steps"]]
        assert step_uses == [
            "git-clone", "kustomize-set-image", "kustomize-build",
            "git-commit", "git-push", "argocd-update",
        ]

    # ---- Preset: gitops-helm-template ----

    def test_gitops_helm_template_preset(self) -> None:
        """Verify gitops-helm-template generates the correct step sequence."""
        spec = build_promotion_task_spec(
            preset="gitops-helm-template",
            git_repo_url="https://github.com/org/repo.git",
            chart_path_pattern="charts/myapp",
        )

        step_uses = [s["uses"] for s in spec["steps"]]
        assert step_uses == [
            "git-clone", "helm-template", "git-commit", "git-push", "argocd-update",
        ]

        # Should not have image variable
        var_names = {v["name"] for v in spec["vars"]}
        assert "image" not in var_names

    # ---- Custom steps ----

    def test_custom_steps(self) -> None:
        """Custom steps should be passed through as-is."""
        custom = [
            {"uses": "git-clone", "config": {"repoURL": "https://example.com"}},
            {"uses": "yaml-update", "config": {"path": "values.yaml"}},
        ]
        spec = build_promotion_task_spec(custom_steps=custom)

        assert spec["steps"] == custom

    def test_custom_steps_with_extra_vars(self) -> None:
        """Custom steps with extra vars."""
        custom = [{"uses": "git-clone", "config": {"repoURL": "https://example.com"}}]
        extra = [{"name": "myVar", "value": "myValue"}]
        spec = build_promotion_task_spec(custom_steps=custom, extra_vars=extra)

        assert spec["vars"] == extra

    # ---- Extra vars with presets ----

    def test_preset_with_extra_vars(self) -> None:
        """Extra vars should be appended to preset vars."""
        extra = [{"name": "customVar", "value": "customValue"}]
        spec = build_promotion_task_spec(
            preset="gitops-image-update",
            git_repo_url="https://github.com/org/repo.git",
            image_repo_url="ghcr.io/org/app",
            extra_vars=extra,
        )

        var_names = [v["name"] for v in spec["vars"]]
        assert "customVar" in var_names
        assert "repoURL" in var_names  # preset vars still present

    # ---- Validation errors ----

    def test_no_preset_no_custom_steps_raises(self) -> None:
        """Must provide either preset or custom_steps."""
        with pytest.raises(KargoValidationError, match="Either 'preset' or 'custom_steps'"):
            build_promotion_task_spec()

    def test_both_preset_and_custom_steps_raises(self) -> None:
        """Cannot provide both preset and custom_steps."""
        with pytest.raises(KargoValidationError, match="Cannot specify both"):
            build_promotion_task_spec(
                preset="gitops-image-update",
                custom_steps=[{"uses": "git-clone"}],
            )

    def test_invalid_preset_raises(self) -> None:
        """Unknown preset name should fail."""
        with pytest.raises(KargoValidationError, match="Unknown preset"):
            build_promotion_task_spec(preset="not-a-real-preset")

    def test_empty_custom_steps_raises(self) -> None:
        """Empty custom_steps list should fail."""
        with pytest.raises(KargoValidationError, match="non-empty list"):
            build_promotion_task_spec(custom_steps=[])

    def test_gitops_image_update_missing_git_url_raises(self) -> None:
        """gitops-image-update without git_repo_url should fail."""
        with pytest.raises(KargoValidationError, match="git_repo_url"):
            build_promotion_task_spec(
                preset="gitops-image-update",
                image_repo_url="ghcr.io/org/app",
            )

    def test_gitops_image_update_missing_image_url_raises(self) -> None:
        """gitops-image-update without image_repo_url should fail."""
        with pytest.raises(KargoValidationError, match="image_repo_url"):
            build_promotion_task_spec(
                preset="gitops-image-update",
                git_repo_url="https://github.com/org/repo.git",
            )

    def test_gitops_kustomize_missing_kustomization_path_raises(self) -> None:
        """gitops-kustomize without kustomization_path_pattern should fail."""
        with pytest.raises(KargoValidationError, match="kustomization_path_pattern"):
            build_promotion_task_spec(
                preset="gitops-kustomize",
                git_repo_url="https://github.com/org/repo.git",
                image_repo_url="ghcr.io/org/app",
            )

    def test_gitops_helm_template_missing_chart_path_raises(self) -> None:
        """gitops-helm-template without chart_path_pattern should fail."""
        with pytest.raises(KargoValidationError, match="chart_path_pattern"):
            build_promotion_task_spec(
                preset="gitops-helm-template",
                git_repo_url="https://github.com/org/repo.git",
            )

    # ---- Structural integrity ----

    def test_all_presets_have_git_clone_first(self) -> None:
        """Every preset should start with a git-clone step."""
        configs = {
            "gitops-image-update": {
                "git_repo_url": "https://example.com",
                "image_repo_url": "ghcr.io/org/app",
            },
            "gitops-kustomize": {
                "git_repo_url": "https://example.com",
                "image_repo_url": "ghcr.io/org/app",
                "kustomization_path_pattern": "overlays/dev",
            },
            "gitops-helm-template": {
                "git_repo_url": "https://example.com",
                "chart_path_pattern": "charts/app",
            },
        }
        for preset_name, kwargs in configs.items():
            spec = build_promotion_task_spec(preset=preset_name, **kwargs)
            assert spec["steps"][0]["uses"] == "git-clone", (
                f"Preset {preset_name} should start with git-clone"
            )

    def test_all_presets_end_with_argocd_update(self) -> None:
        """Every preset should end with an argocd-update step."""
        configs = {
            "gitops-image-update": {
                "git_repo_url": "https://example.com",
                "image_repo_url": "ghcr.io/org/app",
            },
            "gitops-kustomize": {
                "git_repo_url": "https://example.com",
                "image_repo_url": "ghcr.io/org/app",
                "kustomization_path_pattern": "overlays/dev",
            },
            "gitops-helm-template": {
                "git_repo_url": "https://example.com",
                "chart_path_pattern": "charts/app",
            },
        }
        for preset_name, kwargs in configs.items():
            spec = build_promotion_task_spec(preset=preset_name, **kwargs)
            assert spec["steps"][-1]["uses"] == "argocd-update", (
                f"Preset {preset_name} should end with argocd-update"
            )

    def test_available_presets_constant(self) -> None:
        """Verify AVAILABLE_PRESETS contains expected presets."""
        assert AVAILABLE_PRESETS == {
            "gitops-image-update",
            "gitops-kustomize",
            "gitops-helm-template",
        }
