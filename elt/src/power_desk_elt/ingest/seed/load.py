"""Load the seed week into a warehouse through every source's pipeline."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date, timedelta
from pathlib import Path
import tempfile

from dlt.common.pipeline import LoadInfo

from power_desk_elt.ingest.pipeline import make_pipeline, make_source, run
from power_desk_elt.ingest.registry import SOURCES
from power_desk_elt.ingest.seed.replay import SEED_DAYS, SEED_START, SeedPublishers, replay
from power_desk_elt.transform.dbt import run_dbt


def seed_end_date() -> str:
    return (date.fromisoformat(SEED_START) + timedelta(days=SEED_DAYS - 1)).isoformat()


def build_references(
    sources: Iterable[str], db_path: Path | str | None = None, target_path: Path | str | None = None
) -> None:
    """dbt builds the relations `sources` read by reference (`SourceSpec.references`) and what they need, without
    tests (the build that follows the loads runs them), into its own target directory by default."""
    models = sorted({ref.split(".")[-1] for name in sources for ref in SOURCES[name].references})
    if not models:
        return
    with tempfile.TemporaryDirectory() as scratch:
        args = ["build", "--exclude-resource-type", "test", "unit_test", "--select", *(f"+{m}" for m in models)]
        if run_dbt(args, db_path, target_path or scratch) != 0:
            raise RuntimeError(f"dbt could not build {models}, which {sorted(sources)} read")


def load_seed(
    db_path: Path | str | None = None, publishers: SeedPublishers | None = None, sources: Iterable[str] | None = None
) -> list[LoadInfo]:
    """A bounded backfill of the seed week per source (default: every source), served by the replayed publishers.
    Sources reading warehouse relations by reference load last, once dbt has built them."""
    names = list(sources or SOURCES)
    referencing = [name for name in names if SOURCES[name].references]
    loads = []
    with replay(publishers):
        for name in [*(name for name in names if name not in referencing), *referencing]:
            if referencing and name == referencing[0]:
                build_references(referencing, db_path)
            pipeline = make_pipeline(name, db_path, schemas_dir=None)
            loads.append(run(pipeline, make_source(name, SOURCES[name].window(SEED_START, seed_end_date()))))
    return loads
