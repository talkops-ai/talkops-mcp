"""Shared pytest fixtures for unit, in-memory MCP integration, and skill tests."""

from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock
import pytest

from argo_rollout_mcp_server.config import KubernetesConfig, ServerConfig
from argo_rollout_mcp_server.server.bootstrap import ServerBootstrap
from argo_rollout_mcp_server.services.generator_service import GeneratorService


@pytest.fixture
def server_root() -> Path:
    """Return the absolute path to the argo-rollout-mcp-server root directory."""
    return Path(__file__).resolve().parent.parent


@pytest.fixture
def fixtures_dir(server_root: Path) -> Path:
    """Return path to tests/fixtures/manifests."""
    return server_root / "tests" / "fixtures" / "manifests"


@pytest.fixture
def fake_argo_service() -> MagicMock:
    """Create a comprehensive mock ArgoRolloutsService for integration tests."""
    svc = MagicMock()

    svc.list_rollouts = AsyncMock(
        return_value={
            "rollouts": [
                {
                    "name": "payments-api",
                    "namespace": "default",
                    "phase": "Healthy",
                    "health_score": 100,
                    "strategy": "canary",
                    "desired_replicas": 3,
                    "current_replicas": 3,
                    "ready_replicas": 3,
                    "available_replicas": 3,
                    "image": "ghcr.io/talkops/payments-api:1.4.0",
                    "created": "2026-01-01T00:00:00Z",
                }
            ],
            "count": 1,
        }
    )

    svc.get_rollout_status = AsyncMock(
        return_value={
            "name": "payments-api",
            "namespace": "default",
            "phase": "Healthy",
            "health_score": 100,
            "message": "",
            "strategy": "canary",
            "image": "ghcr.io/talkops/payments-api:1.4.0",
            "current_step": 2,
            "total_steps": 6,
            "canary_weight": 25,
            "stable_rs": "7d9f8b6c5",
            "current_pod_hash": "8f4a2c1b9",
            "paused": False,
            "pause_conditions": [],
            "aborted": False,
            "workload_ref": None,
            "replicas": {"total": 3, "updated": 1, "ready": 3, "available": 3},
            "desired_replicas": 3,
            "conditions": [
                {"type": "Available", "status": "True", "reason": "Available", "message": "Rollout has minimum availability"}
            ],
            "timestamp": "2026-01-01T00:00:00Z",
        }
    )

    svc.get_rollout_manifest = AsyncMock(
        return_value="""apiVersion: argoproj.io/v1alpha1
kind: Rollout
metadata:
  name: payments-api
  namespace: default
  managedFields:
    - manager: kubectl
  annotations:
    kubectl.kubernetes.io/last-applied-configuration: '{"secret":"leak"}'
spec:
  replicas: 3
  selector:
    matchLabels:
      app: payments-api
  template:
    metadata:
      labels:
        app: payments-api
    spec:
      containers:
        - name: payments-api
          image: ghcr.io/talkops/payments-api:1.4.0
          env:
            - name: DB_PASSWORD
              value: super-secret-password
            - name: POD_NAME
              valueFrom:
                fieldRef:
                  fieldPath: metadata.name
  strategy:
    canary:
      stableService: payments-api-stable
      canaryService: payments-api-canary
      steps:
        - setWeight: 25
        - pause: {}
"""
    )

    svc.create_rollout = AsyncMock(
        return_value={
            "status": "success",
            "rollout_name": "payments-api",
            "namespace": "default",
            "strategy": "canary",
            "replicas": 3,
            "image": "ghcr.io/talkops/payments-api:1.4.0",
        }
    )

    svc.update_rollout_image = AsyncMock(
        return_value={
            "status": "success",
            "rollout_name": "payments-api",
            "namespace": "default",
            "old_image": "ghcr.io/talkops/payments-api:1.4.0",
            "new_image": "ghcr.io/talkops/payments-api:1.5.0",
            "message": "Updated rollout 'payments-api' image to 'ghcr.io/talkops/payments-api:1.5.0'",
        }
    )

    svc.update_canary_strategy = AsyncMock(
        return_value={
            "status": "success",
            "rollout_name": "payments-api",
            "namespace": "default",
            "message": "Canary strategy updated on Rollout 'payments-api'",
        }
    )

    svc.set_traffic_routing = AsyncMock(
        return_value={
            "status": "success",
            "rollout_name": "payments-api",
            "namespace": "default",
            "strategy": "canary",
            "traffic_routing": {"traefik": {"weightedTraefikServiceName": "payments-wrr"}},
            "message": "trafficRouting patched on Rollout 'payments-api'",
        }
    )

    svc.remove_conflicting_strategy_block = MagicMock(
        return_value={
            "status": "success",
            "rollout_name": "payments-api",
            "namespace": "default",
            "message": "Removed conflicting canary block from Rollout 'payments-api'",
        }
    )

    svc.promote_rollout = AsyncMock(
        return_value={
            "status": "success",
            "rollout_name": "payments-api",
            "namespace": "default",
            "message": "Promoted rollout 'payments-api'",
        }
    )
    svc.abort_rollout = AsyncMock(
        return_value={
            "status": "success",
            "rollout_name": "payments-api",
            "namespace": "default",
            "message": "Aborted rollout 'payments-api'",
        }
    )
    svc.retry_rollout = AsyncMock(
        return_value={
            "status": "success",
            "rollout_name": "payments-api",
            "namespace": "default",
            "message": "Retried rollout 'payments-api'",
        }
    )
    svc.pause_rollout = AsyncMock(
        return_value={
            "status": "success",
            "rollout_name": "payments-api",
            "namespace": "default",
            "message": "Paused rollout 'payments-api'",
        }
    )
    svc.resume_rollout = AsyncMock(
        return_value={
            "status": "success",
            "rollout_name": "payments-api",
            "namespace": "default",
            "message": "Resumed rollout 'payments-api'",
        }
    )
    svc.skip_analysis_promote = AsyncMock(
        return_value={
            "status": "success",
            "rollout_name": "payments-api",
            "namespace": "default",
            "message": "Skipped analysis and promoted rollout 'payments-api'",
        }
    )

    svc.check_workload_ref_delete_safety = AsyncMock(return_value=None)
    svc.verify_rollout_healthy = AsyncMock(return_value=True)
    svc.delete_rollout = AsyncMock(
        return_value={
            "status": "success",
            "rollout_name": "payments-api",
            "namespace": "default",
            "message": "Deleted rollout 'payments-api'",
        }
    )

    svc.scale_deployment = AsyncMock(
        return_value={
            "status": "success",
            "deployment": "payments-api",
            "namespace": "default",
            "replicas": 0,
            "message": "Scaled Deployment 'payments-api' to 0 replicas",
        }
    )
    svc.delete_deployment = AsyncMock(
        return_value={
            "status": "success",
            "deployment": "payments-api",
            "namespace": "default",
            "message": "Deleted Deployment 'payments-api'",
        }
    )
    svc.patch_workload_ref_scale_down = AsyncMock(
        return_value={
            "status": "success",
            "rollout_name": "payments-api",
            "namespace": "default",
            "scale_down": "onsuccess",
            "message": "Patched workloadRef.scaleDown to 'onsuccess'",
        }
    )

    svc.convert_rollout_to_deployment_live = AsyncMock(
        side_effect=lambda name, namespace="default", deployment_strategy="RollingUpdate", dry_run=True, generator_service=None: {
            "status": "preview" if dry_run else "success",
            "dry_run": dry_run,
            "name": name,
            "namespace": namespace,
            "deployment_strategy": deployment_strategy,
            "manifest": f"apiVersion: apps/v1\nkind: Deployment\nmetadata:\n  name: {name}\n  namespace: {namespace}\n",
            "message": f"Converted Rollout '{name}' to Deployment",
        }
    )

    svc.set_analysis_template = AsyncMock(
        return_value={
            "status": "success",
            "rollout_name": "payments-api",
            "template_name": "payments-api-analysis",
            "namespace": "default",
            "scope": "namespace",
            "message": "Configured AnalysisTemplate 'payments-api-analysis'",
        }
    )
    svc.delete_analysis_template = MagicMock(
        return_value={
            "status": "success",
            "template_name": "payments-api-analysis",
            "namespace": "default",
            "scope": "namespace",
            "message": "Deleted AnalysisTemplate 'payments-api-analysis'",
        }
    )

    svc.create_experiment = AsyncMock(
        return_value={
            "status": "success",
            "experiment": "payments-exp",
            "namespace": "default",
            "templates": ["baseline", "candidate"],
            "duration": "20m",
            "analyses": [],
            "message": "Experiment 'payments-exp' created successfully",
            "traefik_note": "Weighted experiment traffic routing is NOT supported with Traefik.",
        }
    )
    svc.get_experiment_status = AsyncMock(
        return_value={
            "status": "success",
            "experiment": "payments-exp",
            "namespace": "default",
            "phase": "Running",
            "templateStatuses": [{"name": "baseline", "replicas": 1, "readyReplicas": 1, "status": "Running"}],
            "analysisRuns": [],
        }
    )
    svc.delete_experiment = AsyncMock(
        return_value={
            "status": "success",
            "experiment": "payments-exp",
            "namespace": "default",
            "message": "Experiment 'payments-exp' deleted successfully",
        }
    )

    svc.diagnose_rollout = AsyncMock(
        return_value={
            "name": "payments-api",
            "namespace": "default",
            "phase": "Healthy",
            "strategy": "canary",
            "summary": "Rollout 'payments-api' in namespace 'default' is in phase 'Healthy' (codes: HEALTHY).",
            "diagnosis_codes": ["HEALTHY"],
            "current_step": 2,
            "canary_weight": 25,
            "replicas": {"desired": 3, "ready": 3, "available": 3, "updated": 3},
            "conditions": [],
            "failing_metrics": [],
            "warning_events": [],
            "pods": [],
        }
    )

    svc.list_analysis_runs = AsyncMock(
        return_value={
            "rollout_name": "payments-api",
            "namespace": "default",
            "count": 1,
            "analysis_runs": [
                {
                    "name": "payments-api-7d9f8b6c5-1",
                    "phase": "Successful",
                    "message": "",
                    "created_at": "2026-01-01T00:05:00Z",
                    "metric_results": [{"name": "error-rate", "phase": "Successful", "count": 3, "successful": 3, "failed": 0}],
                    "failing_metrics": [],
                }
            ],
        }
    )

    svc.list_analysis_templates = AsyncMock(
        return_value={
            "namespace": "default",
            "count": 1,
            "templates": [
                {
                    "name": "payments-api-analysis",
                    "namespace": "default",
                    "scope": "namespace",
                    "args": [],
                    "metrics": ["error-rate", "latency-p99", "latency-p95"],
                }
            ],
        }
    )

    svc.get_rollout_history = AsyncMock(
        return_value={
            "history": [
                {
                    "type": "Available",
                    "status": "True",
                    "reason": "Available",
                    "message": "Rollout has minimum availability",
                    "lastTransitionTime": "2026-01-01T00:00:00Z",
                }
            ]
        }
    )
    svc.get_rollout_revision_history = AsyncMock(
        return_value={
            "currentRevision": 2,
            "revisions": [
                {"revision": 2, "name": "payments-api-8f4a2c1b9", "replicas": 3, "readyReplicas": 3, "image": "ghcr.io/talkops/payments-api:1.4.0"},
                {"revision": 1, "name": "payments-api-7d9f8b6c5", "replicas": 0, "readyReplicas": 0, "image": "ghcr.io/talkops/payments-api:1.3.0"},
            ],
        }
    )

    svc.get_kube_contexts = MagicMock(
        return_value={
            "active_context": "us-west-prod",
            "configured_context": "us-west-prod",
            "in_cluster": False,
            "contexts": [{"name": "us-west-prod", "cluster": "us-west", "namespace": "default"}],
        }
    )
    svc.get_server_capabilities = MagicMock(
        return_value={
            "server_name": "argo-rollout-mcp-server",
            "server_version": "0.2.0",
            "allow_write": True,
            "toolsets": ["all"],
            "cluster_connected": True,
            "crds_installed": {
                "rollout": True,
                "analysis_template": True,
                "cluster_analysis_template": True,
                "analysis_run": True,
                "experiment": True,
            },
            "prometheus_url": "http://prometheus:9090",
        }
    )

    return svc


