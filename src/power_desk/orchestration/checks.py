"""Two freshness checks per raw table, judged against its `freshness` preset in catalog/definitions
(the thresholds its dbt source freshness uses too): a WARN past `warn_after`, an ERROR past `error_after`.

- `recently_fetched`: the table's newest dlt load (`_dlt_load_id`) is recent. Incremental loads hold
  only data after the cursor, so this shows ingestion is delivering; a re-delivered copy (a re-exported
  file) counts as well.
- `recent_data`: the newest data by its own datetime, the dlt cursor, is recent, so re-delivered copies
  and backfills of old data do not count. The cursor is the publication time for Elexon (actuals and
  forecasts), the half hour for PVLive and the update time for ENTSO-E, whose revisions and re-forecasts
  of earlier periods are new data.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

from dagster import AssetCheckExecutionContext, AssetCheckResult, AssetCheckSeverity, AssetKey, asset_check

from power_desk import warehouse
from power_desk.catalog.definitions_loader import load_definitions
from power_desk.ingest.pipeline import DATASET_NAME
from power_desk.orchestration.runs import latest_metadata
from power_desk.orchestration.warehouse_lock import WAREHOUSE_POOL

PERIODS = {"minute": "minutes", "hour": "hours", "day": "days"}


def limit(threshold: dict[str, Any]) -> timedelta:
    """A dbt freshness threshold (`{count, period}`) as a duration."""
    return timedelta(**{PERIODS[threshold["period"]]: threshold["count"]})


def judge(newest: datetime | None, freshness: dict[str, Any]) -> AssetCheckResult:
    age = datetime.now(UTC) - newest if newest else None
    return AssetCheckResult(
        passed=age is not None and age <= limit(freshness["warn_after"]),
        severity=AssetCheckSeverity.ERROR
        if age is None or age > limit(freshness["error_after"])
        else AssetCheckSeverity.WARN,
        metadata={"newest": newest.isoformat() if newest else None, "freshness": freshness},
    )


def cursor_time(cursor: Any) -> datetime | None:
    """A dlt cursor value (ISO timestamp, UTC when naive)."""
    if not cursor:
        return None
    value = datetime.fromisoformat(str(cursor).replace("Z", "+00:00"))
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def freshness_checks(table: str, freshness: dict[str, Any]) -> list:
    key = AssetKey([DATASET_NAME, table])

    @asset_check(asset=key, name="recently_fetched", pool=WAREHOUSE_POOL, description="Newest dlt load is recent.")
    def recently_fetched() -> AssetCheckResult:
        with warehouse.connect() as con:
            if table not in warehouse.base_table_names(con, DATASET_NAME):
                return judge(None, freshness)
            [(load_id,)] = con.execute(f"select max(_dlt_load_id) from {DATASET_NAME}.{table}").fetchall()
        return judge(datetime.fromtimestamp(float(load_id), UTC) if load_id else None, freshness)

    @asset_check(asset=key, name="recent_data", description="Newest data, by its own datetime (dlt cursor), is recent.")
    def recent_data(context: AssetCheckExecutionContext) -> AssetCheckResult:
        return judge(cursor_time(latest_metadata(context.instance, key).get("cursor_last_value")), freshness)

    return [recently_fetched, recent_data]


CHECKS = [
    check
    for table, definition in load_definitions()["tables"].items()
    if definition.get("freshness")
    for check in freshness_checks(table, definition["freshness"])
]
