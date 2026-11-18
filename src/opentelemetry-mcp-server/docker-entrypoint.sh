#!/bin/bash
set -e

export MCP_SERVER_NAME="${MCP_SERVER_NAME:-opentelemetry-mcp-server}"
export MCP_SERVER_VERSION="${MCP_SERVER_VERSION:-0.2.1}"
export MCP_TRANSPORT="${MCP_TRANSPORT:-http}"
export MCP_HOST="${MCP_HOST:-0.0.0.0}"
export MCP_PORT="${MCP_PORT:-8771}"
export MCP_PATH="${MCP_PATH:-/mcp}"
export MCP_ALLOW_WRITE="${MCP_ALLOW_WRITE:-false}"
export MCP_LOG_LEVEL="${MCP_LOG_LEVEL:-INFO}"
export MCP_LOG_FORMAT="${MCP_LOG_FORMAT:-json}"
export MCP_HTTP_TIMEOUT="${MCP_HTTP_TIMEOUT:-300}"
export MCP_HTTP_KEEPALIVE_TIMEOUT="${MCP_HTTP_KEEPALIVE_TIMEOUT:-5}"
export MCP_HTTP_CONNECT_TIMEOUT="${MCP_HTTP_CONNECT_TIMEOUT:-60}"
export K8S_ENABLED="${K8S_ENABLED:-true}"
export OTEL_CRD_GROUP="${OTEL_CRD_GROUP:-opentelemetry.io}"
export OTEL_CRD_API_VERSION="${OTEL_CRD_API_VERSION:-v1beta1}"
export OTEL_INSTRUMENTATION_API_VERSION="${OTEL_INSTRUMENTATION_API_VERSION:-v1alpha1}"
export OTEL_COLLECTOR_PLURAL="${OTEL_COLLECTOR_PLURAL:-opentelemetrycollectors}"
export OTEL_INSTRUMENTATION_PLURAL="${OTEL_INSTRUMENTATION_PLURAL:-instrumentations}"
export OTEL_TA_SERVICE_DISCOVERY="${OTEL_TA_SERVICE_DISCOVERY:-true}"
export OTEL_TA_DEFAULT_PORT="${OTEL_TA_DEFAULT_PORT:-8080}"
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

exec opentelemetry-mcp-server "$@"
