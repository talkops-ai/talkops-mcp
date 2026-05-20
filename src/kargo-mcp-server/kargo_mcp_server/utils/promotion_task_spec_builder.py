"""PromotionTask spec builder.

Constructs valid Kargo PromotionTaskSpec from user-friendly parameters
or industry-standard presets. Presets encode the most common GitOps
promotion workflows so that users who are not familiar with Kargo can
get started with a single tool call.

Available presets:
  - gitops-image-update: Clone → yaml-update → commit → push → argocd-update
  - gitops-kustomize:    Clone → kustomize-set-image → kustomize-build → commit → push → argocd-update
  - gitops-helm-template: Clone → helm-template → commit → push → argocd-update

For advanced use cases not covered by presets, pass ``custom_steps`` directly.
"""

from typing import Any, Dict, List, Optional

from kargo_mcp_server.exceptions import KargoValidationError


# ---- Preset registry ----

AVAILABLE_PRESETS = frozenset({
    "gitops-image-update",
    "gitops-kustomize",
    "gitops-helm-template",
})


# ---- Step templates ----


def _step_git_clone(repo_url_var: str = "repoURL", branch_var: str = "branch") -> Dict[str, Any]:
    """Generate a git-clone step using expression variables."""
    return {
        "uses": "git-clone",
        "config": {
            "repoURL": f"${{{{ vars.{repo_url_var} }}}}",
            "checkout": [
                {
                    "branch": f"${{{{ vars.{branch_var} }}}}",
                    "path": "./out",
                }
            ],
        },
    }


def _step_yaml_update(
    values_path: str,
    image_key: str,
    image_var: str = "image",
) -> Dict[str, Any]:
    """Generate a yaml-update step for image tag promotion."""
    return {
        "uses": "yaml-update",
        "as": "update-image",
        "config": {
            "path": f"./out/{values_path}",
            "updates": [
                {
                    "key": image_key,
                    "value": f"${{{{ imageFrom( vars.{image_var} ).Tag }}}}",
                }
            ],
        },
    }


def _step_kustomize_set_image(
    kustomization_path: str,
    image_var: str = "image",
) -> Dict[str, Any]:
    """Generate a kustomize-set-image step."""
    return {
        "uses": "kustomize-set-image",
        "as": "update-image",
        "config": {
            "path": f"./out/{kustomization_path}",
            "images": [
                {
                    "image": f"${{{{ vars.{image_var} }}}}",
                    "newTag": f"${{{{ imageFrom( vars.{image_var} ).Tag }}}}",
                }
            ],
        },
    }


def _step_kustomize_build(kustomization_path: str) -> Dict[str, Any]:
    """Generate a kustomize-build step."""
    return {
        "uses": "kustomize-build",
        "as": "render-manifests",
        "config": {
            "path": f"./out/{kustomization_path}",
            "outPath": f"./out/{kustomization_path}",
        },
    }


def _step_helm_template(
    chart_path: str,
    release_name: str = "${{ ctx.stage }}",
) -> Dict[str, Any]:
    """Generate a helm-template step."""
    return {
        "uses": "helm-template",
        "as": "render-chart",
        "config": {
            "path": f"./out/{chart_path}",
            "releaseName": release_name,
            "outPath": f"./out/{chart_path}/rendered",
        },
    }


def _step_git_commit(
    commit_message: Optional[str] = None,
) -> Dict[str, Any]:
    """Generate a git-commit step."""
    message = commit_message or (
        "chore: promote ${{ ctx.stage }} with freight ${{ ctx.freight.alias }}"
    )
    return {
        "uses": "git-commit",
        "as": "commit",
        "config": {
            "path": "./out",
            "message": message,
        },
    }


def _step_git_push() -> Dict[str, Any]:
    """Generate a git-push step."""
    return {
        "uses": "git-push",
        "config": {
            "path": "./out",
        },
    }


def _step_argocd_update(app_name_pattern: Optional[str] = None) -> Dict[str, Any]:
    """Generate an argocd-update step."""
    app_name = app_name_pattern or "${{ ctx.project }}-${{ ctx.stage }}"
    return {
        "uses": "argocd-update",
        "config": {
            "apps": [{"name": app_name}],
        },
    }


# ---- Preset builders ----


