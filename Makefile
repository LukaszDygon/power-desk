# Checks, per project. Before pushing to main, `make check` (README.md, "Before pushing").
#
#   make check            lint, then the checks of the projects a change affects (scripts/affected-projects)
#   make check-all        lint, then every project's checks
#   make check-<project>  one project: logging, warehouse, elt, dashboard, services, connector
#   make lint             ruff and the import contracts between projects (pyproject.toml)
#   make hooks            run `make check` before every push to main
#
# Projects' checks are independent: `make -j check` runs them in parallel.

PROJECTS := logging warehouse elt dashboard services connector
PYTEST   := uv run pytest -q

.PHONY: check check-all lint hooks $(addprefix check-,$(PROJECTS))

check: lint
	@projects="$$(scripts/affected-projects | tr '\n' ' ')"; \
	echo "affected: $${projects:-none}"; \
	[ -z "$$projects" ] || $(MAKE) $$(printf 'check-%s ' $$projects)

check-all: lint
	@$(MAKE) $(addprefix check-,$(PROJECTS))

lint:
	uv run ruff check .
	uv run ruff format --check .
	uv run lint-imports

check-logging:
	uv run pyright -p libs/logging
	$(PYTEST) libs/logging/tests

check-warehouse:
	uv run pyright -p libs/warehouse
	$(PYTEST) libs/warehouse/tests

check-elt:
	uv run pyright -p elt
	$(PYTEST) elt/tests

check-dashboard:
	uv run pyright -p dashboard
	$(PYTEST) dashboard/tests

check-services:
	uv run pyright -p services
	$(PYTEST) services/tests

# own environment and lock (OpenMetadata's ingestion pins)
check-connector:
	uv run --project infra/openmetadata-duckdb pytest -q infra/openmetadata-duckdb/tests

hooks:
	git config core.hooksPath .githooks
