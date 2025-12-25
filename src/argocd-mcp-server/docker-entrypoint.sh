#!/bin/bash
set -e

# ArgoCD MCP Server Docker Entrypoint Script
# This script sets default environment variables that can be overridden via docker run -e flags

# ==================== MCP Server Configuration ====================
export MCP_SERVER_NAME="${MCP_SERVER_NAME:-argocd-mcp-server}"
export MCP_SERVER_VERSION="${MCP_SERVER_VERSION:-0.1.0}"
export MCP_TRANSPORT="${MCP_TRANSPORT:-http}"
export MCP_HOST="${MCP_HOST:-0.0.0.0}"
export MCP_PORT="${MCP_PORT:-8765}"
export MCP_PATH="${MCP_PATH:-/sse}"
export MCP_ALLOW_WRITE="${MCP_ALLOW_WRITE:-false}"  # Default to read-only for safety
export MCP_HTTP_TIMEOUT="${MCP_HTTP_TIMEOUT:-300}"
export MCP_HTTP_KEEPALIVE_TIMEOUT="${MCP_HTTP_KEEPALIVE_TIMEOUT:-5}"
export MCP_HTTP_CONNECT_TIMEOUT="${MCP_HTTP_CONNECT_TIMEOUT:-60}"
export MCP_LOG_LEVEL="${MCP_LOG_LEVEL:-INFO}"
export MCP_LOG_FORMAT="${MCP_LOG_FORMAT:-json}"

# ==================== ArgoCD Configuration ====================
export ARGOCD_SERVER_URL="${ARGOCD_SERVER_URL:-https://argocd-server.argocd.svc:443}"
export ARGOCD_AUTH_TOKEN="${ARGOCD_AUTH_TOKEN:-}"  # Must be provided by user
export ARGOCD_INSECURE="${ARGOCD_INSECURE:-false}"
export ARGOCD_TIMEOUT="${ARGOCD_TIMEOUT:-300}"

# ==================== Git Credentials (for repository onboarding) ====================
export GIT_USERNAME="${GIT_USERNAME:-}"  # Optional for HTTPS repos
export GIT_PASSWORD="${GIT_PASSWORD:-}"  # GitHub token for HTTPS repos
export SSH_PRIVATE_KEY_PATH="${SSH_PRIVATE_KEY_PATH:-/app/.ssh/id_rsa}"  # SSH key path

# ==================== Pre-flight Checks ====================
echo "🚀 Starting ArgoCD MCP Server"
echo "📋 Configuration:"
echo "   Server: ${MCP_SERVER_NAME} v${MCP_SERVER_VERSION}"
echo "   Transport: ${MCP_TRANSPORT}"
echo "   Listen: ${MCP_HOST}:${MCP_PORT}${MCP_PATH}"
echo "   Write Mode: ${MCP_ALLOW_WRITE}"
echo "   Log Level: ${MCP_LOG_LEVEL}"
echo ""
echo "🔗 ArgoCD Configuration:"
echo "   Server URL: ${ARGOCD_SERVER_URL}"
echo "   Auth Token: ${ARGOCD_AUTH_TOKEN:+***SET***}"
echo "   Insecure: ${ARGOCD_INSECURE}"
echo ""

# Validate required configuration
if [ -z "$ARGOCD_AUTH_TOKEN" ]; then
    echo "⚠️  WARNING: ARGOCD_AUTH_TOKEN is not set. The server may not function properly."
    echo "   To set it, use: docker run -e ARGOCD_AUTH_TOKEN=your-token ..."
    echo ""
fi

# Execute the argocd-mcp-server command with any arguments passed
echo "✅ Starting server..."
echo ""
exec argocd-mcp-server "$@"
