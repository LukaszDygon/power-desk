"""Publishers replaced by the seed: Elexon / PVLive / NESO APIs, EIC and BM unit files and the ENTSO-E File Library."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
import gzip
import hashlib
from pathlib import Path
import re
from typing import Any
from unittest.mock import patch

from power_desk_elt.ingest import http
from power_desk_elt.ingest.seed import synthetic
from power_desk_elt.ingest.sources import bmrs, entsoe_eic, neso
from power_desk_elt.ingest.sources.entsoe_file_library import ExportFile, FileLibraryClient, export_file
from power_desk_elt.settings import SEED_DIR

SEED_START = "2024-03-01"
SEED_DAYS = 7
# reference files: url -> recorded file under elt/seed/
REFERENCE_FILES = {
    entsoe_eic.CODES_URL: "entsoe_eic/CIO_extraction-all-eic-codes.csv",
    entsoe_eic.FUNCTIONS_URL: "entsoe_eic/eicFunctions.csv",
    entsoe_eic.ISSUING_OFFICES_URL: "entsoe_eic/eic-issuing-offices.html",
    bmrs.BMUNITS_URL: "bmrs/bmunits.json",
}
# the parts of a NESO upload query (`neso.upload_query`) the replay answers
NESO_QUERY = re.compile(
    r"from \"(?P<resource_id>[^\"]+)\" .* >= '(?P<first>[^']+)' .* < '(?P<end>[^']+)' .* offset (?P<offset>\d+)"
)


@dataclass
class SeedPublishers:
    """Payloads served per publisher; tests may change them between runs."""

    records: dict[str, list[dict[str, Any]]]  # Elexon dataset code / "REMIT" / "PVLIVE" / NESO raw table -> records
    files: dict[str, str]  # url -> published file text
    exports: dict[str, dict[str, tuple[str, bytes]]]  # folder -> file name -> (lastUpdatedTimestamp, content)
    requests: list[str] = field(default_factory=list)

    @classmethod
    def from_seed(
        cls, seed_dir: Path = SEED_DIR, start_date: str = SEED_START, num_days: int = SEED_DAYS
    ) -> SeedPublishers:
        exports: dict[str, dict[str, tuple[str, bytes]]] = {}
        for path in sorted((seed_dir / "entsoe").glob("*.csv.gz")):
            name = path.name.removesuffix(".gz")
            folder = name.split("_", 2)[2].removesuffix(".csv")
            exports.setdefault(folder, {})[name] = ("seed", gzip.decompress(path.read_bytes()))
        files = {url: (seed_dir / name).read_text(encoding="utf-8") for url, name in REFERENCE_FILES.items()}
        return cls(synthetic.generate(start_date, num_days), files, exports)

    def fetch_json(self, url: str, params: dict[str, Any] | None = None) -> Any:
        self.requests.append(url)
        params = params or {}
        if "pvlive" in url:
            rows = [r for r in self.records["PVLIVE"] if params["start"] <= r["datetime_gmt"] <= params["end"]]
            return {"meta": ["pes_id", "datetime_gmt", "generation_mw"], "data": [list(r.values()) for r in rows]}
        if url == neso.SQL_URL:
            return {"result": {"records": self.neso_page(params["sql"])}}
        if url == bmrs.REMIT_LIST_URL:
            listed = (r for r in self.records["REMIT"] if params["from"] <= r["publishTime"] <= params["to"])
            keys = ("id", "mrid", "revisionNumber", "createdTime", "publishTime")
            return {"data": [{key: r[key] for key in keys} for r in listed]}
        if url == bmrs.REMIT_URL:
            ids = set(params["messageId"])
            return {"data": [r for r in self.records["REMIT"] if r["id"] in ids]}
        dataset = next(dataset for dataset in bmrs.DATASETS if url.endswith(f"/{dataset.code}"))
        first, last = (params[name] for name in dataset.time_filter)
        return {"data": [r for r in self.records[dataset.code] if first <= r[dataset.cursor] <= last]}

    def neso_page(self, sql: str) -> list[dict[str, Any]]:
        query = NESO_QUERY.search(sql)
        assert query, sql
        dataset = next(dataset for dataset in neso.DATASETS if dataset.resource_id == query["resource_id"])
        rows = sorted(
            (r for r in self.records[dataset.resource] if query["first"] <= r[neso.UPLOAD_TIME] < query["end"]),
            key=lambda r: r[neso.UPLOAD_TIME],
        )
        offset = int(query["offset"])
        return [{"_id": offset + i, **row} for i, row in enumerate(rows[offset : offset + neso.PAGE_ROWS], 1)]

    def fetch_if_changed(self, url: str, etag: str | None = None) -> tuple[str | None, dict[str, str]]:
        self.requests.append(url)
        text = self.files[url]
        tag = hashlib.sha256(text.encode()).hexdigest()
        return (None, {"etag": tag}) if etag == tag else (text, {"etag": tag})

    def list_folder(self, folder: str) -> list[ExportFile]:
        listed = [
            {"name": name, "lastUpdatedTimestamp": updated, "size": len(content)}
            for name, (updated, content) in self.exports.get(folder, {}).items()
        ]
        return [file for item in listed if (file := export_file(item))]

    def download(self, folder: str, filename: str, target: Path) -> Path:
        self.requests.append(f"{folder}/{filename}")
        target.write_bytes(self.exports[folder][filename][1])
        return target


@contextmanager
def replay(publishers: SeedPublishers | None = None) -> Iterator[SeedPublishers]:
    """Serve `publishers` (default: the seed) in place of every publisher."""
    publishers = publishers or SeedPublishers.from_seed()
    with (
        patch.object(http, "fetch_json", publishers.fetch_json),
        patch.object(http, "fetch_if_changed", publishers.fetch_if_changed),
        patch.object(
            FileLibraryClient, "list_folder", lambda _, *args, **kwargs: publishers.list_folder(*args, **kwargs)
        ),
        patch.object(FileLibraryClient, "download", lambda _, *args: publishers.download(*args)),
    ):
        yield publishers
