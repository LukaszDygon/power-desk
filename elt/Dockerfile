# The orchestrator's image: Dagster (webserver, daemon), the dlt sources and the dbt project.
# Build from the repository root (the uv workspace and its lock live there):
#   docker build -f elt/Dockerfile -t power-desk-elt:dev .
# Installed editable: the ELT finds its dbt project and Dagster instance beside its package (settings.py), so
# the image keeps the repository's layout under /app. The warehouse's files are one volume at /app/data
# (docs/hosting.md); dbt's artifacts go there too, where the dashboard and the catalogue read them.
ARG PYTHON_IMAGE=python:3.13-slim

FROM ${PYTHON_IMAGE} AS build
COPY --from=ghcr.io/astral-sh/uv:0.7.3 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=0
WORKDIR /app
# dependencies first: a layer reused until the lock changes
COPY pyproject.toml uv.lock ./
COPY elt/pyproject.toml elt/
COPY dashboard/pyproject.toml dashboard/
COPY libs/logging/pyproject.toml libs/logging/
COPY libs/warehouse/pyproject.toml libs/warehouse/
COPY services/pyproject.toml services/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --package power-desk-elt --no-install-workspace
COPY libs/logging/src libs/logging/src
COPY libs/warehouse/src libs/warehouse/src
COPY elt/src elt/src
COPY elt/dbt elt/dbt
COPY elt/.dagster/prod/dagster.yaml elt/.dagster/prod/dagster.yaml
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --package power-desk-elt

FROM ${PYTHON_IMAGE}
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin app
COPY --from=build /app /app
# dbt writes its artifacts and logs beside the project; the root filesystem is read-only in the cluster
RUN ln -s /app/data/dbt-target /app/elt/dbt/target && ln -s /app/data/dbt-logs /app/elt/dbt/logs
ENV PATH=/app/.venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    HOME=/app/data/home \
    POWER_DESK_LOG_FORMAT=json \
    POWER_DESK_DUCKDB_PATH=/app/data/warehouse_prod.duckdb \
    POWER_DESK_PIPELINES_DIR=/app/data/dlt/pipelines \
    DLT_DATA_DIR=/app/data/dlt \
    DAGSTER_HOME=/app/data/dagster \
    DBT_LOG_FORMAT_FILE=json \
    RUNTIME__DLTHUB_TELEMETRY=false
WORKDIR /app/elt
USER 10001
EXPOSE 3000
