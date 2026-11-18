"""Warehouse spec builder and validator for Kargo v1.10–v1.12.

Constructs a valid Kargo WarehouseSpec from user-friendly subscription
parameters or passthrough Kargo subscription dicts, and detects deprecated/removed
fields that break discovery in Kargo v1.9–v1.12:
  - image.semverConstraint (removed in v1.9 -> use image.constraint)
  - image.gitRepoURL (removed in v1.7 -> use OCI annotation)
  - allowTags / ignoreTags (break discovery in v1.11+ -> use allowTagsRegexes / ignoreTagsRegexes)
"""

from typing import Any, Dict, List, Optional

from kargo_mcp_server.exceptions import KargoValidationError

SUBSCRIPTION_TYPES = frozenset({"image", "git", "chart"})

IMAGE_SELECTION_STRATEGIES = frozenset({
    "SemVer",
    "Lexical",
    "NewestBuild",
    "Digest",
})

GIT_COMMIT_SELECTION_STRATEGIES = frozenset({
    "NewestFromBranch",
    "SemVer",
    "Lexical",
    "NewestTag",
})

FREIGHT_CREATION_POLICIES = frozenset({"Automatic", "Manual"})


def _normalize_regex_list(val: Any) -> List[str]:
    if isinstance(val, str):
        return [val] if val else []
    if isinstance(val, list):
        return [str(x) for x in val if x]
    return []


def _build_image_subscription(sub: Dict[str, Any]) -> Dict[str, Any]:
    """Build a Kargo v1.12 image subscription entry."""
    repo_url = sub.get("repo_url") or sub.get("repoURL")
    if not repo_url:
        raise KargoValidationError("Image subscription requires 'repo_url'.")

    image: Dict[str, Any] = {"repoURL": repo_url}

    # Kargo v1.9+ uses 'constraint' instead of removed 'semverConstraint'
    constraint = (
        sub.get("constraint")
        or sub.get("semver_constraint")
        or sub.get("semverConstraint")
    )
    if constraint:
        image["constraint"] = constraint

    if strategy := (
        sub.get("image_selection_strategy")
        or sub.get("imageSelectionStrategy")
        or sub.get("selection_strategy")
        or sub.get("selectionStrategy")
    ):
        if strategy not in IMAGE_SELECTION_STRATEGIES:
            raise KargoValidationError(
                f"Invalid image_selection_strategy '{strategy}'. "
                f"Valid options: {', '.join(sorted(IMAGE_SELECTION_STRATEGIES))}"
            )
        image["imageSelectionStrategy"] = strategy

    if platform := sub.get("platform"):
        image["platform"] = platform

    # Kargo v1.11+ requires allowTagsRegexes / ignoreTagsRegexes (allowTags/ignoreTags break discovery)
    allow_regexes = _normalize_regex_list(
        sub.get("allow_tags_regexes")
        or sub.get("allowTagsRegexes")
        or sub.get("allow_tags")
        or sub.get("allowTags")
    )
    if allow_regexes:
        image["allowTagsRegexes"] = allow_regexes

    ignore_regexes = _normalize_regex_list(
        sub.get("ignore_tags_regexes")
        or sub.get("ignoreTagsRegexes")
        or sub.get("ignore_tags")
        or sub.get("ignoreTags")
    )
    if ignore_regexes:
        image["ignoreTagsRegexes"] = ignore_regexes

    if "strict_semvers" in sub or "strictSemvers" in sub:
        image["strictSemvers"] = bool(
            sub.get("strict_semvers", sub.get("strictSemvers"))
        )

    if "cache_by_tag" in sub or "cacheByTag" in sub:
        image["cacheByTag"] = bool(sub.get("cache_by_tag", sub.get("cacheByTag")))

    if discovery_limit := (sub.get("discovery_limit") or sub.get("discoveryLimit")):
        image["discoveryLimit"] = int(discovery_limit)

    if "insecure_skip_tls_verify" in sub or "insecureSkipTLSVerify" in sub:
        image["insecureSkipTLSVerify"] = bool(
            sub.get("insecure_skip_tls_verify", sub.get("insecureSkipTLSVerify"))
        )

    entry: Dict[str, Any] = {"image": image}
    if sub.get("name"):
        entry["name"] = sub["name"]
    return entry


