"""Publishers replaced by the seed: Elexon / PVLive APIs, EIC files and the ENTSO-E File Library."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
import gzip
import hashlib
from pathlib import Path
from typing import Any
from unittest.mock import patch

from power_desk.ingest import http
from power_desk.ingest.seed import synthetic
from power_desk.ingest.sources import entsoe_eic
from power_desk.ingest.sources.entsoe_file_library import ExportFile, FileLibraryClient, export_file
from power_desk.settings import DATA_DIR

SEED_DIR = DATA_DIR / "seed"
SEED_START = "2024-03-01"
SEED_DAYS = 7
EIC_FILES = {
    entsoe_eic.CODES_URL: "CIO_extraction-all-eic-codes.csv",
    entsoe_eic.FUNCTIONS_URL: "eicFunctions.csv",
    entsoe_eic.ISSUING_OFFICES_URL: "eic-issuing-offices.html",
}


@dataclass
class SeedPublishers:
    """Payloads served per publisher; tests may change them between runs."""

    records: dict[str, list[dict[str, Any]]]  # Elexon dataset code / "PVLIVE" -> API records
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
        files = {url: (seed_dir / "entsoe_eic" / name).read_text(encoding="utf-8") for url, name in EIC_FILES.items()}
        return cls(synthetic.generate(start_date, num_days), files, exports)

    def fetch_json(self, url: str, params: dict[str, Any] | None = None) -> Any:
        self.requests.append(url)
        params = params or {}
        if "pvlive" in url:
            rows = [r for r in self.records["PVLIVE"] if params["start"] <= r["datetime_gmt"] <= params["end"]]
            return {"meta": ["pes_id", "datetime_gmt", "generation_mw"], "data": [list(r.values()) for r in rows]}
        first, last = params["publishDateTimeFrom"], params["publishDateTimeTo"]
        return {"data": [r for r in self.records[url.rsplit("/", 1)[1]] if first <= r["publishTime"] <= last]}

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
