#!/bin/bash
set -e

# Set default environment variables if not already set
export MCP_SERVER_NAME="${MCP_SERVER_NAME:-loki-mcp-server}"
export MCP_SERVER_VERSION="${MCP_SERVER_VERSION:-0.1.0}"
export MCP_TRANSPORT="${MCP_TRANSPORT:-http}"
export MCP_HOST="${MCP_HOST:-0.0.0.0}"
export MCP_PORT="${MCP_PORT:-8770}"
export MCP_PATH="${MCP_PATH:-/mcp}"
export MCP_LOG_LEVEL="${MCP_LOG_LEVEL:-INFO}"

# Loki specific
export LOKI_URL="${LOKI_URL:-http://localhost:3100}"
export LOKI_TIMEOUT="${LOKI_TIMEOUT:-30}"
export LOKI_VERIFY_SSL="${LOKI_VERIFY_SSL:-true}"
export LOKI_ORG_ID="${LOKI_ORG_ID:-}"
export LOKI_AUTH_TOKEN="${LOKI_AUTH_TOKEN:-}"
export LOKI_BASIC_AUTH_USER="${LOKI_BASIC_AUTH_USER:-}"
export LOKI_BASIC_AUTH_PASSWORD="${LOKI_BASIC_AUTH_PASSWORD:-}"

# Guardrails
export LOKI_MAX_QUERY_BYTES="${LOKI_MAX_QUERY_BYTES:-5000000000}"
export LOKI_MAX_TIME_WINDOW_HOURS="${LOKI_MAX_TIME_WINDOW_HOURS:-336}"
export LOKI_MAX_LOG_LIMIT="${LOKI_MAX_LOG_LIMIT:-5000}"
export LOKI_HIGH_CARDINALITY_THRESHOLD="${LOKI_HIGH_CARDINALITY_THRESHOLD:-10000}"

# Execute the server command with any arguments passed
exec loki-mcp-server "$@"
