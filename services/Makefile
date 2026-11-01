# Local Kubernetes for the services: minikube (Docker driver) and the Helm chart.
#
#   make dev               cluster, image, credentials and release: run again after a change
#   make forward           the ENTSO-E receiver on http://localhost:8081/subscriptions (keeps running)
#   make push              send dev/sample-push.xml to it, as the Transparency Platform would
#   make logs SERVICE=iris follow a service's logs
#
# The cluster is the local platform's (platform/Makefile: `make -C platform down` deletes it; data/ stays).
# Credentials come from the repository's .env (dlt secret names, see .env.example), as one Secret.

PROFILE   ?= power-desk
NAMESPACE ?= power-desk
RELEASE   ?= power-desk-services
IMAGE     ?= power-desk-services:dev
SERVICE   ?= entsoe-subscription
# e.g. --build-arg PYTHON_IMAGE=mirror.gcr.io/library/python:3.13-slim
DOCKER_BUILD_ARGS ?=

ROOT    := $(abspath ..)
KUBECTL := kubectl --context $(PROFILE) -n $(NAMESPACE)
# images are built in the cluster's Docker daemon, so pods use them without a registry
IN_CLUSTER_DOCKER := eval $$(minikube -p $(PROFILE) docker-env) &&
HELM    := helm --kube-context $(PROFILE) -n $(NAMESPACE)

.PHONY: dev cluster image secret deploy forward push logs

dev: cluster image secret deploy

cluster:
	$(MAKE) -C $(ROOT)/platform cluster PROFILE=$(PROFILE)
	kubectl --context $(PROFILE) create namespace $(NAMESPACE) --dry-run=client -o yaml | \
		kubectl --context $(PROFILE) apply -f -

image:
	$(IN_CLUSTER_DOCKER) docker build -f $(ROOT)/services/Dockerfile -t $(IMAGE) $(DOCKER_BUILD_ARGS) $(ROOT)

secret:
	touch $(ROOT)/.env
	$(KUBECTL) create secret generic $(RELEASE)-env --from-env-file=$(ROOT)/.env --dry-run=client -o yaml | \
		$(KUBECTL) apply -f -

# the image id annotation rolls the pods whenever `make image` built a new image under the same tag
deploy:
	$(HELM) upgrade --install $(RELEASE) helm/power-desk-services -f dev/values.yaml \
		--set-string podAnnotations.power-desk/image=$$($(IN_CLUSTER_DOCKER) docker image inspect -f '{{.Id}}' $(IMAGE) | cut -c8-70)
	$(KUBECTL) get pods

forward:
	$(KUBECTL) port-forward svc/$(RELEASE)-entsoe-subscription 8081:80

push:
	curl -sS -X POST -H 'Content-Type: application/soap+xml; charset=utf-8' \
		--data-binary @dev/sample-push.xml http://localhost:8081/subscriptions; echo

logs:
	$(KUBECTL) logs -f deploy/$(RELEASE)-$(SERVICE)
