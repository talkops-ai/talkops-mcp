#!/bin/bash
set -e

export MCP_SERVER_NAME="${MCP_SERVER_NAME:-tempo-mcp-server}"
export MCP_SERVER_VERSION="${MCP_SERVER_VERSION:-0.2.1}"
export MCP_TRANSPORT="${MCP_TRANSPORT:-http}"
export MCP_HOST="${MCP_HOST:-0.0.0.0}"
export MCP_PORT="${MCP_PORT:-8768}"
export MCP_PATH="${MCP_PATH:-/mcp}"
export MCP_ALLOW_WRITE="${MCP_ALLOW_WRITE:-false}"
export MCP_LOG_LEVEL="${MCP_LOG_LEVEL:-INFO}"
export TEMPO_BASE_URL="${TEMPO_BASE_URL:-http://localhost:3200}"
export TEMPO_VERIFY_SSL="${TEMPO_VERIFY_SSL:-true}"
export TEMPO_BACKEND_ID="${TEMPO_BACKEND_ID:-default}"
export TEMPO_TYPE="${TEMPO_TYPE:-tempo}"
export K8S_ENABLED="${K8S_ENABLED:-false}"
# Auto-detect Kubernetes mode (in-cluster vs mounted kubeconfig) unless explicitly set
if [ -z "${K8S_IN_CLUSTER:-}" ]; then
    if [ -n "${KUBERNETES_SERVICE_HOST:-}" ]; then
        export K8S_IN_CLUSTER="true"
    else
        export K8S_IN_CLUSTER="false"
    fi
fi
if [ -f "/app/.kube/config" ]; then
    export KUBECONFIG="${KUBECONFIG:-/app/.kube/config}"
    export K8S_KUBECONFIG="${K8S_KUBECONFIG:-/app/.kube/config}"
fi

exec tempo-mcp-server "$@"
