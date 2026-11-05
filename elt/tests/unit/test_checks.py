from datetime import UTC, datetime, timedelta

from dagster import AssetCheckSeverity
import pytest

from power_desk_elt.orchestration.checks import judge

ACTUALS = {"warn_after": {"count": 2, "period": "hour"}, "error_after": {"count": 6, "period": "hour"}}


@pytest.mark.parametrize(
    ("age", "judged"),
    [
        (timedelta(hours=1), (True, AssetCheckSeverity.WARN)),
        (timedelta(hours=3), (False, AssetCheckSeverity.WARN)),
        (timedelta(hours=7), (False, AssetCheckSeverity.ERROR)),
        (None, (False, AssetCheckSeverity.ERROR)),
    ],
)
def test_freshness_warns_past_warn_after_and_errors_past_error_after(age, judged):
    result = judge(datetime.now(UTC) - age if age is not None else None, ACTUALS)
    assert (result.passed, result.severity) == judged
