"""The landing zone: what publishers push, appended by dlt to a filesystem destination as it arrives.

Each `land` call is one dlt load of rows grouped by table, stored as published in dlt's default files
(gzipped JSONL) at `<landing url>/<source>/<table>/<load id>.<file id>.jsonl.gz`. dlt keeps the pipeline
state in the landing zone, so the working directory is disposable.

Services acknowledge a message to its publisher only after `land` returns, so delivery is at least once: a
crash in between re-delivers it, and loads into the warehouse keep one row per natural key. Services never
write the warehouse: DuckDB allows one writer, which stays the orchestrator.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import threading
from typing import Any

import dlt

from power_desk_services.settings import landing_url, pipelines_dir

Rows = Mapping[str, Sequence[dict[str, Any]]]


class Landing:
    """Lands rows of `source` (the dlt pipeline, schema and landing folder name); safe to call from threads."""

    def __init__(self, source: str, url: str | None = None) -> None:
        self.pipeline = dlt.pipeline(
            pipeline_name=source,
            destination=dlt.destinations.filesystem(bucket_url=url or landing_url()),
            dataset_name=source,
            pipelines_dir=str(pipelines_dir()),
        )
        self._lock = threading.Lock()

    def land(self, rows: Rows) -> None:
        """Append `rows` (table -> rows) in one load, skipping empty tables. Raises if the load fails."""
        resources = [dlt.resource(list(items), name=table) for table, items in rows.items() if items]
        if resources:
            with self._lock:
                self.pipeline.run(resources)
