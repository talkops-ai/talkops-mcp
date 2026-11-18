#!/bin/bash
set -e

export MCP_SERVER_NAME="${MCP_SERVER_NAME:-argocd-mcp-server}"
export MCP_SERVER_VERSION="${MCP_SERVER_VERSION:-0.4.1}"
export MCP_TRANSPORT="${MCP_TRANSPORT:-http}"
export MCP_HOST="${MCP_HOST:-0.0.0.0}"
export MCP_PORT="${MCP_PORT:-8770}"
export MCP_PATH="${MCP_PATH:-/mcp}"
export MCP_ALLOW_WRITE="${MCP_ALLOW_WRITE:-false}"
export MCP_HTTP_TIMEOUT="${MCP_HTTP_TIMEOUT:-300}"
export MCP_HTTP_KEEPALIVE_TIMEOUT="${MCP_HTTP_KEEPALIVE_TIMEOUT:-5}"
export MCP_HTTP_CONNECT_TIMEOUT="${MCP_HTTP_CONNECT_TIMEOUT:-60}"
export MCP_LOG_LEVEL="${MCP_LOG_LEVEL:-INFO}"
export MCP_LOG_FORMAT="${MCP_LOG_FORMAT:-json}"
export ARGOCD_SERVER_URL="${ARGOCD_SERVER_URL:-https://argocd-server.argocd.svc:443}"
export ARGOCD_AUTH_TOKEN="${ARGOCD_AUTH_TOKEN:-}"
export ARGOCD_INSECURE="${ARGOCD_INSECURE:-false}"
export ARGOCD_TIMEOUT="${ARGOCD_TIMEOUT:-300}"
export GIT_USERNAME="${GIT_USERNAME:-}"
export GIT_PASSWORD="${GIT_PASSWORD:-}"
export SSH_PRIVATE_KEY_PATH="${SSH_PRIVATE_KEY_PATH:-/app/.ssh/id_rsa}"

if [ "${MCP_TRANSPORT}" != "stdio" ] && [ -z "${ARGOCD_AUTH_TOKEN}" ]; then
    echo "WARNING: ARGOCD_AUTH_TOKEN is not set. Pass -e ARGOCD_AUTH_TOKEN=<token>." >&2
fi

exec argocd-mcp-server "$@"
