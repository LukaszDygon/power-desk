# The dashboard's image. Build from the repository root (the uv workspace and its lock live there):
#   docker build -f dashboard/Dockerfile -t power-desk-dashboard:dev .
# Installed editable: the app serves its frontend from beside its package (app.py), so the image keeps the
# repository's layout under /app. It reads the warehouse and dbt's manifest from the volume at /app/data.
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
    uv sync --frozen --no-dev --package power-desk-dashboard --no-install-workspace
COPY libs/warehouse/src libs/warehouse/src
COPY dashboard/src dashboard/src
COPY dashboard/frontend dashboard/frontend
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --package power-desk-dashboard

FROM ${PYTHON_IMAGE}
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin app
COPY --from=build /app /app
ENV PATH=/app/.venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    POWER_DESK_DUCKDB_PATH=/app/data/warehouse_prod.duckdb \
    POWER_DESK_DBT_MANIFEST=/app/data/dbt-target/manifest.json
WORKDIR /app
USER 10001
EXPOSE 8888
ENTRYPOINT ["uvicorn", "power_desk_dashboard.app:app", "--host", "0.0.0.0", "--port", "8888"]
