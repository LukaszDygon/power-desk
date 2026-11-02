import argparse
from datetime import timedelta
import json
from pathlib import Path

import pytest

from power_desk_elt.onboarding import profile


@pytest.fixture
def sample(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Two units per half hour; every fifth half hour republished an hour later; nested points per row."""
    monkeypatch.setattr(profile, "ONBOARDING_DIR", tmp_path / "onboarding")
    rows = [
        {
            "Time": f"2026-10-01T{h // 2:02d}:{30 * (h % 2):02d}:00Z",
            "Unit": unit,
            "Published": f"2026-09-30T{10 + revision}:00:00Z",
            "Value": h + revision,
            "Points": [{"i": 1}, {"i": 2}],
        }
        for h in range(48)
        for unit in ("A", "B")
        for revision in ((0, 1) if h % 5 == 0 else (0,))
    ]
    path = tmp_path / "sample.json"
    path.write_text(json.dumps({"data": rows}))
    return path


def run(path: Path, **options: object) -> dict:
    defaults = {"records": "data", "key": [], "time": None, "published": None, "available_from": None}
    return profile.profile(argparse.Namespace(name="pub__units", files=[str(path)], **{**defaults, **options}))


def test_nested_lists_become_child_tables_named_as_dlt_normalizes_them(sample: Path):
    result = run(sample)
    assert {t: info["rows"] for t, info in result["tables"].items()} == {"pub__units": 116, "pub__units__points": 232}
    assert [c["column_name"] for c in result["tables"]["pub__units"]["columns"]] == [
        "time",
        "unit",
        "published",
        "value",
    ]


def test_keys_tell_revisions_from_exact_repeats(sample: Path):
    by_time, by_publication = run(sample, key=["time,unit", "time,unit,published"])["keys"]
    assert (by_time["keys"], by_time["revised_keys"], by_time["exact_repeats"]) == (96, 20, 0)
    assert (by_publication["keys"], by_publication["revised_keys"]) == (116, 0)


def test_time_steps_publication_lag_and_volume(sample: Path):
    result = run(sample, time="time", published="published")
    assert result["time"]["steps"][0] == {"step": timedelta(minutes=30), "count": 47}
    assert result["lag_hours"]["publications_per_time"] == pytest.approx(58 / 48)
    assert result["volume"]["horizons"]["year"]["rows"] == pytest.approx(116 / (23.5 / 24) * 365)
    assert (profile.ONBOARDING_DIR / "pub" / "profile" / "pub__units" / "profile.md").exists()