def _preset_gitops_image_update(
    *,
    git_repo_url: str,
    image_repo_url: str,
    target_branch: str,
    values_path_pattern: str,
    image_key: str,
    argocd_app_name_pattern: Optional[str],
) -> Dict[str, Any]:
    """Build the gitops-image-update preset.

    Workflow: git-clone → yaml-update → git-commit → git-push → argocd-update

    This is the most common GitOps promotion workflow: update an image tag
    in a values file, commit, push, and sync with ArgoCD.
    """
    steps = [
        _step_git_clone(),
        _step_yaml_update(values_path_pattern, image_key),
        _step_git_commit(),
        _step_git_push(),
        _step_argocd_update(argocd_app_name_pattern),
    ]

    variables = [
        {"name": "repoURL", "value": git_repo_url},
        {"name": "image", "value": image_repo_url},
        {"name": "branch", "value": target_branch},
    ]

    return {"steps": steps, "vars": variables}


def _preset_gitops_kustomize(
    *,
    git_repo_url: str,
    image_repo_url: str,
    target_branch: str,
    kustomization_path_pattern: str,
    argocd_app_name_pattern: Optional[str],
) -> Dict[str, Any]:
    """Build the gitops-kustomize preset.

    Workflow: git-clone → kustomize-set-image → kustomize-build → git-commit → git-push → argocd-update

    Use this when your manifests are rendered via Kustomize overlays.
    """
    steps = [
        _step_git_clone(),
        _step_kustomize_set_image(kustomization_path_pattern),
        _step_kustomize_build(kustomization_path_pattern),
        _step_git_commit(),
        _step_git_push(),
        _step_argocd_update(argocd_app_name_pattern),
    ]

    variables = [
        {"name": "repoURL", "value": git_repo_url},
        {"name": "image", "value": image_repo_url},
        {"name": "branch", "value": target_branch},
    ]

    return {"steps": steps, "vars": variables}


def _preset_gitops_helm_template(
    *,
    git_repo_url: str,
    target_branch: str,
    chart_path_pattern: str,
    argocd_app_name_pattern: Optional[str],
) -> Dict[str, Any]:
    """Build the gitops-helm-template preset.

    Workflow: git-clone → helm-template → git-commit → git-push → argocd-update

    Use this when your manifests are rendered via Helm templates.
    """
    steps = [
        _step_git_clone(),
        _step_helm_template(chart_path_pattern),
        _step_git_commit(),
        _step_git_push(),
        _step_argocd_update(argocd_app_name_pattern),
    ]

    variables = [
        {"name": "repoURL", "value": git_repo_url},
        {"name": "branch", "value": target_branch},
    ]

    return {"steps": steps, "vars": variables}


# ---- Public API ----


