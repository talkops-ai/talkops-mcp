"""Tests for automated rollback capability.

Tests the rollback cache and revert_migration() (exposed via traefik_nginx_migration action=revert).
Since rollback interacts with the Kubernetes API, these tests validate the
service logic using mock objects.
"""

from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from traefik_mcp_server.migration_nginx.scanner import (
    ControllerInfo,
    IngressInfo,
    PathInfo,
    ScanResult,
    ServiceRef,
)

from traefik_mcp_server.services.nginx_migration_service import NginxMigrationService
from traefik_mcp_server.config import ServerConfig, KubernetesConfig
from traefik_mcp_server.migration_nginx.migration_plan import (
    IngressMigrationPlanEntry,
)


def _config():
    return ServerConfig(
        allow_write=True,
        kubernetes=KubernetesConfig(),
    )


def _mock_traefik_for_migration():
    mt = MagicMock()
    mt.upsert_servers_transport = AsyncMock(
        return_value={"name": "x", "namespace": "default", "action": "created"}
    )
    mt.merge_service_annotations = AsyncMock(return_value={"status": "success"})
    mt.delete_servers_transport = AsyncMock(return_value={"status": "success"})
    return mt


def _ing(name="web", ns="default"):
    return IngressInfo(
        namespace=ns,
        name=name,
        ingress_class="nginx",
        hosts=["web.test"],
        paths=[
            PathInfo(
                host="web.test", path="/", path_type="Prefix",
                service_name="svc", service_port=80,
            )
        ],
        annotations={
            "nginx.ingress.kubernetes.io/ssl-redirect": "true",
            "other-annotation": "keep-me",
        },
        nginx_annotations={"ssl-redirect": "true"},
        services=[ServiceRef(namespace=ns, name="svc", port=80)],
        complexity="simple",
    )


def _scan_result(ing):
    return ScanResult(
        cluster_name="c",
        controller=ControllerInfo(
            detected=True, type="ingress-nginx", version="1",
            namespace="ing", pod_name="p",
        ),
        ingresses=[ing],
        namespaces=[ing.namespace],
    )


class TestRollbackCache:
    def test_cache_is_empty_initially(self):
        svc = NginxMigrationService(_config(), _mock_traefik_for_migration())
        assert svc._rollback_cache == {}

    def test_migration_plan_entry_does_not_affect_rollback(self):
        """Verify shadow_mode and rollback are independent concerns."""
        entry = IngressMigrationPlanEntry(shadow_mode=True)
        assert entry.shadow_mode is True
        # Rollback cache is a service-level concern, not plan-level


