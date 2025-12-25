# Use Python 3.12 slim as base image
FROM python:3.12-slim AS uv

# Install the project into `/app`
WORKDIR /app

# Enable bytecode compilation
ENV UV_COMPILE_BYTECODE=1

# Copy from the cache instead of linking since it's a mounted volume
ENV UV_LINK_MODE=copy

# Prefer the system python
ENV UV_PYTHON_PREFERENCE=only-system

# Run without updating the uv.lock file like running with `--frozen`
ENV UV_FROZEN=true

# Copy the required files first
COPY pyproject.toml uv.lock ./

# Python optimization and uv configuration
ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install system dependencies and Python package manager
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    libffi-dev \
    libssl-dev \
    cargo \
    curl && \
    pip install --no-cache-dir uv && \
    rm -rf /var/lib/apt/lists/*

# Install the project's dependencies using the lockfile and settings
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --python 3.12 --frozen --no-install-project --no-dev --no-editable

# Then, add the rest of the project source code and install it
# Installing separately from its dependencies allows optimal layer caching
COPY . /app
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --python 3.12 --frozen --no-dev --no-editable

# Make the directory just in case it doesn't exist
RUN mkdir -p /root/.local

# ============================================
# Final stage - runtime image
# ============================================
FROM python:3.12-slim

# Place executables in the environment at the front of the path and include other binaries
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

# Install runtime dependencies, create application user, and set up directories
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    lsof && \
    rm -rf /var/lib/apt/lists/* && \
    update-ca-certificates && \
    groupadd -r app && \
    useradd -r -g app -d /app -s /bin/bash app && \
    mkdir -p /app/.ssh /app/logs && \
    chown -R app:app /app

# Copy application artifacts from build stage
COPY --from=uv --chown=app:app /app/.venv /app/.venv
COPY --from=uv --chown=app:app /root/.local /root/.local

# Copy healthcheck and entrypoint scripts with execute permissions
COPY --chmod=755 ./docker-healthcheck.sh /usr/local/bin/docker-healthcheck.sh
COPY --chmod=755 ./docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh

# Run as non-root user
USER app

# Set working directory
WORKDIR /app

# Default environment variables (can be overridden via docker run -e)
# MCP Server Configuration
ENV MCP_SERVER_NAME=argocd-mcp-server \
    MCP_SERVER_VERSION=0.1.0 \
    MCP_TRANSPORT=http \
    MCP_HOST=0.0.0.0 \
    MCP_PORT=8765 \
    MCP_PATH=/sse \
    MCP_ALLOW_WRITE=false \
    MCP_HTTP_TIMEOUT=300 \
    MCP_HTTP_KEEPALIVE_TIMEOUT=5 \
    MCP_HTTP_CONNECT_TIMEOUT=60 \
    MCP_LOG_LEVEL=INFO \
    MCP_LOG_FORMAT=json

# ArgoCD Configuration
ENV ARGOCD_SERVER_URL=https://argocd-server.argocd.svc:443 \
    ARGOCD_INSECURE=false \
    ARGOCD_TIMEOUT=300

# Expose MCP server port
EXPOSE 8765

# Health check to ensure server is running
HEALTHCHECK --interval=30s --timeout=30s --start-period=10s --retries=3 \
    CMD [ "docker-healthcheck.sh" ]

# When running the container, the entrypoint will use environment variables with defaults
# Environment variables can be overridden via docker run -e flags
ENTRYPOINT ["docker-entrypoint.sh"]