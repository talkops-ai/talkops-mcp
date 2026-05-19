"""Promtool validation tools.

Provides granular tools for validating rule groups and
running rule unit tests via promtool.
"""

from typing import Any, Dict, Optional

import yaml
from mcp.types import ToolAnnotations
from fastmcp import Context
from pydantic import Field

from prometheus_mcp_server.exceptions import PrometheusOperationError
from prometheus_mcp_server.tools.base import BaseTool
from prometheus_mcp_server.utils.promtool_runner import check_rules, test_rules


class PromtoolTools(BaseTool):
    """Promtool-based validation and testing tools."""

    def register(self, mcp_instance) -> None:  # type: ignore[no-untyped-def]

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Check Rule Group",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=False,
            )
        )
        async def prom_check_rule_group(
            rules_yaml: str = Field(
                ..., description="YAML content containing rule groups to validate"
            ),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Validate rule group syntax via promtool check rules.

            Use this before applying rule groups to catch syntax errors,
            invalid expressions, and best-practice violations. Read-only.

            Returns:
            - {\"valid\": bool, \"errors\": [str], \"warnings\": [str],
               \"rules_checked\": int, \"promtool_available\": bool}

            When NOT to use: For running rule unit tests, use
            prom_run_rule_tests instead.

            Prerequisites:
            - promtool binary must be in PATH (optional — graceful fallback
              with error message if not available).

            Common errors:
            - promtool not available: Install from https://prometheus.io/download/
            - Invalid YAML: Ensure the input is valid YAML with rule groups.
            """
            try:
                result = await check_rules(rules_yaml)
                return result
            except Exception as e:
                raise PrometheusOperationError(f"Rule check failed: {e}")

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Run Rule Unit Tests",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=False,
            )
        )
        async def prom_run_rule_tests(
            rules_yaml: str = Field(
                ..., description="YAML content containing rule groups to test"
            ),
            test_yaml: str = Field(
                ..., description="YAML content containing test scenarios (promtool test rules format)"
            ),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Run promtool test rules with synthetic test scenarios.

            Use this to verify that alerting rules fire correctly under
            specific conditions. Read-only — no state mutation.

            Returns:
            - {\"passed\": bool, \"total_tests\": int, \"passed_tests\": int,
               \"failed_tests\": int, \"errors\": [str], \"output\": str,
               \"promtool_available\": bool}

            When NOT to use: For syntax-only validation, use
            prom_check_rule_group instead.

            Prerequisites:
            - promtool binary must be in PATH (optional — graceful fallback).

            Common errors:
            - promtool not available: Install from https://prometheus.io/download/
            - Invalid test format: Follow promtool test rules YAML format.
            """
            try:
                result = await test_rules(rules_yaml, test_yaml)
                return result
            except Exception as e:
                raise PrometheusOperationError(f"Rule test failed: {e}")
