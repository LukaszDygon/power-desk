import pytest

from power_desk_elt.ingest.pipeline import working_dir
from power_desk_elt.settings import environment


def test_unknown_environment_is_rejected(monkeypatch):
    monkeypatch.setenv("POWER_DESK_ENV", "staging")
    with pytest.raises(ValueError, match="POWER_DESK_ENV"):
        environment()


def test_each_warehouse_file_keeps_its_own_dlt_state(tmp_path):
    """A scratch warehouse never inherits the configured warehouse's resource state (e.g. a snapshot's hash)."""
    assert working_dir(tmp_path / "a.duckdb") != working_dir(tmp_path / "b.duckdb") != working_dir()
