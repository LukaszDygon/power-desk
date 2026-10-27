"""The warehouse admits one writer: assets that write it share a pool, and runs still hitting its lock are retried."""

from dagster import RetryRequested

from power_desk.warehouse import is_lock_error

WAREHOUSE_POOL = "duckdb_warehouse"
RUN_RETRIES = 5
RUN_RETRY_WAIT_SECONDS = 10


def retry_run_if_locked(error: BaseException | None) -> None:
    """Request a retry of the run when `error` is the warehouse lock; otherwise do nothing."""
    if is_lock_error(error):
        raise RetryRequested(max_retries=RUN_RETRIES, seconds_to_wait=RUN_RETRY_WAIT_SECONDS) from error
