import pytest

from power_desk.settings import REPO_ROOT, environment, pipelines_dir, warehouse_path


def test_environment_selects_warehouse_and_dlt_state(monkeypatch):
    for name in ("POWER_DESK_DUCKDB_PATH", "POWER_DESK_PIPELINES_DIR", "POWER_DESK_ENV"):
        monkeypatch.delenv(name, raising=False)
    assert warehouse_path() == REPO_ROOT / "data" / "warehouse_dev.duckdb"
    monkeypatch.setenv("POWER_DESK_ENV", "prod")
    assert (warehouse_path(), pipelines_dir()) == (
        REPO_ROOT / "data" / "warehouse_prod.duckdb",
        REPO_ROOT / ".dlt" / "pipelines" / "prod",
    )
    monkeypatch.setenv("POWER_DESK_DUCKDB_PATH", "/tmp/explicit.duckdb")
    assert str(warehouse_path()) == "/tmp/explicit.duckdb"


def test_unknown_environment_is_rejected(monkeypatch):
    monkeypatch.setenv("POWER_DESK_ENV", "staging")
    with pytest.raises(ValueError, match="POWER_DESK_ENV"):
        environment()
