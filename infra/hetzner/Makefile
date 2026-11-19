# Power Desk on one Hetzner dedicated server (docs/hosting.md), driven from your machine over the tailnet.
# Settings and credentials in .env here (env.example); the publishers' credentials in the repository's .env.
#
#   make host HOST=root@<public ip>   first time: copy host/ to the server and run bootstrap.sh
#   make host                         later changes to host/, over the tailnet
#   make kubeconfig                   the cluster's kubeconfig, over the tailnet, in $(KUBECONFIG)
#   make firewall                     the Robot (edge) firewall (robot-firewall.sh): closes public SSH
#   make secrets                      the platform's and the publishers' Secrets
#   make platform                     Tailscale operator, logs (Loki, Alloy, Grafana), catalogue (OpenMetadata)
#   make images                       build the images (linux/amd64) and import them into k3s: no registry
#   make catalog-image                the catalogue's ingestion image, likewise (when the connector changes)
#   make apps                         the warehouse (Dagster, dashboard, catalogue ingestion) and the services
#   make tailnet                      the UIs' HTTPS names on the tailnet (manifests/tailnet.yaml)
#   make public                       ENTSO-E's public route on PUBLIC_HOST (cert-manager, manifests/public.yaml)
#   make status | backup-now | backup-status

SHELL := bash
.SHELLFLAGS := -euo pipefail -c

-include .env
export

ROOT       := $(abspath ../..)
INFRA      := $(ROOT)/infra
include $(INFRA)/versions.mk

TS_HOST    ?= power-desk
HOST       ?= root@$(TS_HOST)
KUBECONFIG ?= $(HOME)/.kube/power-desk-hetzner
PLATFORM   := linux/amd64
# e.g. --build-arg PYTHON_IMAGE=mirror.gcr.io/library/python:3.13-slim, when Docker Hub refuses pulls
DOCKER_BUILD_ARGS ?=
SSH        := ssh -o StrictHostKeyChecking=accept-new $(HOST)
KUBECTL    := kubectl --kubeconfig $(KUBECONFIG)
HELM       := helm --kubeconfig $(KUBECONFIG)
# the tag of the images last imported (make images), deployed by make apps
TAG_FILE   := .image-tag

.PHONY: host kubeconfig firewall namespaces secrets repos platform images catalog-image apps tailnet public status \
	backup-now backup-status

