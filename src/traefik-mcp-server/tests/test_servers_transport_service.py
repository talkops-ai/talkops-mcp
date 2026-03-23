"""Unit tests for TraefikService ServersTransport and Service annotation helpers."""

import asyncio
from unittest.mock import MagicMock, patch

import pytest
from kubernetes.client.rest import ApiException

from traefik_mcp_server.config import KubernetesConfig, ServerConfig
from traefik_mcp_server.services.traefik_service import (
    TraefikService,
    parse_multidoc_yaml_objects,
    TRAEFIK_STICKY_SERVICE_ANNOTATION_KEYS,
)
from traefik_mcp_server.exceptions.custom import TraefikServiceError


def _cfg() -> ServerConfig:
    return ServerConfig(kubernetes=KubernetesConfig())


def test_parse_multidoc_yaml_objects_strips_comments():
    content = """# preamble
---
apiVersion: v1
kind: ServersTransport
metadata:
  name: t1
  namespace: ns1
"""
    objs = parse_multidoc_yaml_objects(content)
    assert len(objs) == 1
    assert objs[0]["kind"] == "ServersTransport"
    assert objs[0]["metadata"]["name"] == "t1"


def test_upsert_servers_transport_create():
    svc = TraefikService(_cfg())
    st_api = MagicMock()
    svc._initialized = True
    svc._k8s_client = MagicMock()
    svc._serverstransport_api = st_api

    body = {
        "apiVersion": "traefik.io/v1alpha1",
        "kind": "ServersTransport",
        "metadata": {"name": "my-transport", "namespace": "prod"},
        "spec": {"forwardingTimeouts": {"dialTimeout": "5s"}},
    }
    out = asyncio.run(svc.upsert_servers_transport(body))
    st_api.create.assert_called_once_with(body=body, namespace="prod")
    assert out["action"] == "created"
    assert out["name"] == "my-transport"


def test_upsert_servers_transport_conflict_patches():
    svc = TraefikService(_cfg())
    st_api = MagicMock()
    st_api.create.side_effect = ApiException(status=409)
    svc._initialized = True
    svc._k8s_client = MagicMock()
    svc._serverstransport_api = st_api

    body = {
        "apiVersion": "traefik.io/v1alpha1",
        "kind": "ServersTransport",
        "metadata": {"name": "t", "namespace": "default"},
        "spec": {"insecureSkipVerify": True},
    }
    out = asyncio.run(svc.upsert_servers_transport(body))
    st_api.patch.assert_called_once()
    assert out["action"] == "updated"


def test_delete_servers_transport_404():
    svc = TraefikService(_cfg())
    st_api = MagicMock()
    st_api.delete.side_effect = ApiException(status=404)
    svc._initialized = True
    svc._serverstransport_api = st_api

    with pytest.raises(TraefikServiceError, match="not found"):
        asyncio.run(svc.delete_servers_transport("missing", "default"))


def test_merge_service_annotations():
    svc = TraefikService(_cfg())
    svc._initialized = True
    svc._k8s_client = MagicMock()
    mock_core = MagicMock()
    with patch("traefik_mcp_server.services.traefik_service.client.CoreV1Api", return_value=mock_core):
        out = asyncio.run(
            svc.merge_service_annotations(
                "api-svc",
                "default",
                {"traefik.ingress.kubernetes.io/service.sticky.cookie": "true"},
            )
        )
    mock_core.patch_namespaced_service.assert_called_once()
    assert out["status"] == "success"


def test_strip_service_annotation_keys():
    svc = TraefikService(_cfg())
    svc._initialized = True
    svc._k8s_client = MagicMock()
    mock_core = MagicMock()
    with patch("traefik_mcp_server.services.traefik_service.client.CoreV1Api", return_value=mock_core):
        out = asyncio.run(
            svc.strip_service_annotation_keys(
                "api-svc",
                "default",
                keys=TRAEFIK_STICKY_SERVICE_ANNOTATION_KEYS[:2],
            )
        )
    call_kw = mock_core.patch_namespaced_service.call_args[1]
    assert (
        call_kw["body"]["metadata"]["annotations"][TRAEFIK_STICKY_SERVICE_ANNOTATION_KEYS[0]]
        is None
    )
    assert out["action"] == "stripped"


def test_build_and_upsert_servers_transport_requires_spec():
    svc = TraefikService(_cfg())
    st_api = MagicMock()
    svc._initialized = True
    svc._k8s_client = MagicMock()
    svc._serverstransport_api = st_api

    with pytest.raises(TraefikServiceError, match="At least one"):
        asyncio.run(svc.build_and_upsert_servers_transport("x", "default"))


def test_build_and_upsert_servers_transport_insecure_only():
    svc = TraefikService(_cfg())
    st_api = MagicMock()
    svc._initialized = True
    svc._k8s_client = MagicMock()
    svc._serverstransport_api = st_api

    asyncio.run(
        svc.build_and_upsert_servers_transport(
            "bt",
            "ns",
            insecure_skip_verify=True,
        )
    )
    st_api.create.assert_called_once()
    body = st_api.create.call_args[1]["body"]
    assert body["spec"]["insecureSkipVerify"] is True
