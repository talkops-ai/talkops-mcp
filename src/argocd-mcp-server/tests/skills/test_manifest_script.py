"""Tests for bundled skill helper scripts (generate_argocd_manifests.py and fetch_argocd_token.py)."""

import subprocess
import sys
from pathlib import Path

PLUGIN_DIR = Path(__file__).parent.parent.parent
MANIFEST_SCRIPT = (
    PLUGIN_DIR
    / "skills"
    / "deploying-argocd-applications"
    / "scripts"
    / "generate_argocd_manifests.py"
)
TOKEN_SCRIPT = (
    PLUGIN_DIR
    / "skills"
    / "onboarding-argocd-repositories-and-projects"
    / "scripts"
    / "fetch_argocd_token.py"
)


def test_generate_application_manifest_cli() -> None:
    """generate_argocd_manifests.py application produces valid ArgoCD Application YAML."""
    res = subprocess.run(
        [
            sys.executable,
            str(MANIFEST_SCRIPT),
            "application",
            "--name",
            "payments-service",
            "--project",
            "production",
            "--repo-url",
            "https://github.com/org/gitops-manifests.git",
            "--path",
            "apps/payments/overlays/prod",
            "--dest-namespace",
            "payments-prod",
            "--revision",
            "v1.4.0",
            "--auto-sync",
            "--prune",
            "--self-heal",
            "--create-namespace",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    out = res.stdout
    assert "apiVersion: argoproj.io/v1alpha1" in out
    assert "kind: Application" in out
    assert "name: payments-service" in out
    assert "project: production" in out
    assert "CreateNamespace=true" in out
    assert "selfHeal: true" in out


def test_generate_applicationset_manifest_cli() -> None:
    """generate_argocd_manifests.py applicationset produces valid ArgoCD ApplicationSet YAML."""
    res = subprocess.run(
        [
            sys.executable,
            str(MANIFEST_SCRIPT),
            "applicationset",
            "--name",
            "payments-appset",
            "--project",
            "production",
            "--repo-url",
            "https://github.com/org/gitops-manifests.git",
            "--path-template",
            "apps/payments/overlays/{{env}}",
            "--environments",
            "dev=https://dev.k8s.local:6443,prod=https://kubernetes.default.svc",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    out = res.stdout
    assert "kind: ApplicationSet" in out
    assert "name: payments-appset" in out
    assert "env: dev" in out
    assert "env: prod" in out


def test_generate_appproject_manifest_cli() -> None:
    """generate_argocd_manifests.py appproject produces valid ArgoCD AppProject YAML."""
    res = subprocess.run(
        [
            sys.executable,
            str(MANIFEST_SCRIPT),
            "appproject",
            "--name",
            "production",
            "--description",
            "Production project",
            "--source-repos",
            "https://github.com/org/gitops-manifests.git",
            "--destinations",
            "payments-prod=https://kubernetes.default.svc",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    out = res.stdout
    assert "kind: AppProject" in out
    assert "name: production" in out
    assert "namespace: payments-prod" in out


def test_both_scripts_support_help_flag() -> None:
    """Both bundled scripts support --help and exit with code 0."""
    for script in (MANIFEST_SCRIPT, TOKEN_SCRIPT):
        res = subprocess.run(
            [sys.executable, str(script), "--help"],
            capture_output=True,
            text=True,
            check=True,
        )
        assert res.returncode == 0
        assert "usage:" in res.stdout.lower()
