"""Shared pytest fixtures for the ArgoCD MCP Server test suite."""

import json
from pathlib import Path
from typing import Any, Callable

import httpx
import pytest
import respx

from argocd_mcp_server.config import ArgoCDConfig, GitConfig, ServerConfig
from argocd_mcp_server.server.bootstrap import ServerBootstrap
from argocd_mcp_server.services import (
    ArgoCDClient,
    ArgoCDManagementService,
    ArgoCDService,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "argocd"
BASE_URL = "https://argocd.example.com"


def load_json_fixture(filename: str) -> Any:
    """Load and parse a JSON fixture from tests/fixtures/argocd/."""
    return json.loads((FIXTURES_DIR / filename).read_text(encoding="utf-8"))


def load_text_fixture(filename: str) -> str:
    """Load a raw text fixture from tests/fixtures/argocd/."""
    return (FIXTURES_DIR / filename).read_text(encoding="utf-8")


@pytest.fixture
def fixture_loader() -> Callable[[str], Any]:
    """Return helper to load JSON fixtures by filename."""
    return load_json_fixture


@pytest.fixture
def dummy_ssh_key_path(tmp_path: Path) -> str:
    """Create a temporary SSH private key file for SSH onboarding tests."""
    key_file = tmp_path / "id_ed25519"
    key_file.write_text(
        "-----BEGIN OPENSSH PRIVATE KEY-----\nTEST_PRIVATE_KEY_DATA\n-----END OPENSSH PRIVATE KEY-----\n",
        encoding="utf-8",
    )
    return str(key_file)


@pytest.fixture
def write_config(dummy_ssh_key_path: str) -> ServerConfig:
    """ServerConfig with MCP_ALLOW_WRITE=true and test credentials."""
    return ServerConfig(
        name="argocd-mcp-server",
        version="0.4.1",
        allow_write=True,
        toolsets=["all"],
        argocd=ArgoCDConfig(
            server_url=BASE_URL,
            auth_token="test-jwt-token-12345",
            insecure=False,
            timeout=5,
            max_retries=1,
        ),
        git=GitConfig(
            username="git-bot",
            password="git-pat-secret-token",
            ssh_private_key_path=dummy_ssh_key_path,
        ),
    )


@pytest.fixture
def readonly_config(dummy_ssh_key_path: str) -> ServerConfig:
    """ServerConfig with MCP_ALLOW_WRITE=false (default safe posture)."""
    return ServerConfig(
        name="argocd-mcp-server",
        version="0.4.1",
        allow_write=False,
        toolsets=["all"],
        argocd=ArgoCDConfig(
            server_url=BASE_URL,
            auth_token="test-jwt-token-12345",
            insecure=False,
            timeout=5,
            max_retries=1,
        ),
        git=GitConfig(
            username="git-bot",
            password="git-pat-secret-token",
            ssh_private_key_path=dummy_ssh_key_path,
        ),
    )


@pytest.fixture
def argocd_client(write_config: ServerConfig) -> ArgoCDClient:
    """Shared ArgoCDClient wired to write_config."""
    return ArgoCDClient(write_config)


@pytest.fixture
def argocd_service(write_config: ServerConfig, argocd_client: ArgoCDClient) -> ArgoCDService:
    """ArgoCDService wired to write_config and shared ArgoCDClient."""
    return ArgoCDService(write_config, client=argocd_client)


@pytest.fixture
def mgmt_service(
    write_config: ServerConfig, argocd_client: ArgoCDClient
) -> ArgoCDManagementService:
    """ArgoCDManagementService wired to write_config and shared ArgoCDClient."""
    return ArgoCDManagementService(write_config, client=argocd_client)


@pytest.fixture
def mcp_server_write(write_config: ServerConfig):
    """Initialized FastMCP server with write operations enabled."""
    mcp, _ = ServerBootstrap.initialize(write_config)
    return mcp


@pytest.fixture
def mcp_server_readonly(readonly_config: ServerConfig):
    """Initialized FastMCP server in read-only mode (MCP_ALLOW_WRITE=false)."""
    mcp, _ = ServerBootstrap.initialize(readonly_config)
    return mcp


@pytest.fixture
def standard_argocd_routes(respx_mock: respx.MockRouter) -> respx.MockRouter:
    """Register standard happy-path ArgoCD REST API routes on respx_mock."""
    apps_list = load_json_fixture("applications_list.json")
    app_detail = load_json_fixture("application_detail.json")
    managed_res = load_json_fixture("application_managed_resources.json")
    res_tree = load_json_fixture("application_resource_tree.json")
    events = load_json_fixture("application_events.json")
    logs_ndjson = load_text_fixture("application_logs_ndjson.txt")
    sync_resp = load_json_fixture("sync_operation_response.json")
    rollback_resp = load_json_fixture("rollback_response.json")
    repos_list = load_json_fixture("repositories_list.json")
    projects_list = load_json_fixture("projects_list.json")
    clusters_list = load_json_fixture("clusters_list.json")
    version_data = load_json_fixture("version.json")

    respx_mock.get(f"{BASE_URL}/api/version").mock(
        return_value=httpx.Response(200, json=version_data)
    )
    respx_mock.get(f"{BASE_URL}/api/v1/clusters").mock(
        return_value=httpx.Response(200, json=clusters_list)
    )
    respx_mock.get(f"{BASE_URL}/api/v1/applications").mock(
        return_value=httpx.Response(200, json=apps_list)
    )
    respx_mock.post(f"{BASE_URL}/api/v1/applications").mock(
        return_value=httpx.Response(200, json=app_detail)
    )
    respx_mock.get(f"{BASE_URL}/api/v1/applications/payments-service").mock(
        return_value=httpx.Response(200, json=app_detail)
    )
    respx_mock.put(f"{BASE_URL}/api/v1/applications/payments-service").mock(
        return_value=httpx.Response(200, json=app_detail)
    )
    respx_mock.delete(f"{BASE_URL}/api/v1/applications/payments-service").mock(
        return_value=httpx.Response(200, json={})
    )
    respx_mock.get(
        f"{BASE_URL}/api/v1/applications/payments-service/managed-resources"
    ).mock(return_value=httpx.Response(200, json=managed_res))
    respx_mock.get(
        f"{BASE_URL}/api/v1/applications/payments-service/resource-tree"
    ).mock(return_value=httpx.Response(200, json=res_tree))
    respx_mock.get(f"{BASE_URL}/api/v1/applications/payments-service/events").mock(
        return_value=httpx.Response(200, json=events)
    )
    respx_mock.get(
        f"{BASE_URL}/api/v1/applications/payments-service/pods/payments-api-7f8c9b-abc12/logs"
    ).mock(
        return_value=httpx.Response(
            200,
            text=logs_ndjson,
            headers={"Content-Type": "text/plain"},
        )
    )
    respx_mock.post(f"{BASE_URL}/api/v1/applications/payments-service/sync").mock(
        return_value=httpx.Response(200, json=sync_resp)
    )
    respx_mock.post(f"{BASE_URL}/api/v1/applications/payments-service/rollback").mock(
        return_value=httpx.Response(200, json=rollback_resp)
    )
    respx_mock.delete(
        f"{BASE_URL}/api/v1/applications/payments-service/operation"
    ).mock(return_value=httpx.Response(200, json={}))

    # Repositories
    respx_mock.get(f"{BASE_URL}/api/v1/repositories").mock(
        return_value=httpx.Response(200, json=repos_list)
    )
    respx_mock.get(
        f"{BASE_URL}/api/v1/repositories/https%3A%2F%2Fgithub.com%2Forg%2Fgitops-manifests.git"
    ).mock(return_value=httpx.Response(200, json=repos_list["items"][0]))
    respx_mock.post(f"{BASE_URL}/api/v1/repositories/validate").mock(
        return_value=httpx.Response(
            200, json={"connectionState": {"status": "Successful", "message": ""}}
        )
    )
    respx_mock.post(f"{BASE_URL}/api/v1/repositories").mock(
        return_value=httpx.Response(
            200,
            json={
                "repo": "https://github.com/org/gitops-manifests.git",
                "type": "git",
                "connectionState": {"status": "Successful", "message": ""},
            },
        )
    )
    respx_mock.delete(
        f"{BASE_URL}/api/v1/repositories/https%3A%2F%2Fgithub.com%2Forg%2Fgitops-manifests.git"
    ).mock(return_value=httpx.Response(200, json={}))

    # Projects
    respx_mock.get(f"{BASE_URL}/api/v1/projects").mock(
        return_value=httpx.Response(200, json=projects_list)
    )
    respx_mock.get(f"{BASE_URL}/api/v1/projects/production").mock(
        return_value=httpx.Response(200, json=projects_list["items"][0])
    )
    respx_mock.post(f"{BASE_URL}/api/v1/projects").mock(
        return_value=httpx.Response(200, json=projects_list["items"][0])
    )
    respx_mock.put(f"{BASE_URL}/api/v1/projects/production").mock(
        return_value=httpx.Response(200, json=projects_list["items"][0])
    )
    respx_mock.delete(f"{BASE_URL}/api/v1/projects/production").mock(
        return_value=httpx.Response(200, json={})
    )

    return respx_mock
