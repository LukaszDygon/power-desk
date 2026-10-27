import duckdb
import pytest

from power_desk import warehouse


def test_connect_retries_while_the_warehouse_is_locked(monkeypatch, tmp_path):
    attempts = []
    real_connect = duckdb.connect

    def locked_once(*args, **kwargs):
        attempts.append(1)
        if len(attempts) == 1:
            raise duckdb.IOException("IO Error: Could not set lock on file")
        return real_connect(*args, **kwargs)

    monkeypatch.setattr(duckdb, "connect", locked_once)
    with warehouse.connect(tmp_path / "w.duckdb", read_only=False) as con:
        assert con.execute("select 1").fetchall() == [(1,)]
    assert len(attempts) == 2


def test_connect_raises_other_errors_at_once(monkeypatch, tmp_path):
    attempts = []

    def broken(*args, **kwargs):
        attempts.append(1)
        raise duckdb.IOException("IO Error: Cannot open file")

    monkeypatch.setattr(duckdb, "connect", broken)
    with pytest.raises(duckdb.IOException, match="Cannot open file"), warehouse.connect(tmp_path / "w.duckdb"):
        pass
    assert len(attempts) == 1
