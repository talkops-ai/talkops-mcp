#!/bin/bash
set -e

export MCP_SERVER_NAME="${MCP_SERVER_NAME:-prometheus-mcp-server}"
export MCP_SERVER_VERSION="${MCP_SERVER_VERSION:-0.2.1}"
export MCP_TRANSPORT="${MCP_TRANSPORT:-http}"
export MCP_HOST="${MCP_HOST:-0.0.0.0}"
export MCP_PORT="${MCP_PORT:-8767}"
export MCP_PATH="${MCP_PATH:-/mcp}"
export MCP_LOG_LEVEL="${MCP_LOG_LEVEL:-INFO}"
export PROMETHEUS_BASE_URL="${PROMETHEUS_BASE_URL:-http://localhost:9090}"
export PROMETHEUS_VERIFY_SSL="${PROMETHEUS_VERIFY_SSL:-true}"
export PROMETHEUS_BACKEND_ID="${PROMETHEUS_BACKEND_ID:-default}"
export PROMETHEUS_TYPE="${PROMETHEUS_TYPE:-prometheus}"
export K8S_ENABLED="${K8S_ENABLED:-true}"
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

exec prometheus-mcp-server "$@"
