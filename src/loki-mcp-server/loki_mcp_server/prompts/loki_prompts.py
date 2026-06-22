"""Loki MCP prompts — guided workflows for common tasks.

Prompts: investigate_errors, check_health, analyze_log_structure,
         build_logql_query, explore_schema
"""

from typing import Any, Dict

from loki_mcp_server.prompts.base import BasePrompt


class LokiPrompts(BasePrompt):
    """Pre-built prompt workflows for common Loki operations."""

    def register(self, mcp_instance) -> None:  # type: ignore[no-untyped-def]
        """Register all prompts with the MCP instance."""

        # ──────────────────────────────────────────
        # Prompt 1: investigate_errors
        # ──────────────────────────────────────────
        @mcp_instance.prompt(
            name="investigate_errors",
            description="Step-by-step workflow to investigate error logs for a service",
        )
        async def investigate_errors(
            service_name: str,
            time_range: str = "1h",
        ) -> str:
            """Build a multi-step error investigation workflow."""
            return f"""## Investigate Errors for '{service_name}' (Last {time_range})

Follow these steps in order:

### Step 1: Discover available labels
Call `get_cluster_labels` to see what labels exist.

### Step 2: Find the service
Call `get_label_values` with label="app" to confirm '{service_name}' exists.
If not found, try label="service_name" or label="job".

### Step 3: Validate the selector
Call `get_active_series` with match='{{app="{service_name}"}}' to confirm
the selector matches active streams.

### Step 4: Detect log structure
Call `get_detected_fields` with query='{{app="{service_name}"}}' to discover
available fields (level, status_code, msg, etc.).

### Step 5: Check query cost
Call `get_query_stats` with query='{{app="{service_name}"}}' and
start='now-{time_range}' to estimate volume.

### Step 6: Fetch error logs
Call `execute_logql_query` with:
- query: '{{app="{service_name}"}} |= "error" | json'
- start: 'now-{time_range}'
- end: 'now'
- limit: 100

### Step 7: Quantify error rate
Call `execute_logql_instant` with:
- query: 'sum(rate({{app="{service_name}"}} |= "error" [5m]))'
- time: 'now'

Summarize your findings with error counts, common patterns, and recommendations.
"""

        # ──────────────────────────────────────────
        # Prompt 2: check_health
        # ──────────────────────────────────────────
        @mcp_instance.prompt(
            name="check_health",
            description="Quick health check for Loki and a service's log pipeline",
        )
        async def check_health(
            service_name: str = "all",
        ) -> str:
            """Build a health check workflow."""
            return f"""## Loki Health Check for '{service_name}'

### Step 1: System health
Read resource `loki://system/health` to verify Loki is reachable.

### Step 2: Label taxonomy
Call `get_cluster_labels` to see the current label landscape.

### Step 3: Service validation
Call `get_active_series` with match='{{app="{service_name}"}}' to verify
the service has active log streams.

### Step 4: Recent log volume
Call `get_query_stats` with query='{{app="{service_name}"}}' and
start='now-1h' to check recent throughput.

### Step 5: Latest logs
Call `execute_logql_query` with:
- query: '{{app="{service_name}"}}'
- start: 'now-15m'
- limit: 10

Report: Is Loki healthy? Is the service producing logs?
What's the current ingestion rate?
"""

        # ──────────────────────────────────────────
        # Prompt 3: analyze_log_structure
        # ──────────────────────────────────────────
        @mcp_instance.prompt(
            name="analyze_log_structure",
            description="Discover log format, fields, and patterns for a service",
        )
        async def analyze_log_structure(
            service_name: str,
        ) -> str:
            """Build a log structure analysis workflow."""
            return f"""## Analyze Log Structure for '{service_name}'

### Step 1: Validate the service exists
Call `get_active_series` with match='{{app="{service_name}"}}'.

### Step 2: Discover structured fields
Call `get_detected_fields` with query='{{app="{service_name}"}}'.
This reveals JSON/logfmt keys, their types, and the parser needed.

### Step 3: Discover patterns
Call `get_log_patterns` with query='{{app="{service_name}"}}'
and start='now-3h'. This shows recurring log shapes.

### Step 4: Sample raw logs
Call `execute_logql_query` with:
- query: '{{app="{service_name}"}}'
- start: 'now-15m'
- limit: 5

Summarize:
1. Log format (JSON, logfmt, plaintext, mixed)
2. Available fields and their types
3. Recommended parser pipeline (| json, | logfmt, | pattern)
4. Top structural patterns
"""

        # ──────────────────────────────────────────
        # Prompt 4: build_logql_query
        # ──────────────────────────────────────────
        @mcp_instance.prompt(
            name="build_logql_query",
            description="Guided query builder: discovers labels/fields then builds LogQL",
        )
        async def build_logql_query(
            intent: str,
        ) -> str:
            """Build a query construction workflow."""
            return f"""## Build LogQL Query for: "{intent}"

### Step 1: Understand the environment
Call `get_cluster_labels` to see available label dimensions.

### Step 2: Explore relevant labels
Based on the intent, call `get_label_values` for likely labels
(e.g., app, namespace, level, cluster).

### Step 3: Validate selector
Call `get_active_series` with your chosen selector to confirm
it matches real streams.

### Step 4: Discover fields
Call `get_detected_fields` with your selector to find
filterable fields inside log lines.

### Step 5: Read references
Read `loki://reference/logql` for syntax help.
Read `loki://reference/query-templates` for common patterns.

### Step 6: Preflight check
Call `get_query_stats` with your selector and time range.

### Step 7: Execute
Use `execute_logql_query` (for range data) or
`execute_logql_instant` (for scalar answers).

Construct the optimal LogQL query for: "{intent}"
"""

        # ──────────────────────────────────────────
        # Prompt 5: explore_schema
        # ──────────────────────────────────────────
        @mcp_instance.prompt(
            name="explore_schema",
            description="Full schema exploration: labels → values → cardinality → fields",
        )
        async def explore_schema() -> str:
            """Build a complete schema exploration workflow."""
            return """## Explore Loki Schema

### Step 1: Global label taxonomy
Call `get_cluster_labels` to discover all label names.

### Step 2: Drill into key labels
For the most important labels (app, namespace, env, cluster),
call `get_label_values` for each to see valid values.

### Step 3: Cardinality analysis
Pick a broad selector (e.g., '{namespace="production"}') and
call `get_active_series` to see:
- Total active streams
- Per-label cardinality
- High-cardinality warnings

### Step 4: Log structure
For a representative service, call `get_detected_fields` to
discover structured fields and their types.

### Step 5: Review governance
Read `loki://reference/label-governance` for naming conventions
and cardinality rules.

Provide a summary report:
1. Label taxonomy overview
2. Service inventory (unique app values)
3. Cardinality health (any warnings?)
4. Log format summary (JSON, logfmt, plain)
"""
