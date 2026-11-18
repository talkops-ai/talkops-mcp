#!/usr/bin/env python3
"""Offline generator for Kargo v1.12 PromotionTask / Stage promotion step arrays.

Produces validated step arrays for standard GitOps patterns:
- gitops-image-update (yaml-update on values.yaml + git-commit + git-push + argocd-update)
- gitops-kustomize (kustomize-set-image + kustomize-build + git-commit + git-push + argocd-update)
- gitops-helm-template (helm-template + git-commit + git-push + argocd-update)
- gitops-pull-request (yaml-update + git-commit + git-push + git-open-pr + git-wait-for-pr + argocd-update)
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

import yaml


def build_steps(
    pattern: str,
    gitops_repo: str,
    image_repo: str,
    stage_branch: str,
    argocd_app: str,
    values_path: str,
    image_key: str,
) -> list[dict[str, Any]]:
    """Construct Kargo v1.12 promotion steps for the requested GitOps pattern."""
    clone_step: dict[str, Any] = {
        "uses": "git-clone",
        "config": {
            "repoURL": gitops_repo,
            "checkout": [
                {
                    "branch": stage_branch,
                    "create": True,
                    "path": "./out",
                }
            ],
        },
    }

    commit_step: dict[str, Any] = {
        "uses": "git-commit",
        "as": "commit",
        "config": {
            "path": "./out",
            "message": f"Promote ${{ imageFrom('{image_repo}').tag }} to ${{ ctx.stage }}",
        },
    }

    push_step: dict[str, Any] = {
        "uses": "git-push",
        "config": {
            "path": "./out",
            "targetBranch": stage_branch,
        },
    }

    argocd_step: dict[str, Any] = {
        "uses": "argocd-update",
        "config": {
            "apps": [
                {
                    "name": argocd_app,
                    "sources": [
                        {
                            "repoURL": gitops_repo,
                            "desiredRevision": "${{ outputs.commit.commit }}",
                        }
                    ],
                }
            ]
        },
    }

    if pattern == "gitops-image-update":
        update_step: dict[str, Any] = {
            "uses": "yaml-update",
            "as": "update-image",
            "config": {
                "path": f"./out/{values_path}",
                "updates": [
                    {
                        "key": image_key,
                        "value": f"${{{{ quote(imageFrom('{image_repo}').tag) }}}}",
                    }
                ],
            },
        }
        return [clone_step, update_step, commit_step, push_step, argocd_step]

    if pattern == "gitops-kustomize":
        kustomize_step: dict[str, Any] = {
            "uses": "kustomize-set-image",
            "as": "update-image",
            "config": {
                "path": "./out/overlays/${{ ctx.stage }}",
                "images": [
                    {
                        "image": image_repo,
                        "tag": f"${{{{ imageFrom('{image_repo}').tag }}}}",
                    }
                ],
            },
        }
        return [clone_step, kustomize_step, commit_step, push_step, argocd_step]

    if pattern == "gitops-helm-template":
        clone_step["config"]["checkout"].append(
            {"branch": "main", "path": "./src"}
        )
        clear_step: dict[str, Any] = {
            "uses": "git-clear",
            "config": {"path": "./out"},
        }
        helm_step: dict[str, Any] = {
            "uses": "helm-template",
            "config": {
                "path": "./src/charts/app",
                "outPath": "./out",
                "releaseName": "${{ ctx.stage }}",
                "valuesFiles": [f"./src/{values_path}"],
                "setValues": [
                    {
                        "key": image_key,
                        "value": f"${{{{ imageFrom('{image_repo}').tag }}}}",
                    }
                ],
            },
        }
        return [clone_step, clear_step, helm_step, commit_step, push_step, argocd_step]

    if pattern == "gitops-pull-request":
        update_step = {
            "uses": "yaml-update",
            "as": "update-image",
            "config": {
                "path": f"./out/{values_path}",
                "updates": [
                    {
                        "key": image_key,
                        "value": f"${{{{ quote(imageFrom('{image_repo}').tag) }}}}",
                    }
                ],
            },
        }
        push_pr_branch: dict[str, Any] = {
            "uses": "git-push",
            "as": "push",
            "config": {
                "path": "./out",
                "generateTargetBranch": True,
            },
        }
        open_pr: dict[str, Any] = {
            "uses": "git-open-pr",
            "as": "open-pr",
            "config": {
                "repoURL": gitops_repo,
                "sourceBranch": "${{ outputs.push.branch }}",
                "targetBranch": stage_branch,
            },
        }
        wait_pr: dict[str, Any] = {
            "uses": "git-wait-for-pr",
            "as": "wait-pr",
            "config": {
                "repoURL": gitops_repo,
                "prNumber": "${{ outputs['open-pr'].pr.id }}",
            },
        }
        argocd_pr_step: dict[str, Any] = {
            "uses": "argocd-update",
            "config": {
                "apps": [
                    {
                        "name": argocd_app,
                        "sources": [
                            {
                                "repoURL": gitops_repo,
                                "desiredRevision": "${{ outputs['wait-pr'].commit }}",
                            }
                        ],
                    }
                ]
            },
        }
        return [
            clone_step,
            update_step,
            commit_step,
            push_pr_branch,
            open_pr,
            wait_pr,
            argocd_pr_step,
        ]

    raise ValueError(f"Unsupported pattern: {pattern}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Render Kargo v1.12 PromotionTask / Stage promotion step arrays."
    )
    parser.add_argument(
        "--pattern",
        choices=[
            "gitops-image-update",
            "gitops-kustomize",
            "gitops-helm-template",
            "gitops-pull-request",
        ],
        default="gitops-image-update",
        help="GitOps promotion step pattern to generate.",
    )
    parser.add_argument(
        "--gitops-repo",
        default="${{ vars.gitopsRepo }}",
        help="GitOps repository URL or expression.",
    )
    parser.add_argument(
        "--image-repo",
        default="ghcr.io/example/app",
        help="Container image repository URL.",
    )
    parser.add_argument(
        "--stage-branch",
        default="stage/${{ ctx.stage }}",
        help="Target Git branch for the stage.",
    )
    parser.add_argument(
        "--argocd-app",
        default="app-${{ ctx.stage }}",
        help="Argo CD Application name or expression.",
    )
    parser.add_argument(
        "--values-path",
        default="stages/${{ ctx.stage }}/values.yaml",
        help="Relative path to YAML values file inside repository.",
    )
    parser.add_argument(
        "--image-key",
        default="image.tag",
        help="YAML key path to update with the new image tag.",
    )
    parser.add_argument(
        "--format",
        choices=["json", "yaml"],
        default="json",
        help="Output serialization format.",
    )
    args = parser.parse_args(argv)

    steps = build_steps(
        pattern=args.pattern,
        gitops_repo=args.gitops_repo,
        image_repo=args.image_repo,
        stage_branch=args.stage_branch,
        argocd_app=args.argocd_app,
        values_path=args.values_path,
        image_key=args.image_key,
    )
    payload = {"pattern": args.pattern, "steps": steps}
    if args.format == "yaml":
        sys.stdout.write(yaml.safe_dump(payload, sort_keys=False))
    else:
        sys.stdout.write(json.dumps(payload, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
