from power_desk.transform.dbt import DbtRun


def test_dbt_run_args_carry_the_loads_scope_and_full_refresh_for_builds_only():
    assert DbtRun(scope="all", full_refresh=True).args(["1"], "run-1") == [
        "build",
        "--vars",
        '{"dlt_load_ids": ["1"], "dlt_scope": "all", "orchestrator_run_id": "run-1"}',
        "--full-refresh",
    ]
    assert "--full-refresh" not in DbtRun(command="test", full_refresh=True).args([])
