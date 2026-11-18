#!/bin/bash
set -e

export MCP_SERVER_NAME="${MCP_SERVER_NAME:-traefik-mcp-server}"
export MCP_SERVER_VERSION="${MCP_SERVER_VERSION:-0.2.1}"
export MCP_TRANSPORT="${MCP_TRANSPORT:-stdio}"
export MCP_ALLOW_WRITE="${MCP_ALLOW_WRITE:-false}"
export MCP_DEBUG="${MCP_DEBUG:-false}"
export TRAEFIK_NAMESPACE="${TRAEFIK_NAMESPACE:-traefik}"
export TRAEFIK_OPERATION_TIMEOUT="${TRAEFIK_OPERATION_TIMEOUT:-120}"
export K8S_CONTEXT="${K8S_CONTEXT:-}"
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

exec traefik-mcp-server "$@"
