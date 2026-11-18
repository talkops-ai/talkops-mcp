#!/bin/bash
set -e

export MCP_SERVER_NAME="${MCP_SERVER_NAME:-kargo-mcp-server}"
export MCP_SERVER_VERSION="${MCP_SERVER_VERSION:-0.2.1}"
export MCP_TRANSPORT="${MCP_TRANSPORT:-http}"
export MCP_HOST="${MCP_HOST:-0.0.0.0}"
export MCP_PORT="${MCP_PORT:-8766}"
export MCP_PATH="${MCP_PATH:-/mcp}"
export MCP_ALLOW_WRITE="${MCP_ALLOW_WRITE:-false}"
export MCP_DEBUG="${MCP_DEBUG:-false}"
export KARGO_BASE_URL="${KARGO_BASE_URL:-http://localhost:8080}"
export KARGO_AUTH_MODE="${KARGO_AUTH_MODE:-admin}"
export KARGO_VERIFY_SSL="${KARGO_VERIFY_SSL:-true}"
export KARGO_TIMEOUT="${KARGO_TIMEOUT:-30}"

exec kargo-mcp-server "$@"
