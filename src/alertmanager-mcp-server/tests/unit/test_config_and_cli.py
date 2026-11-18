"""Unit tests for `config.py`, `main.py`, and `bootstrap.py`."""

from __future__ import annotations

import json
import os
from unittest.mock import MagicMock, patch
import pytest

from alertmanager_mcp_server.config import BackendConfig, Config, ServerConfig
from alertmanager_mcp_server.main import (
    apply_cli_overrides,
    build_arg_parser,
    main,
)
from alertmanager_mcp_server.server.bootstrap import ServerBootstrap


class TestConfigAndValidation:
    def test_default_config_is_read_only_on_port_8769(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            cfg = Config.from_env()
            assert cfg.name == "alertmanager-mcp-server"
            assert cfg.version == "0.2.1"
            assert cfg.port == 8769
            assert cfg.allow_write is False
            assert cfg.toolsets == ["all"]
            assert len(cfg.backends) == 1
            assert cfg.backends[0].id == "default"

    def test_fails_fast_on_malformed_backends_json(self) -> None:
        with patch.dict(
            os.environ, {"ALERTMANAGER_BACKENDS": "{bad json"}, clear=True
        ):
            with pytest.raises(ValueError, match="Malformed JSON"):
                Config.from_env()

    def test_fails_fast_on_duplicate_backend_ids_or_multiple_defaults(self) -> None:
        dup_backends = [
            {"id": "prod", "base_url": "http://am1:9093"},
            {"id": "prod", "base_url": "http://am2:9093"},
        ]
        with patch.dict(
            os.environ,
            {"ALERTMANAGER_BACKENDS": json.dumps(dup_backends)},
            clear=True,
        ):
            with pytest.raises(ValueError, match="Duplicate Alertmanager backend ID"):
                Config.from_env()

        multi_defaults = [
            {"id": "am1", "base_url": "http://am1:9093", "is_default": True},
            {"id": "am2", "base_url": "http://am2:9093", "is_default": True},
        ]
        with patch.dict(
            os.environ,
            {"ALERTMANAGER_BACKENDS": json.dumps(multi_defaults)},
            clear=True,
        ):
            with pytest.raises(ValueError, match="Multiple backends"):
                Config.from_env()

    def test_backend_path_prefix_and_basic_auth(self) -> None:
        with patch.dict(os.environ, {"AM_PASS": "secret123"}, clear=True):
            b = BackendConfig(
                id="proxied",
                base_url="https://monitoring.example.com/",
                path_prefix="/alertmanager/",
                basic_auth_username="admin",
                basic_auth_password_env="AM_PASS",
                headers={"X-Scope-OrgID": "tenant-a"},
            )
            assert b.api_base_url == "https://monitoring.example.com/alertmanager"
            assert b.resolve_basic_auth() == ("admin", "secret123")
            assert b.build_request_headers()["X-Scope-OrgID"] == "tenant-a"


class TestCLIAndBootstrap:
    def test_cli_flags_override_config(self) -> None:
        parser = build_arg_parser()
        args = parser.parse_args(
            [
                "--transport=http",
                "--host=127.0.0.1",
                "--port=9999",
                "--path=/custom",
                "--toolsets=triage,routing",
                "--allow-write",
            ]
        )
        cfg = ServerConfig()
        apply_cli_overrides(cfg, args)
        assert cfg.transport == "http"
        assert cfg.host == "127.0.0.1"
        assert cfg.port == 9999
        assert cfg.path == "/custom"
        assert cfg.toolsets == ["triage", "routing"]
        assert cfg.allow_write is True
        assert cfg.is_toolset_enabled("triage") is True
        assert cfg.is_toolset_enabled("silences") is False

    def test_main_invokes_bootstrap_and_run(self) -> None:
        mock_mcp = MagicMock()
        cfg = ServerConfig(transport="stdio")
        with patch.object(
            ServerBootstrap,
            "initialize",
            return_value=(mock_mcp, cfg, MagicMock()),
        ):
            main([])
            mock_mcp.run.assert_called_once_with()