class TestRevertMigration:
    def test_revert_strips_traefik_and_restores_nginx(self):
        import asyncio

        svc = NginxMigrationService(_config(), _mock_traefik_for_migration())

        # Simulate cached annotations (as captured during apply)
        svc._rollback_cache["default/web"] = {
            "nginx.ingress.kubernetes.io/ssl-redirect": "true",
            "nginx.ingress.kubernetes.io/limit-rps": "10",
            "other-annotation": "keep-me",
        }

        # Mock the Kubernetes clients
        mock_networking = MagicMock()
        mock_custom = MagicMock()
        svc._networking = mock_networking
        svc._custom = mock_custom

        # Mock read_namespaced_ingress: returns an Ingress with Traefik annotations
        mock_ingress = MagicMock()
        mock_ingress.metadata.annotations = {
            "traefik.ingress.kubernetes.io/router.middlewares": "default-web-ssl-redirect@kubernetescrd",
            "other-annotation": "keep-me",
        }
        mock_networking.read_namespaced_ingress.return_value = mock_ingress

        # Mock list/delete for Middleware cleanup
        mock_custom.list_namespaced_custom_object.return_value = {"items": []}

        result = asyncio.run(svc.revert_migration(namespace="default", ingress_name="web"))

        assert result["status"] == "success"
        assert "traefik.ingress.kubernetes.io/router.middlewares" in result["stripped_traefik_annotations"]
        assert "nginx.ingress.kubernetes.io/ssl-redirect" in result["restored_nginx_annotations"]
        assert "nginx.ingress.kubernetes.io/limit-rps" in result["restored_nginx_annotations"]
        assert result["had_cache"] is True

        # Verify patch was called
        mock_networking.patch_namespaced_ingress.assert_called_once()

        # Cache should be cleaned up
        assert "default/web" not in svc._rollback_cache

    def test_revert_restores_mutated_nginx_annotations(self):
        """P1.4: full-replace restores mutated values, not just missing ones."""
        import asyncio

        svc = NginxMigrationService(_config(), _mock_traefik_for_migration())

        # Cache has the ORIGINAL annotation value
        svc._rollback_cache["default/web"] = {
            "nginx.ingress.kubernetes.io/limit-rps": "10",
            "other-annotation": "keep-me",
        }

        mock_networking = MagicMock()
        mock_custom = MagicMock()
        svc._networking = mock_networking
        svc._custom = mock_custom

        # Live Ingress has a MUTATED nginx annotation value
        mock_ingress = MagicMock()
        mock_ingress.metadata.annotations = {
            "nginx.ingress.kubernetes.io/limit-rps": "999",  # mutated!
            "other-annotation": "keep-me",
        }
        mock_networking.read_namespaced_ingress.return_value = mock_ingress
        mock_custom.list_namespaced_custom_object.return_value = {"items": []}

        result = asyncio.run(svc.revert_migration(namespace="default", ingress_name="web"))

        assert result["status"] == "success"
        # The original value "10" should be in the restored list
        assert "nginx.ingress.kubernetes.io/limit-rps" in result["restored_nginx_annotations"]

        # Verify the patch payload uses the ORIGINAL cached value, not "999"
        patch_call = mock_networking.patch_namespaced_ingress.call_args
        patch_body = patch_call[1]["body"] if "body" in patch_call[1] else patch_call[0][2]
        patched_annotations = patch_body["metadata"]["annotations"]
        assert patched_annotations["nginx.ingress.kubernetes.io/limit-rps"] == "10"

    def test_revert_without_cache_still_strips_traefik(self):
        import asyncio

        svc = NginxMigrationService(_config(), _mock_traefik_for_migration())

        mock_networking = MagicMock()
        mock_custom = MagicMock()
        svc._networking = mock_networking
        svc._custom = mock_custom

        mock_ingress = MagicMock()
        mock_ingress.metadata.annotations = {
            "traefik.ingress.kubernetes.io/router.middlewares": "something",
            "other-annotation": "v",
        }
        mock_networking.read_namespaced_ingress.return_value = mock_ingress
        mock_custom.list_namespaced_custom_object.return_value = {"items": []}

        result = asyncio.run(svc.revert_migration(namespace="default", ingress_name="web"))

        assert result["status"] == "success"
        assert result["had_cache"] is False
        assert len(result["stripped_traefik_annotations"]) == 1
        assert len(result["restored_nginx_annotations"]) == 0

    def test_revert_deletes_labelled_middlewares(self):
        import asyncio

        svc = NginxMigrationService(_config(), _mock_traefik_for_migration())

        mock_networking = MagicMock()
        mock_custom = MagicMock()
        svc._networking = mock_networking
        svc._custom = mock_custom

        mock_ingress = MagicMock()
        mock_ingress.metadata.annotations = {}
        mock_networking.read_namespaced_ingress.return_value = mock_ingress

        # First list call (Middleware) returns 2 items; second (ServersTransport) returns 0
        mock_custom.list_namespaced_custom_object.side_effect = [
            {
                "items": [
                    {"metadata": {"name": "web-ssl-redirect"}},
                    {"metadata": {"name": "web-ratelimit"}},
                ]
            },
            {"items": []},  # no ServersTransport CRDs
        ]

        result = asyncio.run(svc.revert_migration(namespace="default", ingress_name="web"))

        assert result["status"] == "success"
        assert "web-ssl-redirect" in result["deleted_middlewares"]
        assert "web-ratelimit" in result["deleted_middlewares"]
        assert result["deleted_serverstransports"] == []
        assert mock_custom.delete_namespaced_custom_object.call_count == 2

    def test_revert_strips_service_sticky_session_patches(self):
        import asyncio

        svc = NginxMigrationService(_config(), _mock_traefik_for_migration())

        # Simulate cached service patch:
        svc._service_patch_cache["default/web"] = [
            ("default", "backend-svc", ["traefik.ingress.kubernetes.io/service.sticky.cookie"])
        ]

        mock_networking = MagicMock()
        mock_custom = MagicMock()
        mock_core = MagicMock()
        svc._networking = mock_networking
        svc._custom = mock_custom
        svc._core = mock_core

        mock_ingress = MagicMock()
        mock_ingress.metadata.annotations = {}
        mock_networking.read_namespaced_ingress.return_value = mock_ingress
        
        # 2 lists: Middleware, then ServersTransport
        mock_custom.list_namespaced_custom_object.side_effect = [
            {"items": []},
            {"items": []},
        ]

        result = asyncio.run(svc.revert_migration(namespace="default", ingress_name="web"))

        assert result["status"] == "success"
        assert "default/backend-svc" in result["reverted_services"]
        assert "default/web" not in svc._service_patch_cache
        
        mock_core.patch_namespaced_service.assert_called_once_with(
            name="backend-svc",
            namespace="default",
            body={"metadata": {"annotations": {"traefik.ingress.kubernetes.io/service.sticky.cookie": None}}},
        )
