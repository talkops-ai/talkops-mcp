#!/usr/bin/env python3
"""Offline validator for Kargo v1.12 pipeline manifests (Project, ProjectConfig, Warehouse, Stage, PromotionTask).

Detects removed Kargo v1.7-v1.12 fields and Stage DAG cycles without network access:
- Project.spec (removed in v1.7 -> move promotionPolicies/webhookReceivers to ProjectConfig)
- Warehouse image.semverConstraint (deprecated -> use constraint)
- Warehouse allowTags / ignoreTags (removed in v1.7 -> use allowTagsRegexes / ignoreTagsRegexes)
- Removed promotion steps (helm-update-image, helm-update-chart, open-pr, wait-for-pr)
- Removed step config fields (fromOrigin, git-commit.config.author)
- Stage upstream DAG cycles
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

REMOVED_STEPS = {
    "helm-update-image": "Replaced by 'yaml-update' in Kargo v1.8+.",
    "helm-chart-update": "Not a registered Kargo v1.12 step; use 'helm-update-chart'.",
    "open-pr": "Renamed to 'git-open-pr'.",
    "wait-for-pr": "Renamed to 'git-wait-for-pr'.",
    "argocd-sync": "Use 'argocd-update'.",
}


def _validate_steps(steps: list[dict[str, Any]], context_name: str, errors: list[str]) -> None:
    for idx, step in enumerate(steps):
        if not isinstance(step, dict):
            continue
        uses = step.get("uses")
        if isinstance(uses, str) and uses in REMOVED_STEPS:
            errors.append(
                f"{context_name} step[{idx}] uses removed step '{uses}': {REMOVED_STEPS[uses]}"
            )
        config = step.get("config")
        if isinstance(config, dict):
            if "fromOrigin" in config:
                errors.append(
                    f"{context_name} step[{idx}] ('{uses}') uses removed 'config.fromOrigin'; "
                    "pass warehouse('<name>') to imageFrom/commitFrom/chartFrom instead."
                )
            if uses == "git-commit" and "author" in config:
                errors.append(
                    f"{context_name} step[{idx}] ('git-commit') uses 'config.author'; "
                    "configure 'author' on the 'git-clone' step instead."
                )
            if uses == "git-open-pr" and "createTargetBranch" in config:
                errors.append(
                    f"{context_name} step[{idx}] ('git-open-pr') uses removed 'config.createTargetBranch'; "
                    "configure 'createTargetBranch' on 'git-push' instead."
                )
            if uses == "git-push" and "maxRetries" in config:
                errors.append(
                    f"{context_name} step[{idx}] ('git-push') uses invalid 'config.maxRetries'; "
                    "configure 'maxAttempts' on 'git-push' instead."
                )


def _detect_stage_cycles(stage_edges: dict[str, list[str]], errors: list[str]) -> None:
    visited: set[str] = set()
    in_stack: set[str] = set()

    def dfs(node: str, path: list[str]) -> None:
        visited.add(node)
        in_stack.add(node)
        for upstream in stage_edges.get(node, []):
            if upstream in in_stack:
                cycle = " -> ".join([*path, upstream])
                errors.append(f"Stage DAG cycle detected: {cycle}")
            elif upstream not in visited and upstream in stage_edges:
                dfs(upstream, [*path, upstream])
        in_stack.remove(node)

    for stage_name in list(stage_edges.keys()):
        if stage_name not in visited:
            dfs(stage_name, [stage_name])


def validate_documents(docs: list[dict[str, Any]]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    stage_edges: dict[str, list[str]] = {}

    for doc in docs:
        if not isinstance(doc, dict):
            continue
        kind = str(doc.get("kind") or "")
        meta = doc.get("metadata") or {}
        name = str(meta.get("name") or "<unnamed>")
        spec = doc.get("spec") or {}

        if kind == "Project" and spec:
            errors.append(
                f"Project '{name}' defines 'spec', which was removed in Kargo v1.7+. "
                "Move promotionPolicies and webhookReceivers into a ProjectConfig resource."
            )

        elif kind == "Warehouse":
            subs = spec.get("subscriptions") or []
            for idx, sub in enumerate(subs):
                if not isinstance(sub, dict):
                    continue
                for sub_type in ("image", "git", "chart"):
                    inner = sub.get(sub_type)
                    if not isinstance(inner, dict):
                        continue
                    if sub_type == "image" and "semverConstraint" in inner:
                        warnings.append(
                            f"Warehouse '{name}' subscription[{idx}].image uses deprecated "
                            "'semverConstraint'; use 'constraint' instead."
                        )
                    if "allowTags" in inner:
                        errors.append(
                            f"Warehouse '{name}' subscription[{idx}].{sub_type} uses removed "
                            "'allowTags'; use 'allowTagsRegexes' (list of regex strings)."
                        )
                    if "ignoreTags" in inner:
                        errors.append(
                            f"Warehouse '{name}' subscription[{idx}].{sub_type} uses removed "
                            "'ignoreTags'; use 'ignoreTagsRegexes' (list of regex strings)."
                        )

        elif kind in ("PromotionTask", "ClusterPromotionTask"):
            steps = spec.get("steps") or []
            if isinstance(steps, list):
                _validate_steps(steps, f"{kind}/{name}", errors)

        elif kind == "Stage":
            upstreams: list[str] = []
            for rf in spec.get("requestedFreight") or []:
                if isinstance(rf, dict):
                    sources = rf.get("sources") or {}
                    if isinstance(sources, dict):
                        for st in sources.get("stages") or []:
                            if isinstance(st, str):
                                upstreams.append(st)
            stage_edges[name] = upstreams
            pt = (spec.get("promotionTemplate") or {}).get("spec") or {}
            steps = pt.get("steps") or []
            if isinstance(steps, list):
                _validate_steps(steps, f"Stage/{name}", errors)

    _detect_stage_cycles(stage_edges, errors)
    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "checked_resources": len(docs),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate Kargo v1.12 YAML/JSON manifests for removed fields and Stage DAG cycles."
    )
    parser.add_argument(
        "--file",
        "-f",
        required=True,
        help="Path to YAML or JSON file containing one or more Kargo manifests.",
    )
    args = parser.parse_args(argv)

    file_path = Path(args.file)
    raw = file_path.read_text(encoding="utf-8")
    docs = [d for d in yaml.safe_load_all(raw) if isinstance(d, dict)]
    report = validate_documents(docs)
    sys.stdout.write(json.dumps(report, indent=2) + "\n")
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
