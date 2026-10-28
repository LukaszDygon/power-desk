from datetime import date

from power_desk.ingest.sources.entsoe import FilePlan, plan_files
from power_desk.ingest.sources.entsoe_file_library import ExportFile, export_file, export_month
from power_desk.ingest.spec import RunWindow
from power_desk.ingest.windows import DateRange

FOLDER = "ActualTotalLoad_6.1.A_r3"
OPEN_ENDED = RunWindow(date(2024, 1, 1), None, max_days=400)


def files(*months: int) -> list[ExportFile]:
    listed = [{"name": f"2024_{m:02d}_{FOLDER}.csv", "lastUpdatedTimestamp": "t1"} for m in months]
    return [file for item in listed if (file := export_file(item))]


def test_plan_files_takes_changed_months_oldest_first_up_to_the_cap():
    plan = plan_files(files(3, 1, 2), {}, RunWindow(date(2024, 1, 15), None, max_days=40))
    assert [f.name[:7] for f in plan.files] == ["2024_01", "2024_02"] and plan.capped


def test_plan_files_skips_files_unchanged_since_their_last_load():
    loaded = {f.name: "t1" for f in files(1, 2, 3)}
    assert plan_files(files(1, 2, 3), loaded, OPEN_ENDED) == FilePlan([])
    loaded[f"2024_02_{FOLDER}.csv"] = "t0"
    assert [f.name[:7] for f in plan_files(files(1, 2, 3), loaded, OPEN_ENDED).files] == ["2024_02"]


def test_plan_files_bounded_backfill_takes_every_file_in_range():
    loaded = {f.name: "t1" for f in files(1, 2, 3)}
    plan = plan_files(files(1, 2, 3), loaded, RunWindow(date(2024, 2, 1), date(2024, 3, 31), max_days=1))
    assert [f.name[:7] for f in plan.files] == ["2024_02", "2024_03"] and not plan.capped
    assert plan.months == DateRange(date(2024, 2, 1), date(2024, 3, 31))


def test_export_month_is_the_calendar_month():
    assert export_month(f"2024_02_{FOLDER}.csv") == DateRange(date(2024, 2, 1), date(2024, 2, 29))
    assert export_month("Export_log_r3.csv") is None
    assert export_file({"name": "Export_log_r3.csv"}) is None
