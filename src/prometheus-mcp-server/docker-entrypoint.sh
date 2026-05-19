#!/bin/bash
set -e

# Set default environment variables if not already set
export MCP_SERVER_NAME="${MCP_SERVER_NAME:-prometheus-mcp-server}"
export MCP_SERVER_VERSION="${MCP_SERVER_VERSION:-0.1.0}"
export MCP_TRANSPORT="${MCP_TRANSPORT:-http}"
export MCP_HOST="${MCP_HOST:-0.0.0.0}"
export MCP_PORT="${MCP_PORT:-8767}"
export MCP_PATH="${MCP_PATH:-/mcp}"
export MCP_LOG_LEVEL="${MCP_LOG_LEVEL:-INFO}"

# Prometheus specific
export PROMETHEUS_BASE_URL="${PROMETHEUS_BASE_URL:-http://localhost:9090}"
export PROMETHEUS_VERIFY_SSL="${PROMETHEUS_VERIFY_SSL:-true}"
export PROMETHEUS_BACKEND_ID="${PROMETHEUS_BACKEND_ID:-default}"
export PROMETHEUS_TYPE="${PROMETHEUS_TYPE:-prometheus}"

# Kubernetes
export K8S_IN_CLUSTER="${K8S_IN_CLUSTER:-true}"
export K8S_ENABLED="${K8S_ENABLED:-true}"

# Execute the server command with any arguments passed
exec prometheus-mcp-server "$@"
