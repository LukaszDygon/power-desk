"""Load the seed week into a warehouse through every source's pipeline."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from dlt.common.pipeline import LoadInfo

from power_desk.ingest.pipeline import make_pipeline, make_source, run
from power_desk.ingest.registry import SOURCES
from power_desk.ingest.seed.replay import SEED_DAYS, SEED_START, SeedPublishers, replay


def seed_end_date() -> str:
    return (date.fromisoformat(SEED_START) + timedelta(days=SEED_DAYS - 1)).isoformat()


def load_seed(db_path: Path | str | None = None, publishers: SeedPublishers | None = None) -> list[LoadInfo]:
    """A bounded backfill of the seed week per source, served by the replayed publishers."""
    with replay(publishers):
        return [
            run(
                make_pipeline(name, db_path, schemas_dir=None),
                make_source(name, spec.window(SEED_START, seed_end_date())),
            )
            for name, spec in SOURCES.items()
        ]
