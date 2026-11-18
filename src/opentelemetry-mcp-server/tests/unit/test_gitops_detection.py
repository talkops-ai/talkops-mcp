"""T-U7: Unit tests for GitOps ownership detection (Argo CD, Flux, Helm)."""

from __future__ import annotations

from opentelemetry_mcp_server.models.findings import FindingCode
from opentelemetry_mcp_server.utils.gitops import (
    build_gitops_finding,
    detect_gitops_ownership,
)


def test_detect_argocd_ownership():
    manifest = {
        "metadata": {
            "name": "otel-agent",
            "annotations": {
                "argocd.argoproj.io/tracking-id": "observability:opentelemetry.io/OpenTelemetryCollector:default/otel-agent"
            },
        }
    }
    info = detect_gitops_ownership(manifest)
    assert info["managed"] is True
    assert info["manager"] == "argocd"
    finding = build_gitops_finding(manifest, resource_ref_or_ns="default/otel-agent")
    assert finding is not None
    assert finding.code == FindingCode.GITOPS_MANAGED


def test_detect_flux_and_helm_ownership():
    flux_obj = {
        "metadata": {
            "labels": {
                "kustomize.toolkit.fluxcd.io/name": "infra-observability",
                "kustomize.toolkit.fluxcd.io/namespace": "flux-system",
            }
        }
    }
    flux_info = detect_gitops_ownership(flux_obj)
    assert flux_info["managed"] is True
    assert flux_info["manager"] == "flux"

    helm_obj = {
        "metadata": {
            "labels": {"app.kubernetes.io/managed-by": "Helm"},
            "annotations": {"meta.helm.sh/release-name": "otel-stack"},
        }
    }
    helm_info = detect_gitops_ownership(helm_obj)
    assert helm_info["managed"] is True
    assert helm_info["manager"] == "helm"


def test_unmanaged_resource_returns_none_finding():
    plain_obj = {"metadata": {"name": "manual-col", "labels": {}, "annotations": {}}}
    info = detect_gitops_ownership(plain_obj)
    assert info["managed"] is False
    assert build_gitops_finding(plain_obj) is None
