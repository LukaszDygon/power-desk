"""Every source loaded into the warehouse. To add one, implement `sources/<source>.py` with a `SPEC`."""

from __future__ import annotations

from power_desk_elt.ingest.sources import bmrs, entsoe, entsoe_eic, neso, pvlive
from power_desk_elt.ingest.spec import SourceSpec

SOURCES: dict[str, SourceSpec] = {
    spec.name: spec for spec in (bmrs.SPEC, pvlive.SPEC, entsoe.SPEC, entsoe_eic.SPEC, neso.SPEC)
}
