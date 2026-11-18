"""Tool module initialization — v0.2.0 Execution Plane Architecture.

Registers up to 18 tools across selectable toolsets:
  discovery (5 read-only): loki_get_labels, loki_get_label_values, loki_get_series,
                           loki_get_log_patterns, loki_get_detected_fields
  query     (4 read-only): loki_get_query_stats, loki_query_instant,
                           loki_query_range, loki_query_a2ui
  analysis  (4 read-only): loki_summarize_service_logs, loki_compare_periods,
                           loki_correlate_trace_logs, loki_analyze_volume
  diagnostics (1 read-only): loki_get_diagnostics
  rules     (2 write-gated): loki_upsert_rule_group, loki_delete_rule_group
  governance (1 write-gated): loki_manage_delete_requests
  operator  (1 write-gated): loki_apply_operator_cr
"""

from typing import Any, Dict

from loki_mcp_server.tools.analysis.analysis_tools import AnalysisTools
from loki_mcp_server.tools.discovery.discovery_tools import DiscoveryTools
from loki_mcp_server.tools.execution.execution_tools import ExecutionTools
from loki_mcp_server.tools.governance.governance_tools import GovernanceAndOperatorTools
from loki_mcp_server.tools.registry import ToolRegistry
from loki_mcp_server.tools.rules.rules_tools import RulesAndDiagnosticsTools
from loki_mcp_server.tools.safety.safety_tools import SafetyTools
from loki_mcp_server.tools.structure.structure_tools import StructureTools


def initialize_tools(service_locator: Dict[str, Any]) -> ToolRegistry:
    """Create and populate the tool registry with all Loki MCP tools."""
    registry = ToolRegistry(service_locator)

    registry.register_tool(DiscoveryTools(service_locator))
    registry.register_tool(StructureTools(service_locator))
    registry.register_tool(SafetyTools(service_locator))
    registry.register_tool(ExecutionTools(service_locator))
    registry.register_tool(AnalysisTools(service_locator))
    registry.register_tool(RulesAndDiagnosticsTools(service_locator))
    registry.register_tool(GovernanceAndOperatorTools(service_locator))

    return registry
