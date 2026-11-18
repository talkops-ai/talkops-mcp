#!/usr/bin/env python3
"""Offline YAML manifest generator for ArgoCD Application, ApplicationSet, and AppProject CRDs.

Uses only the Python standard library and outputs deterministic YAML to stdout or --output file.
"""

import argparse
import sys
from pathlib import Path
from typing import Dict, List, Optional


def _yaml_scalar(value: str) -> str:
    """Format a string safely as a YAML scalar."""
    if value == "" or any(ch in value for ch in (":", "{", "}", "[", "]", "#", "*", "&", "!", "|", ">", "'", '"', "%", "@", "`")):
        escaped = value.replace('"', '\\"')
        return f'"{escaped}"'
    if value.lower() in ("true", "false", "null", "yes", "no", "on", "off"):
        return f'"{value}"'
    return value


def generate_application_yaml(
    name: str,
    project: str,
    repo_url: str,
    path: str,
    dest_namespace: str,
    dest_server: str = "https://kubernetes.default.svc",
    revision: str = "HEAD",
    argocd_namespace: str = "argocd",
    auto_sync: bool = False,
    prune: bool = False,
    self_heal: bool = False,
    create_namespace: bool = False,
) -> str:
    """Render an argoproj.io/v1alpha1 Application YAML manifest."""
    lines = [
        "apiVersion: argoproj.io/v1alpha1",
        "kind: Application",
        "metadata:",
        f"  name: {_yaml_scalar(name)}",
        f"  namespace: {_yaml_scalar(argocd_namespace)}",
        "  finalizers:",
        "    - resources-finalizer.argocd.argoproj.io",
        "spec:",
        f"  project: {_yaml_scalar(project)}",
        "  source:",
        f"    repoURL: {_yaml_scalar(repo_url)}",
        f"    targetRevision: {_yaml_scalar(revision)}",
        f"    path: {_yaml_scalar(path)}",
        "  destination:",
        f"    server: {_yaml_scalar(dest_server)}",
        f"    namespace: {_yaml_scalar(dest_namespace)}",
    ]

    if auto_sync or create_namespace:
        lines.append("  syncPolicy:")
        if auto_sync:
            lines.extend([
                "    automated:",
                f"      prune: {'true' if prune else 'false'}",
                f"      selfHeal: {'true' if self_heal else 'false'}",
            ])
        if create_namespace:
            lines.extend([
                "    syncOptions:",
                "      - CreateNamespace=true",
            ])

    return "\n".join(lines) + "\n"


def generate_applicationset_yaml(
    name: str,
    project: str,
    repo_url: str,
    path_template: str,
    environments: List[Dict[str, str]],
    revision: str = "HEAD",
    argocd_namespace: str = "argocd",
    auto_sync: bool = False,
    prune: bool = False,
    self_heal: bool = False,
    create_namespace: bool = True,
) -> str:
    """Render an argoproj.io/v1alpha1 ApplicationSet YAML manifest using a List generator."""
    lines = [
        "apiVersion: argoproj.io/v1alpha1",
        "kind: ApplicationSet",
        "metadata:",
        f"  name: {_yaml_scalar(name)}",
        f"  namespace: {_yaml_scalar(argocd_namespace)}",
        "spec:",
        "  generators:",
        "    - list:",
        "        elements:",
    ]

    for env_item in environments:
        env_name = env_item["env"]
        server = env_item["server"]
        namespace = env_item.get("namespace") or f"{name}-{env_name}"
        lines.extend([
            f"          - env: {_yaml_scalar(env_name)}",
            f"            server: {_yaml_scalar(server)}",
            f"            namespace: {_yaml_scalar(namespace)}",
        ])

    lines.extend([
        "  template:",
        "    metadata:",
        f'      name: "{name}-{{{{env}}}}"',
        "    spec:",
        f"      project: {_yaml_scalar(project)}",
        "      source:",
        f"        repoURL: {_yaml_scalar(repo_url)}",
        f"        targetRevision: {_yaml_scalar(revision)}",
        f"        path: {_yaml_scalar(path_template)}",
        "      destination:",
        '        server: "{{server}}"',
        '        namespace: "{{namespace}}"',
    ])

    if auto_sync or create_namespace:
        lines.append("      syncPolicy:")
        if auto_sync:
            lines.extend([
                "        automated:",
                f"          prune: {'true' if prune else 'false'}",
                f"          selfHeal: {'true' if self_heal else 'false'}",
            ])
        if create_namespace:
            lines.extend([
                "        syncOptions:",
                "          - CreateNamespace=true",
            ])

    return "\n".join(lines) + "\n"


