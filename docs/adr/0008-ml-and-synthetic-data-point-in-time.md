# ADR 0008: ML and synthetic data: own schemas, inputs as the system held them, runs by id

- **Status:** accepted, 2026-11-19
- **Details:** [architecture](../architecture.md), [hosting](../hosting.md) ([ADR 0007](0007-one-dedicated-server-with-k3s.md))
- **Proof of concept:** GB wind and solar generation from ECMWF weather, shown beside Elexon's and the actuals

## Context

- **Wanted:** our own forecasts, starting with GB wind and solar, on the dashboard beside publishers' data,
  never mistaken for it.
- **Reproducible without copies:** model B, built later, must be comparable with model A on the same
  inputs. The inputs are re-queried as the system held them at a past time; nothing is snapshotted to files.
- **A proof of concept:** a few days of history will do for now; the design must take years.

## Decision

### Where ML and synthetic data live

- **Schema `ml`:** per model, `ml.ods_<model>_<entity>` (every issue, native resolution) and
  `ml.mart_<model>_<entity>` (hourly, by the shared mart macro), plus the run and version tables.
- **Schema `synthetic`:** a table per relation it stands in for (`synthetic.ods_generation_actual`,
  `synthetic.mart_generation_forecast`), plus `synthetic.generator_runs`. It exists in dev and test
  warehouses only.
- **Never in publishers' relations:** `ods`, `marts` and `raw.<publisher>__*` hold only published data.
- **Loaded the one way:** models and generators write files, and dlt loads them (`raw.ml__*`,
  `raw.synthetic__*`).
- **One new project, `ml/`** (`power_desk_ml`): training, scoring and evaluation, in a second Dagster code
  location. It only reads the warehouse.

### System time, not publication time

- **What matters is when the system held a value:** runs and comparisons use system time. Publication
  times stay columns, for analysing outputs.
- **Raw: dlt's built-in `scd2`.** `_dlt_valid_from` and `_dlt_valid_to` come from the load, and
  `_dlt_load_id` names it.
- **FUELINST and WINDFOR move to `scd2`:** dlt's config only, with `merge_key` set to their natural keys,
  ending their `delete-insert` deviation.
- **Marts the models read: dbt's built-in snapshots.** `marts.mart_<entity>_versions` keeps each version
  with `dbt_valid_from` and `dbt_valid_to`; the mart itself stays current.
- **One provenance column per version:** `_dbt_invocation_id`. It names the dbt run that wrote the version.
- **Runs registered once:** `dlt_meta.dbt_invocations` holds the start, the end, the Dagster run and the
  commit for each invocation. `dlt_load_audit` already maps the loads to invocations.
- **Models read marts only:** for the time ranges they need, as the system held them at a given `as_of`.

### Point-in-time inputs

- **As of a time:** a version is visible at `as_of` when `dbt_valid_from <= as_of` and `dbt_valid_to` is
  null or later.
- **Features per issue:** each issue time reads the mart versions held at that time, so the training rows
  reproduce what scoring would have seen.
- **Targets as of training:** actuals are read as held at the training's `as_of`.
- **Feature sets as table macros:** `ml.features_<model>(as_of, issue_from, issue_to)`, built by dbt over the
  mart versions, and queryable by anyone.
- **A training frame is a query, not a file:** its key is the feature set's dbt checksum, `as_of` and the
  issue window. A row-hash fingerprint proves that a re-query returns the same rows.
- **Comparing A and B:** B's backtest runs with A's `as_of` and window, on A's feature set or its own.

### Runs by id

- **Rows carry one id,** never the model's details: `ml.ods_*` and `ml.mart_*` rows carry `_ml_run_id`, and
  synthetic rows carry `_synthetic_run_id`. dlt's `_dlt_load_id` comes too.
- **`ml.model_runs`:** one row per run (training, backtest or scoring), with its kind, its model version,
  its `as_of`, its issue window, its Dagster run id, and its start and end.
