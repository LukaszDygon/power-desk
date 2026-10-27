"""Every source loaded into the warehouse. To add one, implement `sources/<source>.py` with a `SPEC`."""

from __future__ import annotations

from power_desk.ingest.sources import bmrs, entsoe, entsoe_eic, pvlive
from power_desk.ingest.spec import SourceSpec

SOURCES: dict[str, SourceSpec] = {spec.name: spec for spec in (bmrs.SPEC, pvlive.SPEC, entsoe.SPEC, entsoe_eic.SPEC)}