def _build_git_subscription(sub: Dict[str, Any]) -> Dict[str, Any]:
    """Build a Kargo v1.12 git subscription entry."""
    repo_url = sub.get("repo_url") or sub.get("repoURL")
    if not repo_url:
        raise KargoValidationError("Git subscription requires 'repo_url'.")

    git: Dict[str, Any] = {"repoURL": repo_url}

    if branch := sub.get("branch"):
        git["branch"] = branch

    if commit_strategy := (
        sub.get("commit_selection_strategy")
        or sub.get("commitSelectionStrategy")
        or sub.get("selection_strategy")
        or sub.get("selectionStrategy")
    ):
        if commit_strategy not in GIT_COMMIT_SELECTION_STRATEGIES:
            raise KargoValidationError(
                f"Invalid commit_selection_strategy '{commit_strategy}'. "
                f"Valid options: {', '.join(sorted(GIT_COMMIT_SELECTION_STRATEGIES))}"
            )
        git["commitSelectionStrategy"] = commit_strategy

    if semver := (
        sub.get("semver_constraint")
        or sub.get("semverConstraint")
        or sub.get("constraint")
    ):
        git["semverConstraint"] = semver

    allow_regexes = _normalize_regex_list(
        sub.get("allow_tags_regexes")
        or sub.get("allowTagsRegexes")
        or sub.get("allow_tags")
        or sub.get("allowTags")
    )
    if allow_regexes:
        git["allowTagsRegexes"] = allow_regexes

    ignore_regexes = _normalize_regex_list(
        sub.get("ignore_tags_regexes")
        or sub.get("ignoreTagsRegexes")
        or sub.get("ignore_tags")
        or sub.get("ignoreTags")
    )
    if ignore_regexes:
        git["ignoreTagsRegexes"] = ignore_regexes

    if include_paths := (sub.get("include_paths") or sub.get("includePaths")):
        git["includePaths"] = include_paths

    if exclude_paths := (sub.get("exclude_paths") or sub.get("excludePaths")):
        git["excludePaths"] = exclude_paths

    if expr_filter := (sub.get("expression_filter") or sub.get("expressionFilter")):
        git["expressionFilter"] = expr_filter

    if since := sub.get("since"):
        git["since"] = since

    if "blobless" in sub:
        git["blobless"] = bool(sub["blobless"])

    if "strict_semvers" in sub or "strictSemvers" in sub:
        git["strictSemvers"] = bool(sub.get("strict_semvers", sub.get("strictSemvers")))

    if discovery_limit := (sub.get("discovery_limit") or sub.get("discoveryLimit")):
        git["discoveryLimit"] = int(discovery_limit)

    if "insecure_skip_tls_verify" in sub or "insecureSkipTLSVerify" in sub:
        git["insecureSkipTLSVerify"] = bool(
            sub.get("insecure_skip_tls_verify", sub.get("insecureSkipTLSVerify"))
        )

    entry: Dict[str, Any] = {"git": git}
    if sub.get("name"):
        entry["name"] = sub["name"]
    return entry


def _build_chart_subscription(sub: Dict[str, Any]) -> Dict[str, Any]:
    """Build a Kargo v1.12 Helm chart subscription entry."""
    repo_url = sub.get("repo_url") or sub.get("repoURL")
    if not repo_url:
        raise KargoValidationError("Chart subscription requires 'repo_url'.")

    chart: Dict[str, Any] = {"repoURL": repo_url}

    if chart_name := (sub.get("chart_name") or sub.get("chartName")):
        chart["name"] = chart_name

    if semver := (
        sub.get("semver_constraint")
        or sub.get("semverConstraint")
        or sub.get("constraint")
        or sub.get("version")
    ):
        chart["semverConstraint"] = semver

    if discovery_limit := (sub.get("discovery_limit") or sub.get("discoveryLimit")):
        chart["discoveryLimit"] = int(discovery_limit)

    if "insecure_skip_tls_verify" in sub or "insecureSkipTLSVerify" in sub:
        chart["insecureSkipTLSVerify"] = bool(
            sub.get("insecure_skip_tls_verify", sub.get("insecureSkipTLSVerify"))
        )

    entry: Dict[str, Any] = {"chart": chart}
    if sub.get("name") and not chart_name:
        # If 'name' was meant as chart name for HTTP chart repo vs subscription name
        if not repo_url.startswith("oci://"):
            chart["name"] = sub["name"]
        else:
            entry["name"] = sub["name"]
    elif sub.get("subscription_name"):
        entry["name"] = sub["subscription_name"]
    return entry