- **`ml.model_versions`:** one row per version, with the feature set's checksum, the training run, the
  frame's fingerprint, the code commit, the parameters, the seed and the metrics.
- **`ml.champions`:** the champion of each model, versioned (`scd2`), so the one in use at any time can be
  queried.
- **`synthetic.generator_runs`:** the scenario, generator, version, seed and relation stood in for.
- **Only the model is stored:** `data/models/<model>/<version>/` holds the fitted model and its card, backed
  up nightly; training data is never stored.

### Proof of concept: GB wind and solar

- **Targets:** transmission-metered wind (FUELINST) and national solar (PVLive), hourly, 1-48 h ahead.
- **Models:** `gb_wind` and `gb_solar`, LightGBM on CPU, giving `ml.mart_gb_wind_generation_forecast` and
  `ml.mart_gb_solar_generation_forecast`.
- **Inputs:** `mart_weather_forecast`, `mart_generation_actual` and `mart_generation_forecast` (WINDFOR),
  through their versions, with REPD capacity (`dim_site`), solar geometry and calendar.
- **History:** from the day the mart versions start, on an expanding window. The first models train on
  days of data.
- **Benchmarks:** persistence, climatology and WINDFOR (wind).
- **Dashboard:** two widgets (`create-widget`), *wind and solar: actual, ours, Elexon's* and *forecast error
  by source*. They read the publishers' marts and `ml.mart_*`, joined to `ml.model_runs` for labels.

### Synthetic data

- **Statistical, seeded, declared:** a scenario is a committed YAML file (generator, seed, parameters); its
  rows are rebuilt by loading, never committed.
- **Used through the inputs' names:** a feature set reads `synthetic` in place of `marts` for a scenario, so
  ML tests run the production SQL.
- **Uses:** known-signal data (the training pipeline recovers a stated skill) and a leakage canary (a
  feature from the future must give no skill).
- **Pipeline load and edge-case tests** replay generated payloads only into a warehouse file of their own
  (`warehouse_synthetic_<scenario>.duckdb`), never into dev or prod.
- **Not for training:** models learn only from published data.

### Model maintenance

- **Scoring:** a sensor on each build of `mart_weather_forecast`, with `as_of` set to the scoring time.
  Missing inputs mean no forecast, never an imputed one.
- **Training:** weekly while history is short, then monthly, plus on demand. Each training gives a
  challenger version.
- **Promotion by backtest:** a challenger replaces the champion if it beats both the champion and the
  baselines on the same `as_of` and window. In the proof of concept, a person launches the promotion.
- **Monitoring:** daily asset checks on live error against the backtest, skill against the baselines,
  feature coverage and drift.
- **Retraining triggers:** a failed check, a REPD release (fleet capacity) or a change to an input.
- **Retirement:** after three months with no skill over the baselines, or when its inputs are removed. Its
  rows stay in raw.

## Exceptions to confirm

- **New schemas, `ml` and `synthetic`,** beside the layers, with mart versions and table macros as new
  object kinds.
- **The model card as definition:** `ml` datasets cite their cards. Measures reuse the quoted definitions,
  and the provenance columns and run tables are ours, as dlt's are.
- **Elexon's verbatim repeats:** under dlt's `scd2` they land as identical rows (same row hash and
  validity). Staging reads one of each, and the raw row-version test allows identical copies.

## Consequences

- **Provenance at a glance:** the schema says whose data it is; a row's ids lead to the run, the version,
  the dbt invocation, the Dagster run and the dlt loads.
- **Fair comparisons for ever:** any version can be re-backtested on any past `as_of` from the versions in
  the warehouse.
- **The versions are the only history:** losing them loses reproducibility, so the backup's role grows
  ([hosting](../hosting.md)).
- **No history before versioning:** mart versions start when this is deployed; earlier hours appear once,
  as held then.
- **ADR 0001 amended, one deviation fewer:** FUELINST and WINDFOR leave the `delete-insert` deviation; the
  other Elexon streams stay.
