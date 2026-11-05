"""The acceptance run on a seed source: every criterion it can decide, from one fresh warehouse."""

from datetime import date
from pathlib import Path

import pytest

from power_desk_elt.ingest.seed.replay import SEED_START, replay
from power_desk_elt.onboarding import accept, profile


def test_acceptance_run_of_a_stream(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(accept, "ONBOARDING_DIR", tmp_path)
    monkeypatch.setattr(profile, "ONBOARDING_DIR", tmp_path)
    with replay():
        result = accept.accept("pvlive", date.fromisoformat(SEED_START), date(2024, 3, 7), label="seed")
    failed = [c["criterion"] for c in result["criteria"] if not c["passed"]]
    assert failed == []
    assert set(result["relations"]) == {"ods.ods_generation_actual", "marts.mart_generation_actual"}
    assert (tmp_path / "pvlive" / "acceptance" / "sample" / "marts.mart_generation_actual.csv").exists()
    assert (tmp_path / "pvlive" / "timings.jsonl").read_text().count("\n") == 1
