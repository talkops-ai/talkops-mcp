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
    rm -rf /var/lib/apt/lists/*

# Install uv package manager
RUN pip install uv

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

# Final stage - runtime image
FROM python:3.12-slim

# Place executables in the environment at the front of the path and include other binaries
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

# Install runtime dependencies and create application user
RUN apt-get update && \
    apt-get install -y --no-install-recommends ca-certificates curl lsof && \
    rm -rf /var/lib/apt/lists/* && \
    update-ca-certificates && \
    groupadd -r app && \
    useradd -r -g app -d /app -s /bin/bash app

# Install kubectl (latest stable)
RUN curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl" \
    && install -o root -g root -m 0755 kubectl /usr/local/bin/kubectl \
    && rm kubectl

# Install Helm CLI
RUN curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash && \
    helm version

# Copy application artifacts from build stage
COPY --from=uv --chown=app:app /app/.venv /app/.venv
COPY --from=uv --chown=app:app /root/.local /root/.local

# Copy healthcheck and entrypoint scripts
COPY ./docker-healthcheck.sh /usr/local/bin/docker-healthcheck.sh
COPY ./docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# Run as non-root
USER app

# Expose port
EXPOSE 8765

# Set working directory
WORKDIR /app

# Default environment variables (can be overridden via docker run -e)
ENV MCP_SERVER_NAME=helm-mcp-server
ENV MCP_SERVER_VERSION=0.2.0
ENV MCP_TRANSPORT=http
ENV MCP_HOST=0.0.0.0
ENV MCP_PORT=8765
ENV MCP_PATH=/sse
ENV MCP_ALLOW_WRITE=true
ENV MCP_HTTP_TIMEOUT=300
ENV MCP_HTTP_KEEPALIVE_TIMEOUT=5
ENV MCP_HTTP_CONNECT_TIMEOUT=60
ENV MCP_LOG_LEVEL=INFO
ENV MCP_LOG_FORMAT=json
ENV HELM_TIMEOUT=300
ENV K8S_TIMEOUT=30
ENV KUBECONFIG=/app/.kube/config

# Healthcheck
# HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 CMD [ "docker-healthcheck.sh" ]

# When running the container, the entrypoint will use environment variables with defaults
# Environment variables can be overridden via docker run -e flags
ENTRYPOINT ["docker-entrypoint.sh"]