- **Docs on acceptance:** the architecture gains the schemas, the time model and the run tables; the
  deviations list gains the exceptions.

## Limits

- **Snapshots cost a mart's changes per build:** each snapshot reads only the mart rows that pending loads
  touched.
- **Points near large sites only:** the 83 points follow REPD sites of at least 50 MW, while most GB solar
  is small and embedded.
- **Transmission wind only:** FUELINST omits embedded wind.
- **Point forecasts, CPU only:** no quantiles and no deep learning on the server.

## Upgrade options

- **Longer history:** ERA5 at the same points (Copernicus CDS, a new `weather_actual` entity), loaded and
  versioned like any source.
- **More marts versioned:** any mart a new model reads gets a `_versions` snapshot.
- **Quantiles:** P10-P90 columns in `ml.ods_*` and `ml.mart_*`.
- **More points:** representative points per region, weighted by REPD capacity (an amendment to ADR 0006).
- **MLflow:** once experiments outgrow the run tables and Dagster's metadata.

## Appendix A: Evidence and method

- **History in the dev warehouse** (`data/warehouse_dev.duckdb`, copied 2026-10-30):

  | Dataset | Technology | From | Rows |
  |---|---|---|---|
  | FUELINST (`mart_generation_actual`) | wind | 2023-12-30 | 24,829 |
  | PVLive (`mart_generation_actual`) | solar | 2023-12-31 | 24,827 |
  | WINDFOR (`mart_generation_forecast`) | wind | 2023-12-31 | 24,865 |
  | ENTSOE_16.1.B_C, ENTSOE_14.1.D | wind, solar | 2024-01-01 | 62-63 areas, none in GB |

  GB is the only area with both weather points and wind and solar data.
- **Elexon's raw today:**
  - FUELINST and WINDFOR are `delete-insert` (`ingest/sources/bmrs.py`).
  - FUELINST's key excludes `publishTime`, so an in-place revision replaces the row.
  - WINDFOR's key includes `publishTime`: 548,133 rows over 24,865 target hours and 8,269 publications, at a
    median lead of 23.5 h.
  - A reload of a `delete-insert` window gives its rows a new load id, so no load-based system time
    survives.
- **dlt 1.30's `scd2`:**
  - It inserts staged rows whose row hash is not active, and retires active rows whose hash is not staged.
  - It does not deduplicate staging (`destinations/sql_jobs.py`, `gen_scd2_sql`), so verbatim repeats in
    one load become identical rows, inserted and retired together.
  - `deduplicated` exists only for `delete-insert`.
- **dbt snapshots:** `dbt snapshot` is available in dbt-oss 2.0.8. A snapshot whose source query omits
  unchanged rows keeps them current, since `hard_deletes` defaults to `ignore`.
- **Run lineage today:** `dlt_meta.dlt_load_audit` records `(load_id, model_name, dbt_invocation_id,
  processed_at)` for each tracked model built and tested.
- **ECMWF:** open data keeps about the last 12 runs ([data sources](../data-sources.md)). It was onboarded
  on 2026-11-02 at 83 grid points near 115 REPD sites ([ADR 0006](0006-gridded-forecasts-at-named-points.md)).
  The mart keeps the newest run per hour, so earlier runs reach the models only through mart versions.
- **Alternatives considered:**
  - Publication time as the knowledge time: not every input has one, and it says nothing about when the
    system could have used the value.
  - Model and version columns on every output row: repeated per row, and changed in many places at once.
  - Versions of `ods` or staging for the models: models read marts, so only marts need versions.
  - Hand-written SCD2 in dbt or dlt: both tools have it built in.
  - Conforming predictions into `ods_generation_forecast`: hides that they are ours, among third parties'.
  - Saved training frames (Parquet per version): copies that grow with every version.
  - MLflow now: a second record of runs beside Dagster's, for two models.
  - Generative synthetic data (GANs, diffusion): opaque, needs a GPU, and there is no privacy reason with
    public data.

