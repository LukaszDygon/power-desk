-- settlement_period_to_utc / settlement_periods_in_day / utc_to_settlement_* on GMT, BST,
-- the 46-period spring day and the 50-period autumn day. Returns rows only on mismatch.
with cases(settlement_date, settlement_period, expected_utc, expected_periods) as (
    values
        (date '2024-01-15', 1,  timestamp '2024-01-15 00:00:00', 48),
        (date '2024-07-01', 1,  timestamp '2024-06-30 23:00:00', 48),
        (date '2024-07-01', 26, timestamp '2024-07-01 11:30:00', 48),
        (date '2024-03-31', 3,  timestamp '2024-03-31 01:00:00', 46),
        (date '2024-03-31', 46, timestamp '2024-03-31 22:30:00', 46),
        (date '2024-10-27', 1,  timestamp '2024-10-26 23:00:00', 50),
        (date '2024-10-27', 50, timestamp '2024-10-27 23:30:00', 50)
),
computed as (
    select
        *,
        {{ settlement_period_to_utc('settlement_date', 'settlement_period') }} as actual_utc,
        {{ settlement_periods_in_day('settlement_date') }} as actual_periods,
        {{ utc_to_settlement_date("timezone('UTC', expected_utc)") }} as roundtrip_date,
        {{ utc_to_settlement_period("timezone('UTC', expected_utc)") }} as roundtrip_period
    from cases
)
select *
from computed
where actual_utc <> expected_utc
   or actual_periods <> expected_periods
   or roundtrip_date <> settlement_date
   or roundtrip_period <> settlement_period
