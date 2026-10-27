from datetime import date

import pyarrow as pa

from power_desk.ingest.sources.entsoe import file_period, plan_files
from power_desk.ingest.sources.entsoe_file_library import SOURCE_FILE, parse_export

FOLDER = "ActualTotalLoad_6.1.A_r3"
EXPORT = (
    "﻿DateTime(UTC)\tResolutionCode\tAreaCode\tTotalLoad[MW]\tUpdateTime(UTC)\n"
    "2024-03-01 00:00:00\tPT15M\t10YFR-RTE------C\t51000.5\t2024-03-01 01:00:00\n"
    "2024-03-01 00:15:00\tPT15M\t10YFR-RTE------C\t\t2024-03-01 01:00:00\n"
).encode()


def files(*months: int) -> list[dict]:
    return [{"name": f"2024_{m:02d}_{FOLDER}.csv", "lastUpdatedTimestamp": "t1"} for m in months]


def test_parse_export_types_columns_and_tags_the_file():
    table = parse_export(EXPORT, "f.csv")
    assert table.column_names == [
        "DateTime_UTC",
        "ResolutionCode",
        "AreaCode",
        "TotalLoad_MW",
        "UpdateTime_UTC",
        SOURCE_FILE,
    ]
    assert table.schema.field("DateTime_UTC").type == pa.timestamp("us", "UTC")
    assert table["TotalLoad_MW"].to_pylist() == [51000.5, None]
    assert table[SOURCE_FILE].to_pylist() == ["f.csv", "f.csv"]


def test_plan_files_takes_changed_months_oldest_first_up_to_the_cap():
    batch, capped = plan_files(files(3, 1, 2), {}, "2024-01-15", None, max_days_per_run=40)
    assert [f["name"][:7] for f in batch] == ["2024_01", "2024_02"] and capped


def test_plan_files_skips_files_unchanged_since_their_last_load():
    loaded = {f["name"]: "t1" for f in files(1, 2, 3)}
    assert plan_files(files(1, 2, 3), loaded, "2024-01-01", None, 400) == ([], False)
    loaded[f"2024_02_{FOLDER}.csv"] = "t0"
    assert [f["name"][:7] for f in plan_files(files(1, 2, 3), loaded, "2024-01-01", None, 400)[0]] == ["2024_02"]


def test_plan_files_bounded_backfill_takes_every_file_in_range():
    loaded = {f["name"]: "t1" for f in files(1, 2, 3)}
    batch, capped = plan_files(files(1, 2, 3), loaded, "2024-02-01", "2024-03-31", 1)
    assert [f["name"][:7] for f in batch] == ["2024_02", "2024_03"] and not capped


def test_file_period_is_the_calendar_month():
    assert file_period(f"2024_02_{FOLDER}.csv") == (date(2024, 2, 1), date(2024, 2, 29))
    assert file_period("Export_log_r3.csv") is None
