"""Ingest jobs: which raw tables are refreshed together, how often, and the Dagster jobs built from them.

Each ingest job materializes its raw tables and then every dbt model (marts process only pending
loads, so untouched ones are cheap no-ops). Group raw tables by publication cadence; every raw
table belongs to exactly one ingest job.
"""

from dataclasses import dataclass

from dagster import AssetKey, AssetSelection, RunConfig, define_asset_job

from power_desk.ingest.pipeline import DATASET_NAME, make_source
from power_desk.ingest.registry import SOURCES
from power_desk.orchestration.dbt_assets import TransformConfig, dbt_models


@dataclass(frozen=True)
class IngestJob:
    name: str
    schedule: str
    cron: str  # UTC
    tables: tuple[str, ...]  # raw tables (dlt resources), from any source
    description: str

    @property
    def asset_keys(self) -> list[AssetKey]:
        return [AssetKey([DATASET_NAME, table]) for table in self.tables]


INGEST_JOBS = (
    IngestJob(
        "ingest_actuals",
        "actuals_halfhourly",
        "5,35 * * * *",
        ("bmrs__fuelinst", "bmrs__indo", "bmrs__itsdo", "pvlive__solar"),
        description="Outturn published every few minutes to half-hourly.",
    ),
    IngestJob(
        "ingest_forecasts",
        "forecasts_3h",
        "15 */3 * * *",
        ("bmrs__ndf", "bmrs__windfor"),
        description="Forecasts published a few times a day.",
    ),
    IngestJob(
        "ingest_daily_exports",
        "daily_exports_6h",
        "50 */6 * * *",
        (
            "entsoe__actual_total_load",
            "entsoe__day_ahead_total_load_forecast",
            "entsoe__generation_per_type",
            "entsoe__wind_solar_forecast",
        ),
        description="Monthly files re-exported daily around 05:40 UTC; unchanged files are skipped.",
    ),
    IngestJob(
        "refresh_reference",
        "reference_daily",
        "0 6 * * *",
        ("entsoe_eic__codes", "entsoe_eic__functions", "entsoe_eic__issuing_offices"),
        description="Reference snapshots (scd2), skipped while unchanged.",
    ),
)
NIGHTLY_CRON = "0 3 * * *"


def check_every_raw_table_scheduled_once() -> None:
    """Fails unless every raw table loaded by a source is in exactly one ingest job."""
    scheduled = [table for job in INGEST_JOBS for table in job.tables]
    loaded = {table for name in SOURCES for table in make_source(name).resources}
    if len(scheduled) != len(set(scheduled)) or set(scheduled) != loaded:
        raise ValueError(
            f"raw tables must be in exactly one ingest job; scheduled {sorted(scheduled)}, loaded {sorted(loaded)}"
        )


ALL_DBT = AssetSelection.assets(dbt_models)

ingest_jobs = {
    job.name: define_asset_job(
        job.name,
        selection=AssetSelection.assets(*job.asset_keys) | ALL_DBT,
        description=f"{job.description} Then dbt, for the pending loads.",
    )
    for job in INGEST_JOBS
}
dbt_nightly = define_asset_job(
    "dbt_nightly",
    selection=ALL_DBT,
    config=RunConfig(ops={"dbt_models": TransformConfig(scope="all", command="test", docs=True)}),
    description="Every dbt test over the whole warehouse (completeness from the start date), then dbt docs.",
)
backfill = define_asset_job(
    "backfill",
    selection=AssetSelection.all(),
    description="Configurable ingest + dbt: ops.<source>_ingest.config.{start_date,end_date,refresh}; "
    "ops.dbt_models.config.scope=all tests the full range.",
)
JOBS = [*ingest_jobs.values(), dbt_nightly, backfill]