_SUBSCRIPTION_BUILDERS = {
    "image": _build_image_subscription,
    "git": _build_git_subscription,
    "chart": _build_chart_subscription,
}


def _build_single_subscription(sub: Dict[str, Any]) -> Dict[str, Any]:
    """Route a subscription dict (either flat user-friendly or nested Kargo format) to the builder."""
    if not isinstance(sub, dict):
        raise KargoValidationError("Each subscription must be a dictionary.")

    # Support nested Kargo format e.g. {"image": {"repoURL": ...}} directly (upgrading deprecated keys)
    for k in ("image", "git", "chart"):
        if k in sub and isinstance(sub[k], dict):
            flat = dict(sub[k])
            flat["type"] = k
            if "name" in sub and k != "chart":
                flat["name"] = sub["name"]
            elif "name" in sub and k == "chart":
                flat["subscription_name"] = sub["name"]
            if k == "chart" and "name" in sub[k]:
                flat["chart_name"] = sub[k]["name"]
            return _SUBSCRIPTION_BUILDERS[k](flat)

    sub_type = str(sub.get("type", "")).lower()
    if sub_type not in SUBSCRIPTION_TYPES:
        raise KargoValidationError(
            f"Invalid subscription type '{sub_type}'. "
            f"Valid types: {', '.join(sorted(SUBSCRIPTION_TYPES))}"
        )

    return _SUBSCRIPTION_BUILDERS[sub_type](sub)


def detect_deprecated_warehouse_fields(spec: Dict[str, Any]) -> List[str]:
    """Inspect a raw Warehouse spec for deprecated/removed Kargo v1.7–v1.12 fields."""
    issues: List[str] = []
    if not isinstance(spec, dict):
        return issues
    for idx, sub in enumerate(spec.get("subscriptions") or []):
        if not isinstance(sub, dict):
            continue
        img = sub.get("image")
        if isinstance(img, dict):
            if "semverConstraint" in img:
                issues.append(
                    f"subscriptions[{idx}].image.semverConstraint was removed in Kargo v1.9; use image.constraint instead."
                )
            if "gitRepoURL" in img:
                issues.append(
                    f"subscriptions[{idx}].image.gitRepoURL was removed in Kargo v1.7; use OCI annotation org.opencontainers.image.source."
                )
            if "allowTags" in img:
                issues.append(
                    f"subscriptions[{idx}].image.allowTags breaks discovery in Kargo v1.11+; use image.allowTagsRegexes (list of regexes)."
                )
            if "ignoreTags" in img:
                issues.append(
                    f"subscriptions[{idx}].image.ignoreTags breaks discovery in Kargo v1.11+; use image.ignoreTagsRegexes (list of regexes)."
                )
        git = sub.get("git")
        if isinstance(git, dict):
            if "allowTags" in git:
                issues.append(
                    f"subscriptions[{idx}].git.allowTags breaks discovery in Kargo v1.11+; use git.allowTagsRegexes."
                )
            if "ignoreTags" in git:
                issues.append(
                    f"subscriptions[{idx}].git.ignoreTags breaks discovery in Kargo v1.11+; use git.ignoreTagsRegexes."
                )
    return issues


def build_warehouse_spec(
    subscriptions: List[Dict[str, Any]],
    freight_creation_policy: Optional[str] = None,
    interval: Optional[str] = None,
    freight_creation_criteria: Optional[str] = None,
    shard: Optional[str] = None,
) -> Dict[str, Any]:
    """Build a complete Kargo v1.12 WarehouseSpec from user-friendly parameters."""
    if not subscriptions:
        raise KargoValidationError(
            "At least one subscription is required. Provide image, git, "
            "or chart subscriptions."
        )

    policy = freight_creation_policy or "Automatic"
    if policy not in FREIGHT_CREATION_POLICIES:
        raise KargoValidationError(
            f"Invalid freight_creation_policy '{policy}'. "
            f"Valid options: {', '.join(sorted(FREIGHT_CREATION_POLICIES))}"
        )

    kargo_subscriptions = [_build_single_subscription(sub) for sub in subscriptions]

    spec: Dict[str, Any] = {
        "subscriptions": kargo_subscriptions,
        "freightCreationPolicy": policy,
    }

    if interval:
        spec["interval"] = interval

    if freight_creation_criteria:
        spec["freightCreationCriteria"] = {"expression": freight_creation_criteria}

    if shard:
        spec["shard"] = shard

    return spec
