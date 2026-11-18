#!/bin/bash
set -e

export MCP_SERVER_NAME="${MCP_SERVER_NAME:-loki-mcp-server}"
export MCP_SERVER_VERSION="${MCP_SERVER_VERSION:-0.2.1}"
export MCP_TRANSPORT="${MCP_TRANSPORT:-http}"
export MCP_HOST="${MCP_HOST:-0.0.0.0}"
export MCP_PORT="${MCP_PORT:-8770}"
export MCP_PATH="${MCP_PATH:-/mcp}"
export MCP_ALLOW_WRITE="${MCP_ALLOW_WRITE:-false}"
export MCP_LOG_LEVEL="${MCP_LOG_LEVEL:-INFO}"
export LOKI_URL="${LOKI_URL:-http://localhost:3100}"
export LOKI_TIMEOUT="${LOKI_TIMEOUT:-30}"
export LOKI_VERIFY_SSL="${LOKI_VERIFY_SSL:-true}"
export LOKI_MAX_QUERY_BYTES="${LOKI_MAX_QUERY_BYTES:-5000000000}"
export LOKI_MAX_TIME_WINDOW_HOURS="${LOKI_MAX_TIME_WINDOW_HOURS:-336}"
export LOKI_MAX_LOG_LIMIT="${LOKI_MAX_LOG_LIMIT:-5000}"
export LOKI_HIGH_CARDINALITY_THRESHOLD="${LOKI_HIGH_CARDINALITY_THRESHOLD:-10000}"
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

exec loki-mcp-server "$@"
