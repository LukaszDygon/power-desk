# Local platform on minikube: the cluster, log aggregation (Loki, Alloy, Grafana) and the catalogue
# (OpenMetadata). Local-cluster settings only; see README.md.
#
#   make cluster         minikube with data/ mounted (landing zone, run logs); used by infra/services too
#   make observability   Loki + Alloy + Grafana, then `make grafana` -> http://localhost:3000
#   make openmetadata    MySQL + OpenSearch + OpenMetadata, then `make openmetadata-ui` -> http://localhost:8585
#   make catalog         register the warehouse and the dbt project in OpenMetadata (needs `openmetadata-ui`)
#   make observability-down / openmetadata-down   stop a stack (its data stays on its volumes)
#   make down            delete the cluster
#
# Sized to the minimum for trying things out: on a small machine run one stack at a time.

PROFILE ?= power-desk
# the node's memory cap, fixed when the cluster is created (minikube's default: a quarter of the machine's);
# OpenMetadata needs about 6g beside the rest, e.g. `make cluster MEMORY=6g` on a 16 GB machine
MEMORY  ?=
ROOT    := $(abspath ..)
KUBECTL := kubectl --context $(PROFILE)
HELM    := helm --kube-context $(PROFILE)
CONNECTOR := $(ROOT)/infra/openmetadata-duckdb
OM_HOST ?= http://localhost:8585/api

# chart versions, pinned
LOKI_CHART    := 7.5.0
ALLOY_CHART   := 1.15.0
GRAFANA_CHART := 10.5.15
OM_CHART      := 2.0.7

.PHONY: cluster repos observability observability-down grafana openmetadata openmetadata-ui openmetadata-down catalog status down

cluster:
	mkdir -p $(ROOT)/data/landing $(ROOT)/data/logs
	minikube status -p $(PROFILE) >/dev/null 2>&1 || \
		minikube start -p $(PROFILE) --driver=docker --registry-mirror=https://mirror.gcr.io $(if $(MEMORY),--memory=$(MEMORY)) \
			--mount --mount-string="$(ROOT)/data:/power-desk-data"

repos:
	helm repo add --force-update grafana https://grafana.github.io/helm-charts >/dev/null
	helm repo add --force-update open-metadata https://helm.open-metadata.org >/dev/null
	helm repo update grafana open-metadata >/dev/null

observability: cluster repos
	$(HELM) upgrade --install loki grafana/loki --version $(LOKI_CHART) -n observability --create-namespace \
		-f observability/loki.yaml
	$(HELM) upgrade --install alloy grafana/alloy --version $(ALLOY_CHART) -n observability \
		-f observability/alloy.yaml --set-file alloy.configMap.content=observability/config.alloy
	$(HELM) upgrade --install grafana grafana/grafana --version $(GRAFANA_CHART) -n observability \
		-f observability/grafana.yaml --set-file dashboards.power-desk.logs.json=observability/logs-dashboard.json

observability-down:
	$(HELM) -n observability uninstall grafana alloy loki --ignore-not-found

grafana:
	$(KUBECTL) -n observability port-forward svc/grafana 3000:80

openmetadata: cluster repos
	$(KUBECTL) create namespace openmetadata --dry-run=client -o yaml | $(KUBECTL) apply -f -
	$(KUBECTL) -n openmetadata create secret generic mysql-secrets \
		--from-literal=openmetadata-mysql-password=openmetadata_password --dry-run=client -o yaml | $(KUBECTL) apply -f -
	@# the server reads it even without a pipeline service (Airflow)
	$(KUBECTL) -n openmetadata create secret generic airflow-secrets \
		--from-literal=openmetadata-airflow-password=unused --dry-run=client -o yaml | $(KUBECTL) apply -f -
	$(HELM) upgrade --install openmetadata-dependencies open-metadata/openmetadata-dependencies --version $(OM_CHART) \
		-n openmetadata -f openmetadata/dependencies.yaml --wait --timeout 15m
	$(HELM) upgrade --install openmetadata open-metadata/openmetadata --version $(OM_CHART) \
		-n openmetadata -f openmetadata/openmetadata.yaml --wait --timeout 15m

openmetadata-ui:
	$(KUBECTL) -n openmetadata port-forward svc/openmetadata 8585:8585

openmetadata-down:
	$(HELM) -n openmetadata uninstall openmetadata openmetadata-dependencies --ignore-not-found

# dbt's manifest and catalog, compiled into their own target so the builds' artifacts stay as they are
DBT_CATALOG_PATH := $(ROOT)/elt/dbt/target/openmetadata
# test results: the newest build's, from the CLIs (elt/dbt/target) or a Dagster run (its own target)
DBT_RUN_RESULTS = $(shell ls -t $(ROOT)/elt/dbt/target/run_results.json $(ROOT)/elt/dbt/target/dbt_models-*/run_results.json 2>/dev/null | head -1)

# the warehouse (our DuckDB connector), then dbt's artifacts onto its tables; run between Dagster runs
catalog:
	cd $(ROOT) && uv run python -c "from power_desk_elt.transform.dbt import run_dbt; \
		raise SystemExit(run_dbt(['compile', '--write-catalog', '--quiet'], target_path='$(DBT_CATALOG_PATH)'))"
	export OPENMETADATA_HOST=$(OM_HOST) \
		OPENMETADATA_JWT_TOKEN=$$(uv run --project $(CONNECTOR) python openmetadata/bot_token.py $(OM_HOST)) \
		POWER_DESK_DUCKDB_PATH=$$(cd $(ROOT) && uv run python -c "from power_desk_warehouse.settings import warehouse_path; print(warehouse_path())") \
		DBT_CATALOG_PATH=$(DBT_CATALOG_PATH) DBT_RUN_RESULTS=$(DBT_RUN_RESULTS) && \
	uv run --project $(CONNECTOR) metadata ingest -c $(CONNECTOR)/configs/warehouse.yaml && \
	uv run --project $(CONNECTOR) metadata ingest -c $(CONNECTOR)/configs/dbt.yaml

status:
	$(KUBECTL) get pods -A -o wide | grep -v kube-system

down:
	minikube delete -p $(PROFILE)
