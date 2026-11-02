"""Tests run one project at a time: each has its own `tests` package, fixtures and settings.

make check-<project>           type check and tests of one project (README.md, "Before pushing")
make check / make check-all    the projects a change affects / every project
uv run pytest <project>/tests  one project's tests, e.g. `uv run pytest elt/tests/unit`
"""

import pytest


def pytest_configure(config: pytest.Config) -> None:
    raise pytest.UsageError(f"pytest at the repository root collects nothing.\n{__doc__}")
