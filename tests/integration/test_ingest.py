"""Each source's pipeline against the replayed seed publishers."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from power_desk.ingest import http
from power_desk.ingest.pipeline import make_pipeline, make_source, resource_progress, run
from power_desk.ingest.registry import SOURCES
from power_desk.ingest.seed.load import seed_end_date
from power_desk.ingest.seed.replay import SEED_START, SeedPublishers, replay
from power_desk.ingest.sources import bmrs, entsoe, entsoe_eic
from tests.support import query


def published_rows(publishers: SeedPublishers) -> dict[str, int]:
    """Rows each raw table must hold after loading everything the publishers serve."""
    return {
        **{dataset.resource: len(publishers.records[dataset.code]) for dataset in bmrs.DATASETS},
        "pvlive__solar": len(publishers.records["PVLIVE"]),
        **{
            item.resource: sum(content.count(b"\n") - 1 for _, content in publishers.exports[item.folder].values())
            for item in entsoe.DATA_ITEMS
        },
        **{snapshot.resource: len(snapshot.parse(publishers.files[snapshot.url])) for snapshot in entsoe_eic.SNAPSHOTS},
    }


def load(
    source: str,
    db: Path,
    publishers: SeedPublishers,
    start: str = SEED_START,
    end: str | None = None,
    max_days: int | None = None,
    resources: list[str] | None = None,
) -> dict:
    pipeline = make_pipeline(source, db)
    with replay(publishers):
        run(pipeline, make_source(source, SOURCES[source].window(start, end, max_days), resources))
    return resource_progress(pipeline, source)


@pytest.mark.parametrize("source", sorted(SOURCES))
def test_seed_week_loads_every_published_row(source, tmp_path):
    publishers = SeedPublishers.from_seed()
    load(source, tmp_path / "w.duckdb", publishers, end=seed_end_date())
    tables = make_source(source).resources
    loaded = {table: query(tmp_path / "w.duckdb", f"select count(*) from raw.{table}")[0][0] for table in tables}
    assert loaded == {table: published_rows(publishers)[table] for table in tables}


def test_stream_resumes_from_its_cursor_and_records_its_window(tmp_path):
    publishers, db = SeedPublishers.from_seed(), tmp_path / "w.duckdb"
    first = load("bmrs", db, publishers, max_days=1, resources=["bmrs__indo"])["bmrs__indo"]
    assert (first["first_day"], first["last_day"], first["capped"]) == ("2024-02-29", "2024-03-01", True)
    second = load("bmrs", db, publishers, max_days=1, resources=["bmrs__indo"])["bmrs__indo"]
    assert (second["first_day"], second["last_day"]) == ("2024-03-01", "2024-03-02")
    assert second["cursor_last_value"] > first["cursor_last_value"]
    assert query(db, "select count(*) = count(distinct (settlement_date, settlement_period)) from raw.bmrs__indo") == [
        (True,)
    ]


def test_bounded_backfill_leaves_the_cursor_untouched(tmp_path):
    publishers, db = SeedPublishers.from_seed(), tmp_path / "w.duckdb"
    cursor = load("bmrs", db, publishers, "2024-03-02", max_days=1, resources=["bmrs__indo"])["bmrs__indo"][
        "cursor_last_value"
    ]
    after = load("bmrs", db, publishers, "2024-03-01", "2024-03-01", resources=["bmrs__indo"])["bmrs__indo"]
    assert after["cursor_last_value"] == cursor


def test_a_failed_request_fails_the_run_and_keeps_the_state(tmp_path, monkeypatch):
    def unavailable(*args, **kwargs):
        raise ConnectionError("API down")

    pipeline = make_pipeline("bmrs", tmp_path / "w.duckdb")
    monkeypatch.setattr(http, "fetch_json", unavailable)
    with pytest.raises(Exception, match="API down"):
        run(pipeline, make_source("bmrs", SOURCES["bmrs"].window("2024-03-01", "2024-03-02"), ["bmrs__indo"]))
    assert resource_progress(pipeline, "bmrs") == {}


def test_a_republished_value_is_a_new_version_and_unchanged_months_are_skipped(tmp_path):
    publishers, db = SeedPublishers.from_seed(), tmp_path / "w.duckdb"
    item = entsoe.DATA_ITEMS[0]
    [(name, (_, content))] = publishers.exports[item.folder].items()
    load("entsoe", db, publishers, resources=[item.resource])
    published = query(db, f"select count(*) from raw.{item.resource}")[0][0]
    downloads = len(publishers.requests)

    load("entsoe", db, publishers, resources=[item.resource])
    assert len(publishers.requests) == downloads

    # a re-export carrying one revised row: merged on the natural key, the other rows stay current
    header, first_row, *_ = content.decode().splitlines()
    fields = first_row.split("\t")
    fields[header.split("\t").index("TotalLoad[MW]")] = "1.5"
    publishers.exports[item.folder][name] = ("republished", "\n".join([header, "\t".join(fields), ""]).encode())
    load("entsoe", db, publishers, resources=[item.resource])
    versions = f"select count(*), count(*) filter (where _dlt_valid_to is null) from raw.{item.resource}"
    assert query(db, versions) == [(published + 1, published)]
    revised = f"select total_load_mwx from raw.{item.resource} where _dlt_valid_to is null and total_load_mwx = 1.5"
    assert query(db, revised) == [(1.5,)]


def test_snapshot_keeps_every_version_and_skips_an_unchanged_file(tmp_path):
    publishers, db = SeedPublishers.from_seed(), tmp_path / "w.duckdb"
    codes = publishers.files[entsoe_eic.CODES_URL]
    header, first, second, *_ = codes.splitlines()
    publishers.files[entsoe_eic.CODES_URL] = f"{header}\n{first}\n{second}\n"
    current = "select count(*) filter (where _dlt_valid_to is null), count(*) from raw.entsoe_eic__codes"

    load("entsoe_eic", db, publishers, resources=["entsoe_eic__codes"])
    load("entsoe_eic", db, publishers, resources=["entsoe_eic__codes"])
    assert query(db, current) == [(2, 2)]

    fields = first.split(";")
    fields[1] = "RENAMED"
    renamed = ";".join(fields)
    publishers.files[entsoe_eic.CODES_URL] = f"{header}\n{renamed}\n"
    load("entsoe_eic", db, publishers, resources=["entsoe_eic__codes"])
    assert query(db, current) == [(1, 3)]


def test_file_partition_cursor_is_the_latest_update_not_the_latest_value_time(tmp_path):
    publishers, db = SeedPublishers.from_seed(), tmp_path / "w.duckdb"
    item = entsoe.DATA_ITEMS[1]  # day-ahead load forecast: re-forecast after its value times
    cursor = load("entsoe", db, publishers, resources=[item.resource])[item.resource]["cursor_last_value"]
    [(latest_update, latest_value)] = query(
        db, f"select max(update_time_utcx), max(date_time_utcx) from raw.{item.resource}"
    )
    assert datetime.fromisoformat(cursor) == latest_update and latest_update > latest_value


def test_stream_without_publish_time_resumes_from_its_interval_start(tmp_path):
    publishers, db = SeedPublishers.from_seed(), tmp_path / "w.duckdb"
    cursor = load("bmrs", db, publishers, max_days=1, resources=["bmrs__mid"])["bmrs__mid"]["cursor_last_value"]
    assert query(db, "select max(start_time) from raw.bmrs__mid")[0][0] == datetime.fromisoformat(cursor)


def test_documents_sharing_a_natural_key_load_as_published_and_a_revision_closes_them_all(tmp_path):
    publishers, db = SeedPublishers.from_seed(), tmp_path / "w.duckdb"
    item = next(item for item in entsoe.DATA_ITEMS if item.document_key)
    [(name, (_, content))] = publishers.exports[item.folder].items()
    header, first_row, *_ = content.decode().splitlines()
    columns = header.split("\t")
    instance, update, price = (columns.index(c) for c in ("InstanceCode", "UpdateTime(UTC)", "Price[Currency/MWh]"))

    def export(*rows: list[str]) -> bytes:
        return "\r\n".join([header, *("\t".join(row) for row in rows), ""]).encode()

    first = first_row.split("\t")
    second = [*first]
    second[instance], second[update] = "0" * 32, "2026-08-20 12:10:14"
    publishers.exports[item.folder] = {name: ("two documents", export(first, second))}
    load("entsoe", db, publishers, resources=[item.resource])
    current = f"select count(*) filter (where _dlt_valid_to is null), count(*) from raw.{item.resource}"
    assert query(db, current) == [(2, 2)]

    revised = [*second]
    revised[instance], revised[price] = "1" * 32, "1.5"
    publishers.exports[item.folder] = {name: ("revised", export(revised))}
    load("entsoe", db, publishers, resources=[item.resource])
    assert query(db, current) == [(1, 3)]


def test_a_record_the_publisher_repeats_within_a_load_is_stored_once(tmp_path):
    publishers, db = SeedPublishers.from_seed(), tmp_path / "w.duckdb"
    published = len(publishers.records["NDF"])
    publishers.records["NDF"] += [dict(publishers.records["NDF"][0])] * 2
    load("bmrs", db, publishers, end=seed_end_date(), resources=["bmrs__ndf"])
    assert query(db, "select count(*) from raw.bmrs__ndf") == [(published,)]
