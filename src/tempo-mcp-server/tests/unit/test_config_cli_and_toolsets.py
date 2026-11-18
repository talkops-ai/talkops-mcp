"""Unit tests for CLI argument parsing, toolset filtering, and write-gate config."""

import os
from unittest.mock import patch

from tempo_mcp_server.config import Config, ServerConfig, VALID_TOOLSETS


class TestConfigCliAndToolsets:
    """Verify CLI flag parsing and toolset/write-gate registration checks."""

    def test_valid_toolsets_constant(self):
        assert {
            "search",
            "metrics",
            "diagnostics",
            "overrides",
            "operator",
        }.issubset(VALID_TOOLSETS)

    def test_default_config_is_read_only_and_all_toolsets(self):
        with patch.dict(os.environ, {}, clear=True):
            cfg = Config.from_cli_and_env([])
            assert cfg.allow_write is False
            assert cfg.toolsets == ["all"]
            for ts in ("search", "metrics", "diagnostics"):
                assert cfg.should_register(ts, is_write=False) is True

    def test_cli_allow_write_and_toolset_filtering(self):
        with patch.dict(os.environ, {}, clear=True):
            cfg = Config.from_cli_and_env(
                ["--transport", "stdio", "--allow-write", "--toolsets", "search,metrics"]
            )
            assert cfg.transport == "stdio"
            assert cfg.allow_write is True
            assert cfg.toolsets == ["search", "metrics"]

    def test_cli_read_only_overrides_env_allow_write(self):
        with patch.dict(os.environ, {"MCP_ALLOW_WRITE": "true"}, clear=True):
            cfg = Config.from_cli_and_env(["--read-only"])
            assert cfg.allow_write is False

    def test_should_register_respects_toolset_and_write_flag(self):
        ro_cfg = ServerConfig(allow_write=False, toolsets=["search", "overrides"])
        assert ro_cfg.should_register("search", is_write=False) is True
        assert ro_cfg.should_register("metrics", is_write=False) is False
        assert ro_cfg.should_register("overrides", is_write=True) is False

        rw_cfg = ServerConfig(allow_write=True, toolsets=["search", "overrides"])
        assert rw_cfg.should_register("overrides", is_write=True) is True
        assert rw_cfg.should_register("operator", is_write=True) is False
