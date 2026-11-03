from power_desk_elt.transform.dbt import DbtRun


def test_dbt_run_args_carry_the_loads_scope_and_full_refresh_for_builds_only():
    assert DbtRun(scope="all", full_refresh=True).args(["1"], "run-1") == [
        "build",
        "--vars",
        '{"dlt_load_ids": ["1"], "dlt_scope": "all", "orchestrator_run_id": "run-1"}',
        "--full-refresh",
    ]
    assert "--full-refresh" not in DbtRun(command="test", full_refresh=True).args([])


def test_dbt_run_args_select_nodes():
    assert DbtRun(command="test", select=("source:a.t+",)).args([])[-2:] == ["--select", "source:a.t+"]


def test_raw_tables_loaded_by_a_pipeline_or_its_resources_include_child_tables(tmp_path):
    import json

    from power_desk_elt.transform.dbt import downstream_of, raw_tables_loaded_by

    def source(pipeline, resource, name):
        meta = {"dlt": {"pipeline": pipeline, "resource": resource}}
        return {"source_name": pipeline, "name": name, "config": {"meta": meta}}

    manifest = tmp_path / "manifest.json"
    sources = [
        source("pub", "pub__units", "pub__units"),
        source("pub", "pub__units", "pub__units__points"),
        source("pub", "pub__prices", "pub__prices"),
        source("other", "other__x", "other__x"),
        {"source_name": "dlt", "name": "_dlt_loads", "config": {"meta": {}}},
    ]
    manifest.write_text(json.dumps({"sources": {f"source.p.{s['source_name']}.{s['name']}": s for s in sources}}))

    loaded = raw_tables_loaded_by(manifest, ["pub"], ["pub__units"])
    assert loaded == [("pub", "pub__units"), ("pub", "pub__units__points")]
    assert len(raw_tables_loaded_by(manifest, ["pub"])) == 3
    assert downstream_of(loaded) == ("source:pub.pub__units+", "source:pub.pub__units__points+")