def build_promotion_task_spec(
    *,
    preset: Optional[str] = None,
    custom_steps: Optional[List[Dict[str, Any]]] = None,
    git_repo_url: Optional[str] = None,
    image_repo_url: Optional[str] = None,
    target_branch: str = "main",
    values_path_pattern: str = "env/${{ ctx.stage }}/values.yaml",
    image_key: str = "image.tag",
    argocd_app_name_pattern: Optional[str] = None,
    kustomization_path_pattern: Optional[str] = None,
    chart_path_pattern: Optional[str] = None,
    extra_vars: Optional[List[Dict[str, str]]] = None,
) -> Dict[str, Any]:
    """Build a complete Kargo PromotionTaskSpec from presets or custom steps.

    Exactly one of ``preset`` or ``custom_steps`` must be provided.

    Presets automatically generate the appropriate promotion step sequence
    and variable bindings for the most common GitOps workflows:

    - **gitops-image-update**: YAML values update workflow.
      Requires: ``git_repo_url``, ``image_repo_url``.
    - **gitops-kustomize**: Kustomize overlay workflow.
      Requires: ``git_repo_url``, ``image_repo_url``, ``kustomization_path_pattern``.
    - **gitops-helm-template**: Helm chart rendering workflow.
      Requires: ``git_repo_url``, ``chart_path_pattern``.

    Args:
        preset: Name of a built-in preset (mutually exclusive with custom_steps).
        custom_steps: List of raw promotion step dicts for advanced use cases
                      (mutually exclusive with preset).
        git_repo_url: Git repository URL for cloning.
        image_repo_url: Container image repository URL for image tracking.
        target_branch: Git branch to clone and push to (default: "main").
        values_path_pattern: Path to values.yaml relative to repo root, may
                             include Kargo expressions (default: "env/${{ ctx.stage }}/values.yaml").
        image_key: YAML key path for the image tag (default: "image.tag").
        argocd_app_name_pattern: ArgoCD Application name, may include Kargo
                                 expressions (default: "${{ ctx.project }}-${{ ctx.stage }}").
        kustomization_path_pattern: Path to kustomization overlay directory
                                    (required for gitops-kustomize preset).
        chart_path_pattern: Path to Helm chart directory
                            (required for gitops-helm-template preset).
        extra_vars: Additional PromotionTask variables as
                    [{"name": "...", "value": "..."}].

    Returns:
        Dict suitable for use as a Kargo PromotionTask spec body.

    Raises:
        KargoValidationError: For invalid or missing inputs.

    Example:
        >>> build_promotion_task_spec(
        ...     preset="gitops-image-update",
        ...     git_repo_url="https://github.com/org/repo.git",
        ...     image_repo_url="ghcr.io/org/app",
        ...     argocd_app_name_pattern="myapp-${{ ctx.stage }}",
        ... )
    """
    # ---- Mutual exclusivity check ----
    if preset is not None and custom_steps is not None:
        raise KargoValidationError(
            "Cannot specify both 'preset' and 'custom_steps'. "
            "Use 'preset' for standard workflows or 'custom_steps' for "
            "fully custom promotion logic."
        )

    if preset is None and custom_steps is None:
        raise KargoValidationError(
            "Either 'preset' or 'custom_steps' is required for upsert. "
            f"Available presets: {', '.join(sorted(AVAILABLE_PRESETS))}"
        )

    # ---- Custom steps path ----
    if custom_steps is not None:
        if not isinstance(custom_steps, list) or len(custom_steps) == 0:
            raise KargoValidationError(
                "'custom_steps' must be a non-empty list of promotion step dicts."
            )
        spec: Dict[str, Any] = {"steps": custom_steps}
        if extra_vars:
            spec["vars"] = extra_vars
        return spec

    # ---- Preset path ----
    if preset not in AVAILABLE_PRESETS:
        raise KargoValidationError(
            f"Unknown preset '{preset}'. "
            f"Available presets: {', '.join(sorted(AVAILABLE_PRESETS))}"
        )

    if preset == "gitops-image-update":
        if not git_repo_url:
            raise KargoValidationError(
                "Preset 'gitops-image-update' requires 'git_repo_url'."
            )
        if not image_repo_url:
            raise KargoValidationError(
                "Preset 'gitops-image-update' requires 'image_repo_url'."
            )
        spec = _preset_gitops_image_update(
            git_repo_url=git_repo_url,
            image_repo_url=image_repo_url,
            target_branch=target_branch,
            values_path_pattern=values_path_pattern,
            image_key=image_key,
            argocd_app_name_pattern=argocd_app_name_pattern,
        )

    elif preset == "gitops-kustomize":
        if not git_repo_url:
            raise KargoValidationError(
                "Preset 'gitops-kustomize' requires 'git_repo_url'."
            )
        if not image_repo_url:
            raise KargoValidationError(
                "Preset 'gitops-kustomize' requires 'image_repo_url'."
            )
        if not kustomization_path_pattern:
            raise KargoValidationError(
                "Preset 'gitops-kustomize' requires 'kustomization_path_pattern'."
            )
        spec = _preset_gitops_kustomize(
            git_repo_url=git_repo_url,
            image_repo_url=image_repo_url,
            target_branch=target_branch,
            kustomization_path_pattern=kustomization_path_pattern,
            argocd_app_name_pattern=argocd_app_name_pattern,
        )

    elif preset == "gitops-helm-template":
        if not git_repo_url:
            raise KargoValidationError(
                "Preset 'gitops-helm-template' requires 'git_repo_url'."
            )
        if not chart_path_pattern:
            raise KargoValidationError(
                "Preset 'gitops-helm-template' requires 'chart_path_pattern'."
            )
        spec = _preset_gitops_helm_template(
            git_repo_url=git_repo_url,
            target_branch=target_branch,
            chart_path_pattern=chart_path_pattern,
            argocd_app_name_pattern=argocd_app_name_pattern,
        )
    else:
        # Should never reach here due to earlier validation, but be explicit
        raise KargoValidationError(f"Unhandled preset '{preset}'.")

    # Append extra vars if provided
    if extra_vars:
        existing_vars = spec.get("vars", [])
        existing_vars.extend(extra_vars)
        spec["vars"] = existing_vars

    return spec
