from datetime import date

import pytest

from power_desk.ingest.windows import DateRange, WindowPlan, plan_window


@pytest.mark.parametrize(
    ("start", "end", "max_days", "fetched_until", "expected"),
    [
        pytest.param("2024-03-01", None, 7, None, (date(2024, 3, 1), date(2024, 3, 8), True), id="capped"),
        pytest.param(
            "2024-03-08T10:00:00Z", None, 7, None, (date(2024, 3, 8), date(2024, 3, 10), False), id="reaches-today"
        ),
        pytest.param(
            "2024-02-01T10:00:00Z",
            None,
            2,
            "2024-02-20",
            (date(2024, 2, 20), date(2024, 2, 22), True),
            id="advances-past-publication-gap",
        ),
        pytest.param("2024-01-01", "2024-03-01", 7, None, (date(2024, 1, 1), date(2024, 2, 29), False), id="bounded"),
    ],
)
def test_plan_window(start, end, max_days, fetched_until, expected):
    first, last, capped = expected
    assert plan_window(start, end, max_days, fetched_until=fetched_until, today=date(2024, 3, 10)) == WindowPlan(
        DateRange(first, last), capped
    )


def test_date_range_chunks_cover_the_range_without_overlap():
    assert list(DateRange(date(2024, 3, 1), date(2024, 3, 5)).chunks(2)) == [
        DateRange(date(2024, 3, 1), date(2024, 3, 2)),
        DateRange(date(2024, 3, 3), date(2024, 3, 4)),
        DateRange(date(2024, 3, 5), date(2024, 3, 5)),
    ]


def test_date_ranges_overlap_when_they_share_a_day():
    march = DateRange(date(2024, 3, 1), date(2024, 3, 31))
    assert march.overlaps(DateRange(date(2024, 3, 31), date(2024, 4, 2)))
    assert not march.overlaps(DateRange(date(2024, 4, 1), date(2024, 4, 2)))
