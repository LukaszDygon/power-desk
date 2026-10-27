"""Ingest job registry: which raw tables are refreshed together, and how often.

Each entry becomes a Dagster job (its dlt assets + every dbt model), a UTC cron schedule,
a cursor-lag asset check per raw table and a branch of the catch-up sensor. Group tables
by publication cadence; a new source usually adds its tables to an existing job or adds
one entry here. Raw tables are named after their dlt resources (`raw/<resource>`).
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class IngestJob:
    name: str
    schedule: str  # schedule name
    cron: str  # UTC
    tables: tuple[str, ...]  # dlt resource / raw table names, from any source
    # cursor-lag check warns beyond this (publication cadence + slack); None for snapshot sources
    max_cursor_lag_minutes: int | None
    description: str


INGEST_JOBS: tuple[IngestJob, ...] = (
    IngestJob(
        name="ingest_actuals",
        schedule="actuals_halfhourly",
        cron="5,35 * * * *",
        tables=("raw_fuelinst", "raw_indo", "raw_itsdo", "raw_pvlive_solar"),
        max_cursor_lag_minutes=120,
        description="Outturn data published every few minutes to half-hourly.",
    ),
    IngestJob(
        name="ingest_forecasts",
        schedule="forecasts_3h",
        cron="15 */3 * * *",
        tables=("raw_demand_forecast", "raw_windfor"),
        max_cursor_lag_minutes=360,
        description="Forecasts published a few times a day.",
    ),
    IngestJob(
        name="refresh_reference",
        schedule="reference_daily",
        cron="0 6 * * *",  # ENTSO-E regenerates the EIC files around midnight UTC
        tables=("raw_eic_codes", "raw_eic_functions", "raw_eic_issuing_offices"),
        max_cursor_lag_minutes=None,
        description="Reference data snapshots (scd2), skipped when the published file is unchanged.",
    ),
)

# Full-scope test run over the whole warehouse (completeness from the start date) + dbt docs.
NIGHTLY_CRON = "0 3 * * *"
