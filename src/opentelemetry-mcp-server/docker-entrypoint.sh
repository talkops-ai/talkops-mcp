#!/bin/bash
set -e

# Set default environment variables if not already set
export MCP_SERVER_NAME="${MCP_SERVER_NAME:-opentelemetry-mcp-server}"
export MCP_SERVER_VERSION="${MCP_SERVER_VERSION:-0.1.0}"
export MCP_TRANSPORT="${MCP_TRANSPORT:-http}"
export MCP_HOST="${MCP_HOST:-0.0.0.0}"
export MCP_PORT="${MCP_PORT:-8771}"
export MCP_PATH="${MCP_PATH:-/mcp}"
export MCP_LOG_LEVEL="${MCP_LOG_LEVEL:-INFO}"
export MCP_LOG_FORMAT="${MCP_LOG_FORMAT:-json}"

# Timeout Settings
export MCP_HTTP_TIMEOUT="${MCP_HTTP_TIMEOUT:-300}"
export MCP_HTTP_KEEPALIVE_TIMEOUT="${MCP_HTTP_KEEPALIVE_TIMEOUT:-5}"
export MCP_HTTP_CONNECT_TIMEOUT="${MCP_HTTP_CONNECT_TIMEOUT:-60}"

# Kubernetes
export K8S_IN_CLUSTER="${K8S_IN_CLUSTER:-true}"
export K8S_ENABLED="${K8S_ENABLED:-true}"

# OTel Operator CRD Settings
export OTEL_CRD_GROUP="${OTEL_CRD_GROUP:-opentelemetry.io}"
export OTEL_CRD_API_VERSION="${OTEL_CRD_API_VERSION:-v1beta1}"
export OTEL_INSTRUMENTATION_API_VERSION="${OTEL_INSTRUMENTATION_API_VERSION:-v1alpha1}"
export OTEL_COLLECTOR_PLURAL="${OTEL_COLLECTOR_PLURAL:-opentelemetrycollectors}"
export OTEL_INSTRUMENTATION_PLURAL="${OTEL_INSTRUMENTATION_PLURAL:-instrumentations}"

# Target Allocator Settings
export OTEL_TA_SERVICE_DISCOVERY="${OTEL_TA_SERVICE_DISCOVERY:-true}"
export OTEL_TA_DEFAULT_PORT="${OTEL_TA_DEFAULT_PORT:-8080}"

# Prometheus Integration
export PROMETHEUS_BASE_URL="${PROMETHEUS_BASE_URL:-}"
export PROMETHEUS_TIMEOUT="${PROMETHEUS_TIMEOUT:-30}"
export PROMETHEUS_VERIFY_SSL="${PROMETHEUS_VERIFY_SSL:-true}"

# Execute the server command with any arguments passed
exec opentelemetry-mcp-server "$@"
