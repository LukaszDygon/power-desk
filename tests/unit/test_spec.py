from datetime import date

from dlt.common.schema import Schema
from dlt.sources import DltSource

from power_desk.ingest.spec import RunWindow, SourceSpec


def test_source_window_defaults_to_the_start_date_and_the_source_cap(monkeypatch):
    monkeypatch.setenv("POWER_DESK_START_DATE", "2024-01-01")
    spec = SourceSpec("probe", build=lambda window: DltSource(Schema("probe"), "probe"), max_days_per_run=31)
    assert spec.window() == RunWindow(date(2024, 1, 1), None, 31)
    assert spec.window("2024-03-01T10:00:00Z", "2024-03-02", 0) == RunWindow(date(2024, 3, 1), date(2024, 3, 2), 0)


def test_padded_window_widens_both_ends_and_keeps_open_ended_runs_open():
    assert RunWindow(date(2024, 3, 1), date(2024, 3, 2), 7).padded(1) == RunWindow(
        date(2024, 2, 29), date(2024, 3, 3), 7
    )
    assert not RunWindow(date(2024, 3, 1), None, 7).padded(1).bounded
