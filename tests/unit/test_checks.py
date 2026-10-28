from datetime import UTC, datetime, timedelta

from dagster import AssetCheckSeverity

from power_desk.orchestration.checks import judge

ACTUALS = {"warn_after": {"count": 2, "period": "hour"}, "error_after": {"count": 6, "period": "hour"}}


def judged(age: timedelta | None) -> tuple[bool, AssetCheckSeverity]:
    result = judge(datetime.now(UTC) - age if age is not None else None, ACTUALS)
    return result.passed, result.severity


def test_freshness_warns_past_warn_after_and_errors_past_error_after():
    assert judged(timedelta(hours=1))[0]
    assert judged(timedelta(hours=3)) == (False, AssetCheckSeverity.WARN)
    assert judged(timedelta(hours=7)) == (False, AssetCheckSeverity.ERROR)
    assert judged(None) == (False, AssetCheckSeverity.ERROR)