## Appendix B: Details

- **Flow:**

  ```
  publisher ─dlt scd2─> raw ─> staging ─> ods ─> marts ─dbt snapshot─> marts.mart_<entity>_versions
                                                                         │
  dims (versioned) ──────────────────────> ml.features_<model>(as_of, issue_from, issue_to)
     ml: train ─> data/models/<model>/<version>/ ; run, version, champion files ─dlt─> ml.model_*, ml.champions
     ml: score ─> data/landing/ml/<model>/<run>.parquet ─dlt─> raw.ml__<model> ─> staging
               ─> ml.ods_<model>_generation_forecast ─> ml.mart_<model>_generation_forecast
  ```

- **dlt config, FUELINST and WINDFOR:** `write_disposition={"disposition": "merge", "strategy": "scd2"}`,
  with `merge_key` as today's `primary_key`. Defaults stay for the validity column names and the row hash.
- **Snapshots:**
  - YAML-defined `snapshots/marts.yml`, one per versioned mart: `strategy: check`, `check_cols` set to the
    measures and `coverage`, and `unique_key` set to the mart's grain.
  - The source query reads the mart's rows whose `_last_dlt_load_id` is pending, plus `'{{ invocation_id }}'
    as _dbt_invocation_id`.
  - It runs in the same `dbt build`, after its mart and before the loads are marked processed.
- **`dlt_meta.dbt_invocations`:** written by the on-run-end hook with `invocation_id`, `run_started_at`, the
  end time, `DAGSTER_RUN_ID` and the commit.
- **Fingerprint:** an order-independent hash of the frame's rows (`bit_xor` of row hashes) and their count,
  stored in `ml.model_versions` and checked on each re-query.
- **Dagster assets** (code location `power_desk_ml`): `<model>/version` (partitioned by training `as_of`),
  `<model>/champion`, `<model>/predictions` (partitioned by issue time). The ELT's `ml` raw assets depend
  on them.
- **Model card:** targets, features, training `as_of` and window, baselines, backtest metrics, limits and
  commit. The catalogue cites it for `ml` datasets.
- **Features:**
  - Wind: 100 m and 10 m speed, its cube, direction (from U and V), weighted by operational wind capacity
    near each point.
  - Solar: radiation, cloud cover and temperature, weighted by solar capacity, with solar elevation and
    clear-sky radiation (pvlib).
  - Both: lead time, hour, day of year, the latest actual, and the installed capacity (REPD) to scale the
    target.
- **Backtest:** rolling origin, daily folds while history is short, then weekly. Each fold is trained only on
  issues before it. Metrics are MAE and RMSE as fractions of installed capacity, and skill = 1 − MAE / MAE of
  the baseline.
- **Monitoring thresholds (starting values):** warn when 14-day MAE exceeds the backtest's by 25%, when skill
  over a baseline is negative over 28 days, when any feature's coverage falls below 95%, or when a feature's
  population stability index exceeds 0.25.
- **Synthetic generators:**

  | Generator | Writes | Use |
  |---|---|---|
  | `known_signal` | `synthetic.mart_weather_forecast`, `synthetic.mart_generation_actual`: generation from a stated power curve and irradiance model, plus noise | the training pipeline recovers the stated skill |
  | `leakage_canary` | as `known_signal`, with one feature equal to the next day's actual | a point-in-time feature set gives it no skill |
  | `scale` | payloads, days resampled in blocks from the seed week, into a synthetic warehouse file | load and benchmark runs |
  | `edge` | payloads with clock-change days, gaps, revisions, late or repeated publications, into a synthetic warehouse file | integration tests of staging, ods and marts |

- **Scenarios:** in `ml/synthetic/` and `elt/synthetic/`; their files in `data/synthetic/<scenario>/`
  (gitignored). Generators refuse `POWER_DESK_ENV=prod`.
- **Sizing:** training and scoring run as Dagster runs within the daemon's 12 GiB, one at a time; they take
  no writer pool, since they only read.
