"""Pytest fixtures for Traefik MCP Server unit, integration, and skill tests."""

import pytest
from traefik_mcp_server.config import ServerConfig
from traefik_mcp_server.server.bootstrap import ServerBootstrap
from traefik_mcp_server.services.traefik_service import TraefikService
from tests.fixtures.k8s_objects import default_seed_objects
from tests.fixtures.prometheus_responses import get_prometheus_fixture
from tests.fixtures.sample_logs import SAMPLE_ACCESS_LOG_LINES, SAMPLE_CONTROLLER_LOG_LINES
from tests.fixtures.traefik_runtime import get_runtime_fixture


def build_seeded_service(config: ServerConfig) -> TraefikService:
    """Create a TraefikService pre-populated with realistic in-memory fixtures."""
    svc = TraefikService(
        config=config,
        seed_objects=default_seed_objects(),
        runtime_fixture=get_runtime_fixture(),
        prometheus_fixture=get_prometheus_fixture(),
    )
    svc.set_mock_logs("access", SAMPLE_ACCESS_LOG_LINES)
    svc.set_mock_logs("controller", SAMPLE_CONTROLLER_LOG_LINES)
    return svc


@pytest.fixture
def rw_config() -> ServerConfig:
    return ServerConfig(
        allow_write=True,
        toolsets=("all",),
        prometheus_url="http://prometheus.monitoring.svc:9090",
    )


@pytest.fixture
def ro_config() -> ServerConfig:
    return ServerConfig(
        allow_write=False,
        toolsets=("all",),
        prometheus_url="http://prometheus.monitoring.svc:9090",
    )


@pytest.fixture
def traefik_service(rw_config: ServerConfig) -> TraefikService:
    return build_seeded_service(rw_config)


@pytest.fixture
def mcp_rw(rw_config: ServerConfig, traefik_service: TraefikService):
    mcp, _ = ServerBootstrap.build(config=rw_config, services={"traefik_service": traefik_service})
    return mcp


@pytest.fixture
def mcp_ro(ro_config: ServerConfig):
    svc = build_seeded_service(ro_config)
    mcp, _ = ServerBootstrap.build(config=ro_config, services={"traefik_service": svc})
    return mcp
