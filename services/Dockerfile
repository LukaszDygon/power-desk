# One image for every service; the command picks one: `power-desk-service <name>`.
# Build from the repository root (the uv workspace and its lock live there):
#   docker build -f services/Dockerfile -t power-desk-services:dev .
# PYTHON_IMAGE swaps the base for a registry mirror (e.g. mirror.gcr.io/library/python:3.13-slim).
ARG PYTHON_IMAGE=python:3.13-slim

FROM ${PYTHON_IMAGE} AS build
COPY --from=ghcr.io/astral-sh/uv:0.7.3 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=0
WORKDIR /app
# dependencies first: a layer reused until the lock changes
# every workspace member's pyproject.toml, so uv finds the workspace; only this package's are installed
COPY pyproject.toml uv.lock ./
COPY elt/pyproject.toml elt/
COPY dashboard/pyproject.toml dashboard/
COPY libs/logging/pyproject.toml libs/logging/
COPY libs/warehouse/pyproject.toml libs/warehouse/
COPY services/pyproject.toml services/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --package power-desk-services --no-install-workspace
COPY libs/logging/src libs/logging/src
COPY services/src services/src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --package power-desk-services --no-editable

FROM ${PYTHON_IMAGE}
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin app
COPY --from=build /app/.venv /app/.venv
ENV PATH=/app/.venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    POWER_DESK_LOG_FORMAT=json \
    POWER_DESK_SERVICES_PIPELINES_DIR=/var/lib/power-desk/pipelines \
    DLT_DATA_DIR=/var/lib/power-desk/dlt \
    RUNTIME__DLTHUB_TELEMETRY=false
WORKDIR /var/lib/power-desk
RUN chown app /var/lib/power-desk
USER 10001
EXPOSE 8080
ENTRYPOINT ["power-desk-service"]
