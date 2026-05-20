"""Warehouse spec builder.

Constructs a valid Kargo WarehouseSpec from user-friendly subscription
parameters. Handles the mapping from simplified flat fields to the nested
Kargo API subscription structure.

Supported subscription types:
  - image: Container image repository (Docker, ECR, GHCR, etc.)
  - git: Git repository (GitHub, GitLab, Bitbucket, etc.)
  - chart: Helm chart repository (OCI or HTTP)
"""

from typing import Any, Dict, List, Optional

from kargo_mcp_server.exceptions import KargoValidationError


# ---- Subscription type constants ----

SUBSCRIPTION_TYPES = frozenset({"image", "git", "chart"})

IMAGE_SELECTION_STRATEGIES = frozenset({
    "SemVer", "Lexical", "NewestBuild", "Digest",
})

FREIGHT_CREATION_POLICIES = frozenset({"Automatic", "Manual"})


# ---- Individual subscription builders ----


def _build_image_subscription(sub: Dict[str, Any]) -> Dict[str, Any]:
    """Build an image subscription entry.

    Required fields:
        repo_url: Container image repository URL.

    Optional fields:
        semver_constraint: SemVer constraint string (e.g. "^1.26.0").
        image_selection_strategy: One of SemVer, Lexical, NewestBuild, Digest.
        platform: Target platform (e.g. "linux/amd64").
        allow_tags: Regex pattern for allowed tags.
        ignore_tags: List of regex patterns for tags to ignore.
    """
    repo_url = sub.get("repo_url")
    if not repo_url:
        raise KargoValidationError(
            "Image subscription requires 'repo_url'."
        )

    image: Dict[str, Any] = {"repoURL": repo_url}

    if semver := sub.get("semver_constraint"):
        image["semverConstraint"] = semver

    if strategy := sub.get("image_selection_strategy"):
        if strategy not in IMAGE_SELECTION_STRATEGIES:
            raise KargoValidationError(
                f"Invalid image_selection_strategy '{strategy}'. "
                f"Valid options: {', '.join(sorted(IMAGE_SELECTION_STRATEGIES))}"
            )
        image["imageSelectionStrategy"] = strategy

    if platform := sub.get("platform"):
        image["platform"] = platform

    if allow_tags := sub.get("allow_tags"):
        image["allowTags"] = allow_tags

    if ignore_tags := sub.get("ignore_tags"):
        image["ignoreTags"] = ignore_tags

    return {"image": image}


def _build_git_subscription(sub: Dict[str, Any]) -> Dict[str, Any]:
    """Build a git subscription entry.

    Required fields:
        repo_url: Git repository URL.

    Optional fields:
        branch: Branch to track (default: inferred by Kargo).
        semver_constraint: Tag semver constraint for tag-based tracking.
        include_paths: List of paths to include in change detection.
        exclude_paths: List of paths to exclude from change detection.
    """
    repo_url = sub.get("repo_url")
    if not repo_url:
        raise KargoValidationError(
            "Git subscription requires 'repo_url'."
        )

    git: Dict[str, Any] = {"repoURL": repo_url}

    if branch := sub.get("branch"):
        git["branch"] = branch

    if semver := sub.get("semver_constraint"):
        git["semverConstraint"] = semver

    if include_paths := sub.get("include_paths"):
        git["includePaths"] = include_paths

    if exclude_paths := sub.get("exclude_paths"):
        git["excludePaths"] = exclude_paths

    return {"git": git}


def _build_chart_subscription(sub: Dict[str, Any]) -> Dict[str, Any]:
    """Build a Helm chart subscription entry.

    Required fields:
        repo_url: Chart repository URL (HTTP/S or OCI).

    Optional fields:
        chart_name: Chart name within the repository (required for HTTP repos,
                     not needed for OCI).
        semver_constraint: SemVer constraint string (e.g. "^1.0.0").
    """
    repo_url = sub.get("repo_url")
    if not repo_url:
        raise KargoValidationError(
            "Chart subscription requires 'repo_url'."
        )

    chart: Dict[str, Any] = {"repoURL": repo_url}

    if chart_name := sub.get("chart_name"):
        chart["name"] = chart_name

    if semver := sub.get("semver_constraint"):
        chart["semverConstraint"] = semver

    return {"chart": chart}


# ---- Subscription router ----

_SUBSCRIPTION_BUILDERS = {
    "image": _build_image_subscription,
    "git": _build_git_subscription,
    "chart": _build_chart_subscription,
}


def _build_single_subscription(sub: Dict[str, Any]) -> Dict[str, Any]:
    """Route a subscription dict to the appropriate builder.

    Args:
        sub: Subscription dict with a 'type' key.

    Returns:
        Kargo-format subscription dict.

    Raises:
        KargoValidationError: If type is missing or invalid.
    """
    sub_type = sub.get("type", "").lower()
    if sub_type not in SUBSCRIPTION_TYPES:
        raise KargoValidationError(
            f"Invalid subscription type '{sub_type}'. "
            f"Valid types: {', '.join(sorted(SUBSCRIPTION_TYPES))}"
        )

    builder = _SUBSCRIPTION_BUILDERS[sub_type]
    return builder(sub)


# ---- Public API ----


def build_warehouse_spec(
    subscriptions: List[Dict[str, Any]],
    freight_creation_policy: Optional[str] = None,
    interval: Optional[str] = None,
) -> Dict[str, Any]:
    """Build a complete Kargo WarehouseSpec from user-friendly parameters.

    Converts a list of simplified subscription dicts into a valid Kargo
    WarehouseSpec. Each subscription dict must have a 'type' key (image,
    git, or chart) and a 'repo_url' key, plus type-specific optional fields.

    Args:
        subscriptions: List of subscription dicts, each with:
            - type: "image", "git", or "chart"
            - repo_url: Repository URL (required for all types)
            - Plus type-specific optional fields (see individual builders)
        freight_creation_policy: "Automatic" (default) or "Manual".
        interval: Polling interval, e.g. "5m0s" (default).

    Returns:
        Dict suitable for use as a Kargo Warehouse spec body.

    Raises:
        KargoValidationError: For invalid inputs.

    Example:
        >>> build_warehouse_spec([
        ...     {"type": "image", "repo_url": "ghcr.io/org/app", "semver_constraint": "^1.0.0"},
        ...     {"type": "git", "repo_url": "https://github.com/org/repo.git", "branch": "main"},
        ... ])
        {
            "subscriptions": [
                {"image": {"repoURL": "ghcr.io/org/app", "semverConstraint": "^1.0.0"}},
                {"git": {"repoURL": "https://github.com/org/repo.git", "branch": "main"}},
            ],
            "freightCreationPolicy": "Automatic",
        }
    """
    if not subscriptions:
        raise KargoValidationError(
            "At least one subscription is required. Provide image, git, "
            "or chart subscriptions."
        )

    # Validate freight creation policy
    policy = freight_creation_policy or "Automatic"
    if policy not in FREIGHT_CREATION_POLICIES:
        raise KargoValidationError(
            f"Invalid freight_creation_policy '{policy}'. "
            f"Valid options: {', '.join(sorted(FREIGHT_CREATION_POLICIES))}"
        )

    # Build each subscription
    kargo_subscriptions = [
        _build_single_subscription(sub) for sub in subscriptions
    ]

    spec: Dict[str, Any] = {
        "subscriptions": kargo_subscriptions,
        "freightCreationPolicy": policy,
    }

    if interval:
        spec["interval"] = interval

    return spec
