# Kargo v1.12 Promotion Steps & Expression Catalog

## Table of Contents
1. [Overview](#overview)
2. [Expression Language Functions](#expression-language-functions)
3. [Git Operations](#git-operations)
4. [Container Image, Kustomize & Helm Steps](#container-image-kustomize--helm-steps)
5. [YAML, JSON, TOML & File Manipulation Steps](#yaml-json-toml--file-manipulation-steps)
6. [Argo CD & HTTP Integration Steps](#argo-cd--http-integration-steps)
7. [Removed Steps & Breaking Config Changes](#removed-steps--breaking-config-changes)

## Overview

In Kargo v1.7+, stages execute declarative promotion steps defined inline in `Stage.spec.promotionTemplate.spec.steps` or referenced from reusable `PromotionTask` (`kargo://projects/{project}/promotion-tasks/{task}`) and `ClusterPromotionTask` (`kargo://cluster-promotion-tasks/{task}`) resources via `kargo_apply_promotion_task` and `kargo_apply_stage`.

## Expression Language Functions

Expressions are wrapped in `${{ ... }}` and evaluated via `expr-lang`:

- `imageFrom(repoURL)` or `imageFrom(repoURL, warehouse("name"))`: Returns `{repoURL, tag, digest, annotations}` from the promoted Freight.
- `commitFrom(repoURL)` or `commitFrom(repoURL, warehouse("name"))`: Returns `{repoURL, id, branch, tag, message, author}` from the promoted Freight.
- `chartFrom(repoURL, chartName)` or `chartFrom(ociRepoURL)`: Returns `{repoURL, name, version}` from the promoted Freight.
- `warehouse(name)`: Constructs a FreightOrigin selector for disambiguating multi-warehouse stages.
- `outputs.<stepAlias>.<field>`: Accesses outputs from earlier promotion steps (e.g., `${{ outputs.commit.commit }}` or `${{ outputs['open-pr'].pr.url }}`).
- `vars.<name>`: Reads step or stage variables.
- `ctx.project`, `ctx.stage`, `ctx.promotion`, `ctx.freight.name`, `ctx.freight.alias`, `ctx.targetBranch`: Built-in execution context metadata.
- `secret(name)` and `configMap(name)`: Reads project/shared `Secret` or `ConfigMap` data during step execution.
- `quote(val)`: Safely quotes scalar values (such as numeric tags) for YAML updates.

## Git Operations

| Step (`uses`) | Purpose | Key `config` Fields |
|---------------|---------|---------------------|
| `git-clone` | Clone remote Git repository into workspace | `repoURL`, `checkout` (`branch`, `commit`, `tag`, `create`, `path`), `author`, `filter`, `sparse` |
| `git-commit` | Commit workspace changes to checked-out branch | `path`, `message` (note: `author` moved to `git-clone` in v1.8+) |
| `git-push` | Push commits or generated tags to remote | `path`, `targetBranch`, `generateTargetBranch`, `createTargetBranch`, `tag`, `force`, `maxAttempts` |
| `git-open-pr` | Open pull request on GitHub, GitLab, Gitea, Bitbucket, Azure DevOps | `repoURL`, `provider`, `sourceBranch`, `targetBranch`, `title`, `description`, `labels` |
| `git-wait-for-pr` | Wait until PR is merged (and optionally closed) | `repoURL`, `provider`, `prNumber` (`${{ outputs['open-pr'].pr.id }}`), `timeout` |
| `git-merge-pr` | Merge an open pull request (v1.11+) | `repoURL`, `provider`, `prNumber`, `mergeMethod` |
| `git-clear` | Remove all non-`.git` files from working directory | `path` |
| `git-Worktree` / `git-branch-delete` | Manage temporary branches | `path`, `branch` |

## Container Image, Kustomize & Helm Steps

| Step (`uses`) | Purpose | Key `config` Fields |
|---------------|---------|---------------------|
| `kustomize-set-image` | Update image tag/digest in `kustomization.yaml` | `path`, `images` (`[{image, name, newName, tag, digest, useDigest}]`) |
| `kustomize-build` | Render Kustomize overlay to output file/dir | `path`, `outPath`, `pluginConfig` |
| `helm-template` | Render Helm chart into plain YAML manifests | `path`, `outPath`, `releaseName`, `namespace`, `valuesFiles`, `setValues`, `includeCRDs`, `useReleaseName` |
| `helm-update-chart` | Update `Chart.yaml` dependencies and run `helm dependency update` | `path`, `charts` (`[{repository, name, version, key}]`) |
| `oci-copy` / `oci-push` / `oci-pull` | Copy or push OCI artifacts across registries (v1.11+) | `srcRef`, `destRef`, `mediaType` |

## YAML, JSON, TOML & File Manipulation Steps

| Step (`uses`) | Purpose | Key `config` Fields |
|---------------|---------|---------------------|
| `yaml-update` | Update keys in YAML files (replaces `helm-update-image`) | `path`, `updates` (`[{key, value}]`) |
| `yaml-parse` | Parse YAML keys into step `outputs` | `path`, `outputs` (`[{name, fromExpression}]`) |
| `json-update` | Update keys in JSON files | `path`, `updates` (`[{key, value}]`) |
| `json-parse` | Parse JSON keys into step `outputs` | `path`, `outputs` (`[{name, fromExpression}]`) |
| `toml-update` / `toml-parse` | Update or parse TOML configuration files (v1.12) | `path`, `updates` / `outputs` |
| `copy` | Copy files or directories within workspace | `inPath`, `outPath`, `ignore` |
| `delete` | Delete files or directories from workspace | `path`, `strict` |
| `mkdir` | Create workspace directories | `path` |
| `untar` / `untar-gz` / `unzip` | Extract archives in workspace | `inPath`, `outPath` |

## Argo CD & HTTP Integration Steps

| Step (`uses`) | Purpose | Key `config` Fields |
|---------------|---------|---------------------|
| `argocd-update` | Sync Argo CD Applications and wait for health | `apps` (`[{name, namespace, sources: [{repoURL, desiredRevision, helm, kustomize}]}]`) |
| `http` | Perform arbitrary HTTP calls (webhooks, Slack, APIs) | `url`, `method`, `headers`, `queryParams`, `body`, `successExpression`, `outputs`, `timeout` |
| `wait` | Pause promotion for a fixed duration (v1.11+) | `duration` (e.g., `"30s"`, `"5m"`) |
| `fail` | Intentionally fail a promotion step on condition | `message` |

## Removed Steps & Breaking Config Changes

1. **`helm-update-image` (Removed in v1.8)**: Replace with `yaml-update` targeting `values.yaml` (e.g., `updates: [{key: "image.tag", value: "${{ quote(imageFrom('...').tag) }}"}]`).
2. **`git-open-pr.config.createTargetBranch` (Removed in v1.12)**: Configure `createTargetBranch` on `git-push` instead; for chart dependency updates always use `helm-update-chart` (not `helm-chart-update`).
3. **`git-open-pr` / `git-wait-for-pr` renamed**: Older `open-pr` and `wait-for-pr` aliases were removed; always use `git-open-pr` and `git-wait-for-pr`.
4. **`fromOrigin` in step config (Removed in v1.8)**: Pass `warehouse('<name>')` as the second argument to `imageFrom()`, `commitFrom()`, or `chartFrom()`.
5. **`git-commit.config.author` (Moved in v1.8)**: Configure `author` inside `git-clone.config.author`.
