"""Cursor-lag checks: warn when a stream's newest loaded value is older than its job's threshold."""

from dagster import AssetCheckExecutionContext, AssetCheckResult, AssetCheckSeverity, AssetKey, asset_check

from power_desk.orchestration.jobs import INGEST_JOBS
from power_desk.orchestration.runs import latest_metadata


def cursor_lag_check(key: AssetKey, threshold: int):
    @asset_check(asset=key, name="cursor_lag", description=f"dlt cursor lags now by at most {threshold} min")
    def check(context: AssetCheckExecutionContext) -> AssetCheckResult:
        metadata = latest_metadata(context.instance, key)
        lag = metadata.get("cursor_lag_minutes")
        lag_minutes = float(lag) if isinstance(lag, int | float) else None  # None: no cursor recorded yet
        return AssetCheckResult(
            passed=lag_minutes is not None and lag_minutes <= threshold,
            severity=AssetCheckSeverity.WARN,
            metadata={
                "cursor_lag_minutes": lag_minutes,
                "threshold_minutes": threshold,
                "cursor_last_value": str(metadata.get("cursor_last_value", "")),
            },
        )

    return check


CHECKS = [
    cursor_lag_check(key, job.max_cursor_lag_minutes)
    for job in INGEST_JOBS
    if job.max_cursor_lag_minutes is not None
    for key in job.asset_keys
]
