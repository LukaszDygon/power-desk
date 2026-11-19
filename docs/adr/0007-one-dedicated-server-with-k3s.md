# ADR 0007: One Hetzner AX41, running k3s, reached over Tailscale

- **Status:** proposed, 2026-11-19
- **Details:** [hosting](../hosting.md); scripts in [`infra/hetzner`](../../infra/hetzner)

## Context

- **What it hosts:** scheduled loads, the dashboard, the push services, logs and OpenMetadata, with room
  for a few more services.
- **Not critical:** an analytics dashboard refreshed on a schedule.
- **One machine:** DuckDB has one writer, and its file lock holds only within one machine.

## Assumptions

- **Downtime:** hours are acceptable, and recovery means restoring last night's backup.
- **Warehouse size:** 4-8 GB today, about 110 bytes per raw row. It grows with sources and history, not
  with users.
- **Users:** a few, all on the tailnet. ENTSO-E's pushes are the only public traffic.
- **Runs:** scheduled runs are incremental. A full dbt rebuild needs about 3.3 GiB.
- **OpenMetadata:** one warehouse and one dbt project, which fit in about 4.5 GiB.
- **Prices:** Hetzner's, as of 2026-11-19.

## Decision

- **One AX41:** 6 cores, 64 GB (no ECC), 2 × 512 GB NVMe in RAID 1, at €59 a month. It is the cheapest
  machine with 32 GB or more.
- **k3s on one node:** the existing Helm charts run with the server's values; images are imported over SSH.
- **Tailscale for people:** the only way in. From the internet, only ENTSO-E's two addresses reach 443.
- **Nightly off-site backup:** an LVM snapshot copied with restic to a Storage Box.

## Limits

- **Memory:** about 27 GiB of limits, 12 of them for runs. The warehouse stays cached up to about 30 GB;
  beyond that, it slows rather than fails.
- **Storage:** about 340 GiB for data, so the warehouse should stay below about 120 GB, which is about a
  billion raw rows.
- **CPU:** six cores. Runs go one at a time, so a backfill delays scheduled runs.

## Upgrade options

- **Bigger single machine:** AX42 or AX102 (up to 16 cores, 128 GB), moved to by a restore. OpenMetadata
  and the other services can move to a second node first.
- **Away from one DuckDB file:** Quack (several writers through one server) and DuckLake (Parquet with a
  Postgres catalogue) keep the SQL and the dbt project. A server database (Postgres, ClickHouse) would
  change the dbt adapter and the dlt destination.

## Consequences

- **Cost:** about €65 a month, covering the server, IPv4 and the Storage Box.
- **Single point of failure:** recovered within hours, if the restore has been rehearsed.

## Appendix: Evidence and method

- **Prices, excluding VAT, 2026-11-19:**
  - AX41: €59, no setup fee.
  - AX42: €79-99, plus €49 setup.
  - AX102: €159-259, plus €129 setup.
  - Cloud: CPX62 (32 GB) €130.49, shown as unavailable; CCX33 (8 dedicated vCPU, 32 GB) €138.99.
  - Server auction: from €78.70.
  - Storage Box BX11: €3.20.
  - Hetzner repriced in April and June 2026, citing RAM and NVMe costs.
  - Sources: [hosting, Appendix A](../hosting.md#appendix-a-evidence).
- **Rebuild measurement:**
  - Method: `dbt build --full-refresh` on a copy of the dev warehouse (73M raw rows, 8.3 GB), excluding
    PVLive, on an 8 GB laptop.
  - Result: 197 s, a peak of 3.3 GiB resident and a 7.7 GiB footprint. DuckDB spills beyond 80% of
    detected memory.
  - Bytes per row: the 8.3 GB file divided by 73M raw rows, marts included.
- **Limits, derived:**
  - Memory: the limits table in [hosting, Appendix B](../hosting.md#appendix-b-details). About 12-16 GiB
    is in use at a run's peak.
  - Storage: about 476 GiB in RAID 1, minus 48 GiB for root and swap, leaves 428 GiB. 80% of that is for
    data and the rest for snapshots.
  - Warehouse ceiling: a full rebuild needs spill files plus a second copy of the tables it rewrites,
    and the other volumes need about 30 GB. That keeps the warehouse at or below about 120 GB.
- **Alternatives considered:**
  - Hetzner Cloud: easier resizing and snapshots, but about twice the price for half the memory.
    DuckDB is fine on a Cloud Volume, since a Volume is a disk attached to one server and DuckDB's
    caution is about shared network file systems.
  - Docker Compose: it would mean rewriting the Helm charts, and has no path to a second node.
  - Public UIs behind an identity proxy: no public users need them.
  - Headscale or plain WireGuard: the fallback if Tailscale's service or its Personal plan (for
    non-commercial use) stops suiting. Neither has a Kubernetes operator.
