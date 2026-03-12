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
# NOTE: Removed --frozen because the package might not be fully locked yet
ENV UV_FROZEN=false

# Copy the required files first
COPY pyproject.toml ./

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
    curl && \
    rm -rf /var/lib/apt/lists/*

# Install uv package manager
RUN pip install uv

# Create virtual environment and install the project's dependencies
RUN uv venv /app/.venv
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --python 3.12 --no-install-project --no-dev --no-editable

# Then, add the rest of the project source code and install it
COPY . /app
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --python 3.12 --no-dev --no-editable

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

# Install Argo Rollouts kubectl plugin
RUN curl -LO "https://github.com/argoproj/argo-rollouts/releases/latest/download/kubectl-argo-rollouts-linux-amd64" \
    && install -o root -g root -m 0755 kubectl-argo-rollouts-linux-amd64 /usr/local/bin/kubectl-argo-rollouts \
    && rm kubectl-argo-rollouts-linux-amd64

# Copy application artifacts from build stage
COPY --from=uv --chown=app:app /app/.venv /app/.venv
COPY --from=uv --chown=app:app /root/.local /root/.local

# Copy scripts and make them executable
COPY ./docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# Run as non-root
USER app

# Expose port
EXPOSE 8768

# Set working directory
WORKDIR /app

# Default environment variables (override with -e at runtime)
ENV MCP_SERVER_NAME=argo-rollout-mcp-server
ENV MCP_SERVER_VERSION=0.1.0
ENV MCP_TRANSPORT=http
ENV MCP_HOST=0.0.0.0
ENV MCP_PORT=8768
ENV MCP_PATH=/mcp
ENV MCP_DEBUG=false
ENV K8S_KUBECONFIG=/app/.kube/config
ENV K8S_IN_CLUSTER=false
ENV PROMETHEUS_URL=http://prometheus:9090

ENTRYPOINT ["docker-entrypoint.sh"]
