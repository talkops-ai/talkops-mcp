"""Root test configuration and shared fixtures.

Following the TalkOps MCP Server Testing Guide standard:
- Fixtures load from external JSON files
- HTTP mocking via respx
- Composable fixtures for unit and integration tests
"""

import json
import os
import re
from pathlib import Path
from typing import Any, Dict
from unittest.mock import patch

import httpx
import pytest
import respx

# ──────────────────────────────────────────────
# Fixture Loader
# ──────────────────────────────────────────────

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "loki"


def _load_fixture(name: str) -> Dict[str, Any]:
    """Load a JSON fixture file.

    Args:
        name: Filename relative to tests/fixtures/loki/

    Returns:
        Parsed JSON dict.
    """
    with open(FIXTURES_DIR / name, encoding="utf-8") as f:
        return json.load(f)


# ──────────────────────────────────────────────
# Text extraction helpers
# ──────────────────────────────────────────────


def get_text(result) -> str:
    """Extract text from either call_tool or read_resource result.

    Per the test guide §9:
    - call_tool returns CallToolResult → result.content[0].text
    - read_resource returns list → result[0].text
    """
    if isinstance(result, list):
        return result[0].text if result else ""
    return result.content[0].text if result.content else str(result)


# ──────────────────────────────────────────────
# Shared Fixtures
# ──────────────────────────────────────────────

LOKI_BASE_URL = "http://test-loki:3100"


@pytest.fixture
def mock_loki_http():
    """Stub all Loki HTTP endpoints with respx.

    Per the test guide §11: mock at the HTTP layer, not internal methods.
    Uses assert_all_called=False to avoid flaky tests from unused routes.
    """
    with respx.mock(assert_all_called=False) as mock:
        base = LOKI_BASE_URL

        # Health / readiness
        mock.get(f"{base}/ready").mock(
            return_value=httpx.Response(200, text="ready")
        )

        # Labels
        mock.get(f"{base}/loki/api/v1/labels").mock(
            return_value=httpx.Response(
                200, json=_load_fixture("labels_response.json")
            )
        )

        # Label values (dynamic path)
        mock.get(
            url__regex=rf"{re.escape(base)}/loki/api/v1/label/.+/values"
        ).mock(
            return_value=httpx.Response(
                200, json=_load_fixture("label_values_response.json")
            )
        )

        # Series
        mock.get(f"{base}/loki/api/v1/series").mock(
            return_value=httpx.Response(
                200, json=_load_fixture("series_response.json")
            )
        )

        # Query range (streams) — default response
        mock.get(f"{base}/loki/api/v1/query_range").mock(
            return_value=httpx.Response(
                200, json=_load_fixture("query_range_streams.json")
            )
        )

        # Query (instant)
        mock.get(f"{base}/loki/api/v1/query").mock(
            return_value=httpx.Response(
                200, json=_load_fixture("query_range_streams.json")
            )
        )

        # Index stats
        mock.get(f"{base}/loki/api/v1/index/stats").mock(
            return_value=httpx.Response(
                200, json=_load_fixture("index_stats_response.json")
            )
        )

        # Patterns
        mock.get(f"{base}/loki/api/v1/patterns").mock(
            return_value=httpx.Response(
                200, json=_load_fixture("patterns_response.json")
            )
        )

        # Detected fields
        mock.get(f"{base}/loki/api/v1/detected_fields").mock(
            return_value=httpx.Response(
                200, json=_load_fixture("detected_fields_response.json")
            )
        )

        yield mock


@pytest.fixture
async def mcp_client(mock_loki_http):
    """Bootstrapped FastMCP Client with all Loki endpoints stubbed.

    Per the test guide §6: integration tests go through
    ServerBootstrap.initialize() with mocked HTTP.

    Uses FastMCP v3 in-memory transport:
    Client(transport=mcp_server_instance)
    """
    from fastmcp import Client

    env = {
        "LOKI_URL": LOKI_BASE_URL,
        "LOKI_TIMEOUT": "5",
        "LOKI_VERIFY_SSL": "false",
        "MCP_TRANSPORT": "stdio",
        "MCP_LOG_LEVEL": "WARNING",
    }
    with patch.dict(os.environ, env, clear=False):
        from loki_mcp_server.server.bootstrap import ServerBootstrap

        mcp, _, _ = ServerBootstrap.initialize()
        async with Client(transport=mcp) as client:
            yield client
