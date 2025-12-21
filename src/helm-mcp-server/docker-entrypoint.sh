#!/bin/bash
set -e

# Set default environment variables if not already set
# These can be overridden via docker run -e flags
export MCP_SERVER_NAME="${MCP_SERVER_NAME:-helm-mcp-server}"
export MCP_SERVER_VERSION="${MCP_SERVER_VERSION:-0.2.0}"
export MCP_TRANSPORT="${MCP_TRANSPORT:-http}"
export MCP_HOST="${MCP_HOST:-0.0.0.0}"
export MCP_PORT="${MCP_PORT:-8765}"
export MCP_PATH="${MCP_PATH:-/sse}"
export MCP_ALLOW_WRITE="${MCP_ALLOW_WRITE:-true}"
export MCP_HTTP_TIMEOUT="${MCP_HTTP_TIMEOUT:-300}"
export MCP_HTTP_KEEPALIVE_TIMEOUT="${MCP_HTTP_KEEPALIVE_TIMEOUT:-5}"
export MCP_HTTP_CONNECT_TIMEOUT="${MCP_HTTP_CONNECT_TIMEOUT:-60}"
export MCP_LOG_LEVEL="${MCP_LOG_LEVEL:-INFO}"
export MCP_LOG_FORMAT="${MCP_LOG_FORMAT:-json}"
export HELM_TIMEOUT="${HELM_TIMEOUT:-300}"
export K8S_TIMEOUT="${K8S_TIMEOUT:-30}"
export KUBECONFIG="${KUBECONFIG:-/app/.kube/config}"

# Execute the helm-mcp-server command with any arguments passed
exec helm-mcp-server "$@"
