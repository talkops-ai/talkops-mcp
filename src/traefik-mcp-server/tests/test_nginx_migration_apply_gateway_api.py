"""NginxMigrationService.migrate() apply behavior for gateway-api vs traefik."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, Mock, patch

from traefik_mcp_server.config import KubernetesConfig, ServerConfig
from traefik_mcp_server.migration_nginx.scanner import (
    ControllerInfo,
    IngressInfo,
    PathInfo,
    ScanResult,
    ServiceRef,
)
from traefik_mcp_server.services.nginx_migration_service import NginxMigrationService


def _cfg(allow_write: bool = True) -> ServerConfig:
    return ServerConfig(
        allow_write=allow_write,
        kubernetes=KubernetesConfig(),
    )


def _scan_default() -> ScanResult:
    ing = IngressInfo(
        namespace="default",
        name="web",
        ingress_class="nginx",
        hosts=["app.example.com"],
        paths=[
            PathInfo(
                host="app.example.com",
                path="/",
                path_type="Prefix",
                service_name="web-svc",
                service_port=80,
            )
        ],
        annotations={"nginx.ingress.kubernetes.io/ssl-redirect": "true"},
        nginx_annotations={"ssl-redirect": "true"},
        services=[ServiceRef(namespace="default", name="web-svc", port=80)],
        complexity="simple",
    )
    return ScanResult(
        cluster_name="test",
        controller=ControllerInfo(
            detected=True, type="ingress-nginx", version="1",
            namespace="ing", pod_name="p",
        ),
        ingresses=[ing],
        namespaces=["default"],
    )


def _mock_tf():
    m = Mock()
    m.upsert_servers_transport = AsyncMock()
    m.merge_service_annotations = AsyncMock()
    m.delete_servers_transport = AsyncMock()
    return m


def test_migrate_gateway_api_apply_skipped_with_warning():
    svc = NginxMigrationService(_cfg(allow_write=True), _mock_tf())
    svc._ensure_clients = lambda: None
    svc._networking = MagicMock()
    svc._core = MagicMock()
    svc._custom = MagicMock()

    mock_apply = AsyncMock()
    svc._apply_migration = mock_apply

    with patch(
        "traefik_mcp_server.services.nginx_migration_service.NginxMigrationScanner",
    ) as MS:
        MS.return_value.scan = MagicMock(return_value=_scan_default())
        out = asyncio.run(
            svc.migrate(
                namespace="default",
                target="gateway-api",
                apply=True,
            ),
        )

    mock_apply.assert_not_called()
    assert out.get("status") == "success"
    ar = out.get("apply_result") or {}
    assert ar.get("status") == "skipped"
    assert ar.get("reason") == "gateway_api_apply_not_supported"
    assert "gateway-api" in (ar.get("message") or "").lower()
    assert "kubectl" in (ar.get("message") or "").lower() or "gitops" in (
        ar.get("message") or ""
    ).lower()


def test_migrate_traefik_apply_still_invokes_cluster_apply():
    svc = NginxMigrationService(_cfg(allow_write=True), _mock_tf())
    svc._ensure_clients = lambda: None
    svc._networking = MagicMock()
    svc._core = MagicMock()
    svc._custom = MagicMock()

    mock_apply = AsyncMock(
        return_value={
            "middleware_results": [],
            "ingress_results": [],
            "summary": {"applied": 0, "errors": 0},
        },
    )
    svc._apply_migration = mock_apply

    with patch(
        "traefik_mcp_server.services.nginx_migration_service.NginxMigrationScanner",
    ) as MS:
        MS.return_value.scan = MagicMock(return_value=_scan_default())
        out = asyncio.run(
            svc.migrate(
                namespace="default",
                target="traefik",
                apply=True,
            ),
        )

    mock_apply.assert_called_once()
    assert out.get("status") == "success"
    assert out.get("apply_result", {}).get("summary") is not None