@pytest.fixture
def fake_generator_service(fixtures_dir: Path) -> GeneratorService:
    """Create a GeneratorService backed by fixture YAML for fetch_deployment_yaml and mocked cluster calls."""
    gen = GeneratorService()
    basic_yaml = (fixtures_dir / "deployment-basic.yaml").read_text(encoding="utf-8")
    gen.fetch_deployment_yaml = AsyncMock(return_value=basic_yaml)
    gen.discover_service_for_deployment = AsyncMock(return_value=None)
    gen.create_stable_canary_services = AsyncMock(
        side_effect=lambda app_name, namespace="default", port=80, target_port=None, selector_labels=None, apply=False, strategy="canary", pod_template_spec=None: {
            "status": "success",
            "stable_service_name": f"{app_name}-active" if strategy == "bluegreen" else f"{app_name}-stable",
            "canary_service_name": f"{app_name}-preview" if strategy == "bluegreen" else f"{app_name}-canary",
            "namespace": namespace,
            "applied": apply,
            "created": [
                f"{app_name}-active" if strategy == "bluegreen" else f"{app_name}-stable",
                f"{app_name}-preview" if strategy == "bluegreen" else f"{app_name}-canary",
            ]
            if apply
            else [],
            "already_existed": [],
        }
    )
    gen.create_rollout_service = AsyncMock(
        side_effect=lambda service_name, **kwargs: {
            "status": "success",
            "created": [service_name],
            "already_existed": [],
        }
    )
    gen.apply_rollout_crd = AsyncMock(
        side_effect=lambda rollout_yaml, namespace="default": {
            "rollout_name": "payments-api",
            "rollout_applied": True,
            "rollout_already_existed": False,
        }
    )
    return gen


def make_test_server(
    allow_write: bool = True,
    toolsets: Optional[List[str]] = None,
    prometheus_url: Optional[str] = "http://prometheus:9090",
    argo_service: Any = None,
    generator_service: Any = None,
):
    """Build an in-memory FastMCP server with injected fake services."""
    cfg = ServerConfig(
        allow_write=allow_write,
        toolsets=toolsets or ["all"],
        prometheus_url=prometheus_url,
        kubernetes=KubernetesConfig(in_cluster=False),
    )
    services: Dict[str, Any] = {}
    if argo_service is not None:
        services["argo_service"] = argo_service
    if generator_service is not None:
        services["generator_service"] = generator_service
    mcp, _ = ServerBootstrap.build(config=cfg, services=services)
    return mcp