def generate_appproject_yaml(
    name: str,
    description: str,
    source_repos: List[str],
    destinations: List[Dict[str, str]],
    argocd_namespace: str = "argocd",
) -> str:
    """Render an argoproj.io/v1alpha1 AppProject YAML manifest."""
    lines = [
        "apiVersion: argoproj.io/v1alpha1",
        "kind: AppProject",
        "metadata:",
        f"  name: {_yaml_scalar(name)}",
        f"  namespace: {_yaml_scalar(argocd_namespace)}",
        "spec:",
        f"  description: {_yaml_scalar(description)}",
        "  sourceRepos:",
    ]
    for repo in source_repos:
        lines.append(f"    - {_yaml_scalar(repo)}")

    lines.append("  destinations:")
    for dest in destinations:
        lines.extend([
            f"    - namespace: {_yaml_scalar(dest.get('namespace', '*'))}",
            f"      server: {_yaml_scalar(dest.get('server', 'https://kubernetes.default.svc'))}",
        ])

    return "\n".join(lines) + "\n"


def _parse_environments(raw: str) -> List[Dict[str, str]]:
    """Parse comma-separated env=server[:namespace] pairs."""
    items: List[Dict[str, str]] = []
    for entry in raw.split(","):
        entry = entry.strip()
        if not entry:
            continue
        if "=" not in entry:
            raise ValueError(
                f"Invalid environment specification '{entry}'. Expected format: env=https://server:6443"
            )
        env_name, server = entry.split("=", 1)
        items.append({"env": env_name.strip(), "server": server.strip()})
    if not items:
        raise ValueError("At least one environment must be specified.")
    return items


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="generate_argocd_manifests.py",
        description="Generate deterministic ArgoCD Application, ApplicationSet, and AppProject YAML manifests.",
    )
    subparsers = parser.add_subparsers(dest="kind", required=True)

    # Application subparser
    app_p = subparsers.add_parser("application", help="Generate an ArgoCD Application manifest.")
    app_p.add_argument("--name", required=True, help="Application name.")
    app_p.add_argument("--project", default="default", help="AppProject name (default: default).")
    app_p.add_argument("--repo-url", required=True, help="Git repository URL.")
    app_p.add_argument("--path", required=True, help="Path within Git repository.")
    app_p.add_argument("--dest-namespace", required=True, help="Target Kubernetes namespace.")
    app_p.add_argument(
        "--dest-server",
        default="https://kubernetes.default.svc",
        help="Target cluster API URL.",
    )
    app_p.add_argument("--revision", default="HEAD", help="Target Git revision.")
    app_p.add_argument("--argocd-namespace", default="argocd", help="ArgoCD control-plane namespace.")
    app_p.add_argument("--auto-sync", action="store_true", help="Enable automated sync.")
    app_p.add_argument("--prune", action="store_true", help="Enable auto-prune (requires --auto-sync).")
    app_p.add_argument("--self-heal", action="store_true", help="Enable self-heal (requires --auto-sync).")
    app_p.add_argument("--create-namespace", action="store_true", help="Add CreateNamespace=true syncOption.")
    app_p.add_argument("--output", help="Write YAML to file instead of stdout.")

    # ApplicationSet subparser
    appset_p = subparsers.add_parser(
        "applicationset", help="Generate an ArgoCD ApplicationSet manifest."
    )
    appset_p.add_argument("--name", required=True, help="ApplicationSet name.")
    appset_p.add_argument("--project", default="default", help="AppProject name.")
    appset_p.add_argument("--repo-url", required=True, help="Git repository URL.")
    appset_p.add_argument(
        "--path-template",
        required=True,
        help="Manifest path template, e.g. 'apps/my-app/overlays/{{env}}'.",
    )
    appset_p.add_argument(
        "--environments",
        required=True,
        help="Comma-separated env=server pairs, e.g. 'dev=https://dev:6443,prod=https://kubernetes.default.svc'.",
    )
    appset_p.add_argument("--revision", default="HEAD", help="Target Git revision.")
    appset_p.add_argument("--argocd-namespace", default="argocd", help="ArgoCD namespace.")
    appset_p.add_argument("--auto-sync", action="store_true", help="Enable automated sync.")
    appset_p.add_argument("--prune", action="store_true", help="Enable auto-prune.")
    appset_p.add_argument("--self-heal", action="store_true", help="Enable self-heal.")
    appset_p.add_argument(
        "--no-create-namespace",
        action="store_true",
        help="Disable CreateNamespace=true syncOption.",
    )
    appset_p.add_argument("--output", help="Write YAML to file instead of stdout.")

    # AppProject subparser
    proj_p = subparsers.add_parser("appproject", help="Generate an ArgoCD AppProject manifest.")
    proj_p.add_argument("--name", required=True, help="AppProject name.")
    proj_p.add_argument("--description", default="", help="Project description.")
    proj_p.add_argument(
        "--source-repos",
        required=True,
        help="Comma-separated list of allowed source repository URLs.",
    )
    proj_p.add_argument(
        "--destinations",
        required=True,
        help="Comma-separated namespace=server pairs, e.g. 'prod-*=https://kubernetes.default.svc'.",
    )
    proj_p.add_argument("--argocd-namespace", default="argocd", help="ArgoCD namespace.")
    proj_p.add_argument("--output", help="Write YAML to file instead of stdout.")

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.kind == "application":
            yaml_out = generate_application_yaml(
                name=args.name,
                project=args.project,
                repo_url=args.repo_url,
                path=args.path,
                dest_namespace=args.dest_namespace,
                dest_server=args.dest_server,
                revision=args.revision,
                argocd_namespace=args.argocd_namespace,
                auto_sync=args.auto_sync,
                prune=args.prune,
                self_heal=args.self_heal,
                create_namespace=args.create_namespace,
            )
        elif args.kind == "applicationset":
            envs = _parse_environments(args.environments)
            yaml_out = generate_applicationset_yaml(
                name=args.name,
                project=args.project,
                repo_url=args.repo_url,
                path_template=args.path_template,
                environments=envs,
                revision=args.revision,
                argocd_namespace=args.argocd_namespace,
                auto_sync=args.auto_sync,
                prune=args.prune,
                self_heal=args.self_heal,
                create_namespace=not args.no_create_namespace,
            )
        else:
            repos = [r.strip() for r in args.source_repos.split(",") if r.strip()]
            dests = []
            for d in args.destinations.split(","):
                d = d.strip()
                if not d:
                    continue
                if "=" in d:
                    ns, srv = d.split("=", 1)
                    dests.append({"namespace": ns.strip(), "server": srv.strip()})
                else:
                    dests.append({"namespace": d, "server": "https://kubernetes.default.svc"})
            yaml_out = generate_appproject_yaml(
                name=args.name,
                description=args.description,
                source_repos=repos,
                destinations=dests,
                argocd_namespace=args.argocd_namespace,
            )

        if args.output:
            out_path = Path(args.output)
            out_path.write_text(yaml_out, encoding="utf-8")
        else:
            sys.stdout.write(yaml_out)
        return 0
    except Exception as exc:
        sys.stderr.write(f"Error generating manifest: {exc}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
