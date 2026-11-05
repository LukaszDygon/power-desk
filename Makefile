# Checks, per project. Before pushing to main, `make check` (README.md, "Before pushing").
#
#   make check            lint, then the checks of the projects a change affects, with only the tests it can
#                         affect (scripts/affected-projects)
#   make check-all        lint, then every project's checks
#   make check-<project>  one project: logging, warehouse, elt, dashboard, services, connector
#                         (TESTS_<project>='<paths>' narrows its tests)
#   make lint             ruff, the import contracts between projects (pyproject.toml), unique ADR numbers
#   make format           ruff's formatting and fixes
#   make hooks            run `make check` before every push to main (.githooks/pre-push)
#
# Projects' checks are independent: `make -j check` runs them in parallel. A passing `check` or `check-all`
# on a clean tree records it, so the pre-push hook doesn't run the same checks again.

PROJECTS := logging warehouse elt dashboard services connector
PYTEST   := uv run pytest -q
# the tree that passed, when nothing is uncommitted (read by .githooks/pre-push)
RECORD   := git diff --quiet HEAD && [ -z "$$(git ls-files --others --exclude-standard)" ] \
	&& git rev-parse 'HEAD^{tree}' > "$$(git rev-parse --git-path power-desk-checked)" || true

.PHONY: check check-all lint format hooks $(addprefix check-,$(PROJECTS))

check: lint
	@checks="$$(scripts/affected-projects)"; \
	echo "affected: $${checks:-none}"; \
	[ -z "$$checks" ] || eval '$(MAKE)' "$$checks"
	@$(RECORD)

check-all: lint
	@$(MAKE) $(addprefix check-,$(PROJECTS))
	@$(RECORD)

lint:
	uv run ruff check .
	uv run ruff format --check .
	uv run lint-imports
	@dups="$$(ls docs/adr | cut -c1-4 | sort | uniq -d)"; \
	[ -z "$$dups" ] || { echo "duplicate ADR numbers in docs/adr: $$dups (renumber the newer one)"; exit 1; }

format:
	uv run ruff format .
	uv run ruff check --fix .

check-logging:
	uv run pyright -p libs/logging
	$(PYTEST) $(or $(TESTS_logging),libs/logging/tests)

check-warehouse:
	uv run pyright -p libs/warehouse
	$(PYTEST) $(or $(TESTS_warehouse),libs/warehouse/tests)

# dbt parse first: Dagster's definitions read the manifest, which a new model or seed makes stale
check-elt:
	uv run dbt parse --quiet --project-dir elt/dbt --profiles-dir elt/dbt
	uv run pyright -p elt
	$(PYTEST) $(or $(TESTS_elt),elt/tests)

check-dashboard:
	uv run pyright -p dashboard
	$(PYTEST) $(or $(TESTS_dashboard),dashboard/tests)

check-services:
	uv run pyright -p services
	$(PYTEST) $(or $(TESTS_services),services/tests)

# own environment and lock (OpenMetadata's ingestion pins)
check-connector:
	uv run --project infra/openmetadata-duckdb pytest -q infra/openmetadata-duckdb/tests

hooks:
	git config core.hooksPath .githooks
