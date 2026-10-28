"""Download one ENTSO-E month for the ingestion experiments and derive its 1%-revised copy.

    uv run python bench/ingestion/prepare.py

Needs Transparency Platform credentials (`.env`, see `.env.example`). Writes `data/month.csv`, as
published, and `data/month_revised.csv`: the same rows, about 1% of them re-published with a later
`UpdateTime(UTC)` and a changed value.
"""

from pathlib import Path

import duckdb

from power_desk.ingest.sources.entsoe_file_library import FileLibraryClient
import power_desk.settings  # noqa: F401  (loads .env, where dlt finds the credentials)

DATA = Path(__file__).resolve().parent / "data"
FOLDER = "AggregatedGenerationPerType_16.1.B_C_r3"
MONTH = f"2024_03_{FOLDER}.csv"
KEY = '"DateTime(UTC)", ResolutionCode, AreaCode, AreaTypeCode, ProductionType'


def main() -> None:
    DATA.mkdir(exist_ok=True)
    month = FileLibraryClient().download(FOLDER, MONTH, DATA / "month.csv")
    with duckdb.connect() as con:
        con.execute(f"create view m as select * from read_csv('{month}', sep='\t')")
        columns = [name for (name, *_rest) in con.execute("describe m").fetchall()]
        changed = f"hash({KEY}) % 100 = 0"
        revised = {
            "ActualGenerationOutput[MW]": f'case when {changed} then "ActualGenerationOutput[MW]" + 1 else "ActualGenerationOutput[MW]" end',
            "UpdateTime(UTC)": f'case when {changed} then "UpdateTime(UTC)" + interval 1 day else "UpdateTime(UTC)" end',
        }
        select = ", ".join(f'{revised.get(c, f"{chr(34)}{c}{chr(34)}")} as "{c}"' for c in columns)
        con.execute(f"copy (select {select} from m) to '{DATA / 'month_revised.csv'}' (delimiter '\t', header true)")


if __name__ == "__main__":
    main()
