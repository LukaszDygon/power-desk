# OpenMetadata's ingestion image (the server's version) with this connector; build from this directory:
#   docker build -f docker/Dockerfile -t openmetadata-ingestion-duckdb .
FROM docker.getcollate.io/openmetadata/ingestion:2.0.7
WORKDIR /opt/airflow/openmetadata-duckdb
USER airflow
COPY --chown=airflow:0 pyproject.toml ./
COPY --chown=airflow:0 src ./src
# the image brings openmetadata-ingestion; add the warehouse's DuckDB
RUN pip install --no-deps . duckdb==1.5.5
