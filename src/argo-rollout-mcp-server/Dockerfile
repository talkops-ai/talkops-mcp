# Stage 1: Build locked Python virtual environment with uv
FROM python:3.12-slim AS uv

ARG TARGETARCH=amd64
WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_PREFERENCE=only-system \
    UV_FROZEN=true \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential \
        gcc \
        libffi-dev \
        libssl-dev \
        curl && \
    pip install --no-cache-dir uv && \
    rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock ./

RUN --mount=type=cache,target=/root/.cache/uv,id=uv-argo-rollout-mcp-server-${TARGETARCH} \
    uv sync --python 3.12 --frozen --no-install-project --no-dev --no-editable

COPY . /app
RUN --mount=type=cache,target=/root/.cache/uv,id=uv-argo-rollout-mcp-server-${TARGETARCH} \
    uv sync --python 3.12 --frozen --no-dev --no-editable

# Stage 2: Minimal non-root runtime image
FROM python:3.12-slim

ARG TARGETARCH=amd64
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    HOME=/app

RUN apt-get update && \
    apt-get install -y --no-install-recommends ca-certificates curl lsof && \
    rm -rf /var/lib/apt/lists/* && \
    update-ca-certificates && \
    groupadd -r app && \
    useradd -r -g app -d /app -s /bin/bash app && \
    mkdir -p /app/.kube /app/.cache /app/.config /app/.ssh /app/logs && \
    chown -R app:app /app

# Install kubectl (multi-arch)
RUN KUBE_VERSION="$(curl -fsSL https://dl.k8s.io/release/stable.txt)" && \
    curl -fsSLo /usr/local/bin/kubectl "https://dl.k8s.io/release/${KUBE_VERSION}/bin/linux/${TARGETARCH}/kubectl" && \
    chmod +x /usr/local/bin/kubectl

# Install Argo Rollouts kubectl plugin (multi-arch)
RUN curl -fsSLo /usr/local/bin/kubectl-argo-rollouts \
        "https://github.com/argoproj/argo-rollouts/releases/latest/download/kubectl-argo-rollouts-linux-${TARGETARCH}" && \
    chmod +x /usr/local/bin/kubectl-argo-rollouts

COPY --from=uv --chown=app:app /app/.venv /app/.venv
COPY --from=uv --chown=app:app /app/plugin.json /app/mcp.json /app/
COPY --from=uv --chown=app:app /app/skills /app/skills

COPY --chmod=755 ./docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh

USER app
WORKDIR /app

EXPOSE 8768

ENV MCP_SERVER_NAME=argo-rollout-mcp-server \
    MCP_SERVER_VERSION=0.2.1 \
    MCP_TRANSPORT=http \
    MCP_HOST=0.0.0.0 \
    MCP_PORT=8768 \
    MCP_PATH=/mcp \
    MCP_ALLOW_WRITE=false \
    MCP_DEBUG=false \
    PROMETHEUS_URL=http://prometheus:9090

ENTRYPOINT ["docker-entrypoint.sh"]
