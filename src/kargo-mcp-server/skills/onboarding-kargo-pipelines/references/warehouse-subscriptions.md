# Warehouse Subscriptions Reference (Kargo v1.12)

## Table of Contents
1. [Overview](#overview)
2. [Image Subscriptions](#image-subscriptions)
3. [Git Subscriptions](#git-subscriptions)
4. [Helm Chart Subscriptions](#helm-chart-subscriptions)
5. [Freight Creation Criteria & Interval](#freight-creation-criteria--interval)
6. [Removed & Deprecated Fields (v1.7–v1.12)](#removed--deprecated-fields-v17v112)

## Overview

A `Warehouse` (`kargo.akuity.io/v1alpha1`) polls Git repositories, container image registries, and Helm chart repositories to produce immutable `Freight` bundles. Use `kargo_apply_warehouse` to create or update a Warehouse and `kargo://projects/{project}/warehouses/{warehouse}` to inspect its live state.

## Image Subscriptions

```yaml
- image:
    repoURL: ghcr.io/org/guestbook
    imageSelectionStrategy: SemVer   # SemVer | Lexical | NewestBuild | Digest
    constraint: "^1.2.0"             # Replaces deprecated semverConstraint
    allowTagsRegexes:
      - "^v?[0-9]+\\.[0-9]+\\.[0-9]+$"
    ignoreTagsRegexes:
      - ".*-rc\\..*"
      - ".*-alpha.*"
    platform: linux/amd64
    discoveryLimit: 20
    strictSemvers: true
```

### Selection Strategies
- `SemVer`: Selects highest semantic version matching `constraint`. Note: `Masterminds/semver` treats suffixed tags such as `2.2.0-checkout` as SemVer prereleases, which do not match `^2.2.0` unless the constraint includes `-0` (e.g., `^2.2.0-0` / `>=2.2.0-0`) or `imageSelectionStrategy: Lexical` is paired with `allowTagsRegexes`.
- `Lexical`: Sorts tags lexicographically and selects the highest tag.
- `NewestBuild`: Inspects image metadata creation timestamps (requires registry metadata calls).
- `Digest`: Tracks a mutable tag (configured in `constraint`, e.g., `latest` or `main`) by its image digest.

## Git Subscriptions

```yaml
- git:
    repoURL: https://github.com/org/gitops-manifests.git
    commitSelectionStrategy: NewestFromBranch  # NewestFromBranch | SemVer | Lexical | NewestTag
    branch: main
    strictSemvers: true
    allowTagsRegexes:
      - "^v[0-9]+\\.[0-9]+\\.[0-9]+$"
    ignoreTagsRegexes:
      - ".*-dev$"
    includePaths:
      - "apps/guestbook/**"
    excludePaths:
      - "docs/**"
    discoveryLimit: 20
```

## Helm Chart Subscriptions

```yaml
- chart:
    repoURL: oci://ghcr.io/org/charts/guestbook
    semverConstraint: "^2.0.0"   # SemVer constraint for chart versions
    discoveryLimit: 10
```

For classic HTTP/S Helm repositories, specify `name` alongside `repoURL`:
```yaml
- chart:
    repoURL: https://charts.bitnami.com/bitnami
    name: nginx
    semverConstraint: "^18.0.0"
```

## Freight Creation Criteria & Interval

- `interval`: Polling interval such as `"5m0s"` or `"15m0s"`. Trigger immediate discovery anytime with `kargo_refresh(project=..., kind="warehouse", name=..., wait=True)`.
- `freightCreationPolicy`: Defaults to `Automatic`. Set to `Manual` when assembling Freight via `kargo_manage_freight(action="create", ...)`.
- `freightCreationCriteria`: Optional expression gate (`expression: "..."`) controlling when discovered artifacts combine into new Freight. When discovered tags/commits fail the expression, Kargo sets `FreightCreationCriteriaSatisfied: False` and withholds Freight creation until matching artifacts arrive:
  ```yaml
  freightCreationCriteria:
    expression: ${{ imageFrom('ghcr.io/org/app').Tag startsWith '2.2.' && imageFrom('ghcr.io/org/sidecar').Tag != '' }}
  ```

## Removed & Deprecated Fields (v1.7–v1.12)

| Legacy Field | Kargo v1.12 Replacement | Notes |
|--------------|-------------------------|-------|
| `image.semverConstraint` | `image.constraint` | `semverConstraint` was deprecated and replaced by unified `constraint`. |
| `image.allowTags` (string) | `image.allowTagsRegexes` (list of strings) | Scalar regex was removed in Kargo v1.7. |
| `image.ignoreTags` (list) | `image.ignoreTagsRegexes` (list of strings) | Exact tag ignore list replaced by regex list in Kargo v1.7. |
| `git.allowTags` (string) | `git.allowTagsRegexes` (list of strings) | Scalar regex replaced by regex list in Kargo v1.7. |
| `git.ignoreTags` (list) | `git.ignoreTagsRegexes` (list of strings) | Replaced by regex list in Kargo v1.7. |
