#!/bin/bash
set -e

# Set default environment variables if not already set
export MCP_SERVER_NAME="${MCP_SERVER_NAME:-alertmanager-mcp-server}"
export MCP_SERVER_VERSION="${MCP_SERVER_VERSION:-0.1.0}"
export MCP_TRANSPORT="${MCP_TRANSPORT:-http}"
export MCP_HOST="${MCP_HOST:-0.0.0.0}"
export MCP_PORT="${MCP_PORT:-8769}"
export MCP_PATH="${MCP_PATH:-/mcp}"
export MCP_LOG_LEVEL="${MCP_LOG_LEVEL:-INFO}"

# Alertmanager specific
export ALERTMANAGER_BASE_URL="${ALERTMANAGER_BASE_URL:-http://localhost:9093}"
export ALERTMANAGER_VERIFY_SSL="${ALERTMANAGER_VERIFY_SSL:-true}"
export ALERTMANAGER_BACKEND_ID="${ALERTMANAGER_BACKEND_ID:-default}"

# Silence safety guardrails
export AM_MAX_SILENCE_MINUTES="${AM_MAX_SILENCE_MINUTES:-1440}"
export AM_SILENCE_WARNING_THRESHOLD="${AM_SILENCE_WARNING_THRESHOLD:-50}"

# Execute the server command with any arguments passed
exec alertmanager-mcp-server "$@"
