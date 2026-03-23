#!/bin/bash
set -e

# Set default environment variables if not already set
export MCP_SERVER_NAME="${MCP_SERVER_NAME:-traefik-mcp-server}"
export MCP_SERVER_VERSION="${MCP_SERVER_VERSION:-0.1.0}"
export MCP_TRANSPORT="${MCP_TRANSPORT:-http}"
export MCP_HOST="${MCP_HOST:-0.0.0.0}"
export MCP_PORT="${MCP_PORT:-8769}"
export MCP_PATH="${MCP_PATH:-/mcp}"
export MCP_ALLOW_WRITE="${MCP_ALLOW_WRITE:-true}"
export MCP_DEBUG="${MCP_DEBUG:-false}"
export TRAEFIK_OPERATION_TIMEOUT="${TRAEFIK_OPERATION_TIMEOUT:-120}"
export K8S_KUBECONFIG="${K8S_KUBECONFIG:-/app/.kube/config}"
export K8S_CONTEXT="${K8S_CONTEXT:-}"
export K8S_IN_CLUSTER="${K8S_IN_CLUSTER:-false}"

# Execute the server command with any arguments passed
exec traefik-mcp-server "$@"
