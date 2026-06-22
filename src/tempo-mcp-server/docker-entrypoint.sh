#!/bin/bash
set -e

# Set default environment variables if not already set
export MCP_SERVER_NAME="${MCP_SERVER_NAME:-tempo-mcp-server}"
export MCP_SERVER_VERSION="${MCP_SERVER_VERSION:-0.1.0}"
export MCP_TRANSPORT="${MCP_TRANSPORT:-http}"
export MCP_HOST="${MCP_HOST:-0.0.0.0}"
export MCP_PORT="${MCP_PORT:-8768}"
export MCP_PATH="${MCP_PATH:-/mcp}"
export MCP_LOG_LEVEL="${MCP_LOG_LEVEL:-INFO}"

# Tempo specific
export TEMPO_BASE_URL="${TEMPO_BASE_URL:-http://localhost:3200}"
export TEMPO_VERIFY_SSL="${TEMPO_VERIFY_SSL:-true}"
export TEMPO_BACKEND_ID="${TEMPO_BACKEND_ID:-default}"
export TEMPO_TYPE="${TEMPO_TYPE:-tempo}"

# Kubernetes
export K8S_IN_CLUSTER="${K8S_IN_CLUSTER:-true}"
export K8S_ENABLED="${K8S_ENABLED:-true}"

# Execute the server command with any arguments passed
exec tempo-mcp-server "$@"
