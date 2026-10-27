"""ENTSO-E definitions provider.

Kinds:
- `eic-functions/<slug>`: an EIC function (role of a code, e.g. `bidding-zone`) with its
  official definition, code type and markets, from the CIO's eicFunctions.csv. The same file
  is loaded as reference data by the `entsoe_eic` source.
"""

from __future__ import annotations

import re
from typing import Any

from power_desk.ingest.http import fetch_if_changed
from power_desk.ingest.sources.entsoe_eic import FUNCTIONS_URL, parse_csv

NAME = "entsoe"
LABELS = {"eic-functions": "ENTSO-E EIC function"}
FUNCTIONS_PAGE = "https://www.entsoe.eu/data/eic-functions/"


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def eic_functions(ids: list[str]) -> dict[str, dict[str, Any]]:
    text, _ = fetch_if_changed(FUNCTIONS_URL)
    grouped: dict[str, list[dict[str, str]]] = {}
    for row in parse_csv(text or "", ","):
        grouped.setdefault(slug(row["EIC Function"]), []).append(row)
    out = {}
    for ident in ids:
        rows = grouped.get(ident)
        if not rows:
            raise KeyError(f"{NAME}: no EIC function with slug {ident!r}")
        definitions = sorted(
            {r["Definition"].strip() for r in rows if r["Definition"].strip() not in ("", "Missing definition.")}
        )
        markets = sorted({r["Valid in Market"] for r in rows})
        types = sorted({r["EIC Type"] for r in rows})
        out[ident] = {
            "title": rows[0]["EIC Function"],
            "summary": " ".join(definitions) or "No definition published.",
            "reference": f"EIC code type {', '.join(types)}; market: {', '.join(markets)}",
            "url": FUNCTIONS_PAGE,
        }
    return out


def fetch(kind: str, ids: list[str]) -> dict[str, dict[str, Any]]:
    if kind == "eic-functions":
        return eic_functions(ids)
    raise KeyError(f"{NAME}: unknown kind {kind!r} (expected one of {sorted(LABELS)})")
