"""Publishers replaced by the seed: Elexon / PVLive / NESO APIs, EIC, BM unit and REPD files, the
ENTSO-E File Library and the ECMWF open-data portal."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
import gzip
import hashlib
from pathlib import Path
import re
from typing import Any
from unittest.mock import patch

import duckdb
import pyarrow as pa

from power_desk_elt.ingest import http
from power_desk_elt.ingest.seed import synthetic
from power_desk_elt.ingest.sources import bmrs, desnz_repd, ecmwf, entsoe_eic, neso
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
REPD_URL = "https://assets.publishing.service.gov.uk/media/seed/REPD_Publication_seed.csv"
REPD_FILE = "REPD_Publication_seed.csv"
# a step file on the ECMWF open-data portal (`ecmwf.Dataset.file_url`)
ECMWF_FILE = re.compile(
    r"/(?P<model>[^/]+)/(?P<resolution>[^/]+)/(?P<stream>[^/]+)/(?P<run>\d{10})0000-(?P<step>\d+)h-[^.]+\.(?P<ext>index|grib2)$"
)


# the last days of the seed week serve ECMWF runs: a run is ~56k rows, and a day's runs cover what the tests
# need (a run loaded, a later one read next, a reload)
ECMWF_SEED_DAYS = 1


@dataclass
class SeedPublishers:
    """Payloads served per publisher; tests may change them between runs."""

    records: dict[str, list[dict[str, Any]]]  # Elexon dataset code / "REMIT" / "PVLIVE" / NESO raw table -> records
    files: dict[str, str]  # url -> published file text
    exports: dict[str, dict[str, tuple[str, bytes]]]  # folder -> file name -> (lastUpdatedTimestamp, content)
    requests: list[str] = field(default_factory=list)
    ecmwf_runs: set[datetime] = field(default_factory=set)  # runs the portal serves (synthetic step files)

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
        files[REPD_URL] = (seed_dir / "desnz_repd" / REPD_FILE).read_bytes().decode(desnz_repd.REPD.encoding)
        first = date.fromisoformat(start_date)
        runs = {
            datetime(day.year, day.month, day.day, hour, tzinfo=UTC)
            for day in (first + timedelta(days=n) for n in range(max(0, num_days - ECMWF_SEED_DAYS), num_days))
            for dataset in ecmwf.DATASETS
            for hour in dataset.steps
        }
        return cls(synthetic.generate(start_date, num_days), files, exports, ecmwf_runs=runs)

    def fetch_json(self, url: str, params: dict[str, Any] | None = None) -> Any:
        self.requests.append(url)
        params = params or {}
        if url == desnz_repd.CONTENT_URL:
            return {"details": {"attachments": [{"content_type": "text/csv", "url": REPD_URL}]}}
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
        """The source's query run on the datastore resources, each with the datastore's own columns."""
        with duckdb.connect() as con:
            for dataset in neso.DATASETS:
                rows = [
                    {"_id": n, "_full_text": " ".join(f"'{value}'" for value in row.values()), **row}
                    for n, row in enumerate(self.records[dataset.resource], 1)
                ]
                con.register(dataset.resource_id, pa.Table.from_pylist(rows))
            result = con.execute(sql)
            columns = [column[0] for column in result.description or ()]
            return [dict(zip(columns, row, strict=True)) for row in result.fetchall()]

    def fetch_if_changed(
        self, url: str, etag: str | None = None, encoding: str = "utf-8-sig"
    ) -> tuple[str | None, dict[str, str]]:
        self.requests.append(url)
        text = self.files[url]
        tag = hashlib.sha256(text.encode()).hexdigest()
        return (None, {"etag": tag}) if etag == tag else (text, {"etag": tag})

    def fetch_bytes(self, url: str, byte_range: tuple[int, int] | None = None) -> bytes | None:
        """An ECMWF step file (index or GRIB2, or a byte range of it) of a served run; None otherwise."""
        self.requests.append(url)
        match = ECMWF_FILE.search(url)
        assert match, url
        run = datetime.strptime(match["run"], "%Y%m%d%H").replace(tzinfo=UTC)
        if run not in self.ecmwf_runs:
            return None
        index, content = synthetic.ecmwf_step_file(match["stream"], run, int(match["step"]), match["model"])
        if match["ext"] == "index":
            return index.encode()
        return content[byte_range[0] : byte_range[1] + 1] if byte_range else content

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
        patch.object(http, "fetch_bytes", publishers.fetch_bytes),
        patch.object(
            FileLibraryClient, "list_folder", lambda _, *args, **kwargs: publishers.list_folder(*args, **kwargs)
        ),
        patch.object(FileLibraryClient, "download", lambda _, *args: publishers.download(*args)),
    ):
        yield publishers