host:
	$(SSH) 'rm -rf /root/power-desk-host && mkdir -p /root/power-desk-host'
	scp -q host/* $(HOST):/root/power-desk-host/
	@# the auth key on stdin, not on a command line
	printf '%s\n' "$${TAILSCALE_AUTHKEY:-}" | \
		$(SSH) 'read -r TAILSCALE_AUTHKEY; export TAILSCALE_AUTHKEY; bash /root/power-desk-host/bootstrap.sh'

kubeconfig:
	mkdir -p $(dir $(KUBECONFIG))
	$(SSH) cat /etc/rancher/k3s/k3s.yaml | \
		sed -e 's#https://127.0.0.1:6443#https://$(TS_HOST):6443#' -e 's/: default$$/: power-desk/' > $(KUBECONFIG)
	chmod 0600 $(KUBECONFIG)
	$(KUBECTL) get nodes

firewall:
	./robot-firewall.sh

namespaces:
	for ns in power-desk observability openmetadata tailscale cert-manager; do \
		$(KUBECTL) create namespace $$ns --dry-run=client -o yaml | $(KUBECTL) apply -f - >/dev/null; done

# Values come from the environment (printf is a shell builtin), so no secret appears on a command line.
secrets: namespaces
	$(KUBECTL) -n power-desk create secret generic power-desk-env --from-env-file=$(ROOT)/.env \
		--dry-run=client -o yaml | $(KUBECTL) apply -f -
	$(KUBECTL) -n tailscale create secret generic operator-oauth --dry-run=client -o yaml --from-env-file=<( \
		printf 'client_id=%s\nclient_secret=%s\n' "$$TS_OAUTH_CLIENT_ID" "$$TS_OAUTH_CLIENT_SECRET") | $(KUBECTL) apply -f -
	$(KUBECTL) -n observability create secret generic grafana-admin --dry-run=client -o yaml --from-env-file=<( \
		printf 'admin-user=admin\nadmin-password=%s\n' "$$GRAFANA_ADMIN_PASSWORD") | $(KUBECTL) apply -f -
	$(KUBECTL) -n openmetadata create secret generic mysql-auth --dry-run=client -o yaml --from-env-file=<( \
		printf 'mysql-root-password=%s\nmysql-password=%s\n' "$$MYSQL_ROOT_PASSWORD" "$$MYSQL_PASSWORD") | $(KUBECTL) apply -f -
	$(KUBECTL) -n openmetadata create secret generic mysql-secrets --dry-run=client -o yaml --from-env-file=<( \
		printf 'openmetadata-mysql-password=%s\n' "$$MYSQL_PASSWORD") | $(KUBECTL) apply -f -
	@# the server reads it even without a pipeline service (Airflow)
	$(KUBECTL) -n openmetadata create secret generic airflow-secrets --dry-run=client -o yaml \
		--from-literal=openmetadata-airflow-password=unused | $(KUBECTL) apply -f -
	if [ -n "$${OM_BOT_TOKEN:-}" ]; then \
		$(KUBECTL) -n power-desk create secret generic openmetadata-ingestion-bot --dry-run=client -o yaml --from-env-file=<( \
			printf 'OPENMETADATA_JWT_TOKEN=%s\n' "$$OM_BOT_TOKEN") | $(KUBECTL) apply -f -; fi
	if [ -n "$${CLOUDFLARE_API_TOKEN:-}" ]; then \
		$(KUBECTL) -n cert-manager create secret generic cloudflare-api-token --dry-run=client -o yaml --from-env-file=<( \
			printf 'api-token=%s\n' "$$CLOUDFLARE_API_TOKEN") | $(KUBECTL) apply -f -; fi

repos:
	helm repo add --force-update grafana https://grafana.github.io/helm-charts >/dev/null
	helm repo add --force-update open-metadata https://helm.open-metadata.org >/dev/null
	helm repo add --force-update tailscale https://pkgs.tailscale.com/helmcharts >/dev/null
	helm repo add --force-update jetstack https://charts.jetstack.io >/dev/null
	helm repo update grafana open-metadata tailscale jetstack >/dev/null

# Each chart takes the local cluster's values (infra/), then the server's (values/).
platform: repos namespaces
	$(HELM) upgrade --install tailscale-operator tailscale/tailscale-operator --version $(TS_OPERATOR_CHART) \
		-n tailscale --wait
	$(HELM) upgrade --install loki grafana/loki --version $(LOKI_CHART) -n observability \
		-f $(INFRA)/observability/loki.yaml
	$(HELM) upgrade --install alloy grafana/alloy --version $(ALLOY_CHART) -n observability \
		-f $(INFRA)/observability/alloy.yaml -f values/alloy.yaml \
		--set-file alloy.configMap.content=$(INFRA)/observability/config.alloy
	$(HELM) upgrade --install grafana grafana/grafana --version $(GRAFANA_CHART) -n observability \
		-f $(INFRA)/observability/grafana.yaml -f values/grafana.yaml \
		--set-file dashboards.power-desk.logs.json=$(INFRA)/observability/logs-dashboard.json
	$(HELM) upgrade --install openmetadata-dependencies open-metadata/openmetadata-dependencies --version $(OM_CHART) \
		-n openmetadata -f $(INFRA)/openmetadata/dependencies.yaml -f values/openmetadata-dependencies.yaml \
		--wait --timeout 15m
	$(HELM) upgrade --install openmetadata open-metadata/openmetadata --version $(OM_CHART) -n openmetadata \
		-f $(INFRA)/openmetadata/openmetadata.yaml -f values/openmetadata.yaml --wait --timeout 15m

# Built here, streamed into k3s's containerd over SSH; pods find them by tag (pullPolicy IfNotPresent).
images:
	tag=$$(git -C $(ROOT) rev-parse --short=12 HEAD)$$(git -C $(ROOT) diff --quiet HEAD || echo "-dirty$$(date +%s)"); \
	for project in elt dashboard services; do \
		docker buildx build --platform $(PLATFORM) $(DOCKER_BUILD_ARGS) -f $(ROOT)/$$project/Dockerfile \
			-t power-desk-$$project:$$tag --load $(ROOT); done; \
	docker save power-desk-elt:$$tag power-desk-dashboard:$$tag power-desk-services:$$tag | gzip -1 | \
		$(SSH) 'gunzip | k3s ctr -n k8s.io images import -'; \
	echo "$$tag" > $(TAG_FILE)

catalog-image:
	docker buildx build --platform $(PLATFORM) -f $(INFRA)/openmetadata-duckdb/docker/Dockerfile \
		-t openmetadata-ingestion-duckdb:$(OM_CHART) --load $(INFRA)/openmetadata-duckdb
	docker save openmetadata-ingestion-duckdb:$(OM_CHART) | gzip -1 | \
		$(SSH) 'gunzip | k3s ctr -n k8s.io images import -'

apps:
	tag=$$(cat $(TAG_FILE)); \
	$(HELM) upgrade --install power-desk-warehouse $(INFRA)/warehouse/power-desk-warehouse -n power-desk \
		-f values/warehouse.yaml --set-string images.elt.tag=$$tag,images.dashboard.tag=$$tag \
		--set-string images.catalog.tag=$(OM_CHART); \
	$(HELM) upgrade --install power-desk-services $(INFRA)/services/power-desk-services -n power-desk \
		-f values/services.yaml --set-string image.tag=$$tag \
		$(if $(PUBLIC_HOST),--set services.entsoe-subscription.ingress.enabled=true \
			--set-string services.entsoe-subscription.ingress.host=$(PUBLIC_HOST))

tailnet:
	$(KUBECTL) apply -f manifests/tailnet.yaml

public: repos
	test -n "$(PUBLIC_HOST)" || { echo "set PUBLIC_HOST in .env"; exit 1; }
	$(HELM) upgrade --install cert-manager jetstack/cert-manager --version $(CERT_MANAGER_CHART) -n cert-manager \
		--set crds.enabled=true --wait
	$(KUBECTL) apply -f manifests/public.yaml
	$(MAKE) apps

status:
	$(KUBECTL) get pods -A -o wide | grep -v kube-system
	$(KUBECTL) get ingress -A

backup-now:
	$(SSH) 'systemctl start power-desk-backup && journalctl -u power-desk-backup -n 20 --no-pager'

backup-status:
	$(SSH) 'set -a; . /etc/power-desk/backup.env; restic snapshots --latest 5; systemctl list-timers power-desk-backup.timer'
