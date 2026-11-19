# Hosting

How Power Desk runs in production: one Hetzner AX41 running k3s, reached over Tailscale, and backed up off
the server ([ADR 0007](adr/0007-one-dedicated-server-with-k3s.md); scripts in
[`infra/hetzner`](../infra/hetzner/Makefile)).

```
   internet ── 443 from ENTSO-E only ──┐        ┌── tailnet: SSH, kubectl, HTTPS UIs
                                       ▼        ▼
   Robot firewall ─> nftables ─> k3s: power-desk (Dagster, dashboard, catalogue job, services)
                                      observability (Loki, Alloy, Grafana)
                                      openmetadata (MySQL, OpenSearch, server), tailscale (operator)
   /srv/power-desk on RAID 1 NVMe ── nightly LVM snapshot, restic ──> Storage Box, another location
```

## Server

- **AX41, about €65 a month:** this covers the server, IPv4 and the Storage Box (Appendix A).
- **One machine opens the warehouse:** DuckDB's lock spans one machine, so any local disk will do.
- **Charts as on minikube:** the server's values in `infra/hetzner/values/` go over the local ones.
- **Images over SSH:** they are built locally and imported into k3s, so no registry is needed.

## Access

- **Tailscale only, for people:** SSH, the Kubernetes API and the UIs (`pd-dagster`, `pd-dashboard`,
  `pd-grafana`, `pd-openmetadata`), with the admins group as the only source.
- **Public, ENTSO-E only:** 443 from its two addresses, at the edge, on the host and in Traefik; the
  certificate comes by DNS-01.
- **Two firewalls:** Hetzner's stateless edge firewall and nftables in its own table.
- **Hardened host:** SSH keys only, unattended security updates, Secrets encrypted at rest, non-root pods
  on read-only root filesystems.
- **Break-glass:** Hetzner's Rescue System and KVM console, or SSH from `BREAK_GLASS_IP`.

## Storage and backups

- **`/srv/power-desk`:** XFS on LVM over RAID 1 NVMe. `data/` is the warehouse's directory; `volumes/` holds
  k3s's volumes.
- **Nightly backup:** an LVM snapshot copied with restic to a Storage Box in another location. Runs don't
  stop, and every engine recovers from it as from a power cut.
- **Raw must be backed up:** publishers don't republish the past.
- **Left out of the backup:** OpenSearch's index, Loki's logs and dlt's working directory, all rebuildable.
- **Restore quarterly:** `restic restore latest`, then `make platform apps`.

## Sizing

- **Memory:** limits total about 27 GiB, of which 12 GiB is for runs, and 12-16 GiB is in use at a run's
  peak. The rest is page cache (Appendix B).
- **Runs:** a full dbt rebuild needs about 3.3 GiB and 3.3 minutes (Appendix A).
- **OpenMetadata:** about 4.5 GiB for one warehouse, far below its documented production sizes.

## Growth and opportunities

- **Limits and upgrades:** see [ADR 0007](adr/0007-one-dedicated-server-with-k3s.md).
- **Second node:** OpenMetadata, observability and new services can move off the warehouse's node.
- **Remote storage:** Object Storage for the landing zone, Loki's chunks or a second backup copy.
- **Postgres:** for Dagster once its run history slows the UI, and for OpenMetadata with it.
- **Readers off the writer's lock:** publish an XFS reflink copy of the warehouse after each run, or front
  it with a Quack server.
- **DuckDB's memory:** set `memory_limit` and `temp_directory` in the dbt profile, below the runs' limit.
- **Per-run pods and a registry:** use Dagster's Kubernetes run launcher once runs vary widely, and GHCR
  with CI once there is a second node or maintainer.

## Open

- **Traefik and client addresses:** check whether Traefik sees ENTSO-E's addresses behind ServiceLB. Until
  then, the firewalls alone filter.
- **OpenMetadata's JWT keys:** still the chart's defaults. Replace them before anyone but the admins can
  reach the server.
- **Alerts:** failed runs, failed backups and freshness checks notify no one yet.

## Appendix A: Evidence

- **Prices, excluding VAT, as of 2026-11-19:**
  - Sources: Hetzner's [AX price list](https://www.hetzner.com/dedicated-rootserver/matrix-ax/),
    [Cloud plans](https://www.hetzner.com/cloud/regular-performance/), the
    [server auction](https://www.hetzner.com/sb/) and a
    [2026 price tracker](https://agentdeals.dev/hetzner-pricing-2026).
  - Hetzner repriced three times in 2026, so check before ordering.

  | Item | Spec | Per month |
  |---|---|---|
  | AX41 | Ryzen 5 3600 (6 cores), 64 GB DDR4 (no ECC), 2 × 512 GB NVMe | €59, no setup fee |
  | AX42 | Ryzen 7 PRO 8700GE (8 cores), 64 GB DDR5 ECC, 2 × 1.92 TB NVMe | €79-99, plus €49 setup |
  | Cloud CPX62 | 16 shared vCPU, 32 GB (shown as unavailable) | €130.49 |
  | Cloud CCX33 | 8 dedicated vCPU, 32 GB | €138.99 |
  | Server auction | varies | from €78.70 |
  | Storage Box BX11 | 1 TB, SFTP on port 23 | €3.20 |
  | Object Storage | 1 TB stored, 1 TB egress | €6.49 |
  | Tailscale Personal | free, non-commercial use only | €0 |
- **Full dbt rebuild (2026-11-19):**
  - Method: a copy of the dev warehouse (73M raw rows, 8.3 GB file), `dbt build --full-refresh` excluding
    PVLive, timed with `/usr/bin/time -l`, on an 8 GB laptop.
  - PVLive was left out because that copy predates PVLive's versioned raw. The copy's audit table was
    dropped first, since it predates a column.
  - Result: 582 of 584 nodes passed and 2 warned, in 197 s. Peak resident memory was 3.3 GiB; the peak
    footprint, compressed memory included, was 7.7 GiB.
  - DuckDB caps itself at 80% of the memory it detects and spills the rest to disk, so this shows the
    build fits in 8 GB, not what it would use with more.
- **Docs:**
  - DuckDB: advises caution with shared directories on network storage
    ([concurrency](https://duckdb.org/docs/stable/connect/concurrency)).
  - OpenMetadata's production sizes: a 16 GB server, a 16 GB database, three 8 GB search nodes
    ([requirements](https://docs.open-metadata.org/v2.0.x/deployment/production-ready-requirements)).
  - Hetzner's [Robot firewall](https://docs.hetzner.com/robot/dedicated-server/firewall/): stateless,
    at most 10 rules per direction.
  - The [Tailscale operator](https://tailscale.com/kb/1439/kubernetes-operator-cluster-ingress) serves
    HTTPS on tailnet names only.
  - ingress-nginx was retired in March 2026.

## Appendix B: Details

- **Memory limits** (`infra/hetzner/values/`):

  | Workload | Limit |
  |---|---|
  | Dagster daemon, with its runs (dlt, dbt, DuckDB) | 12 GiB |
  | Dagster webserver, dashboard | 2 + 2 GiB |
  | OpenMetadata: server (1 GB heap), MySQL (256 MB buffer pool), OpenSearch (1 GB heap) | 1.5 + 1 + 2 GiB |
  | Catalogue ingestion (nightly job) | 3 GiB |
  | Loki (a week), Alloy, Grafana | 0.5 + 0.25 + 0.25 GiB |
  | Services (IRIS, ENTSO-E) | 1 + 1 GiB |
  | k3s, Tailscale proxies, OS (`system-reserved`) | about 3 GiB |
- **Edge firewall** (`robot-firewall.sh`), admitting:
  - ICMP.
  - TCP and UDP replies on ports 32768-65535: the server's own connections, DNS, NTP and Tailscale. IPv4
    and IPv6 are both filtered.
  - TCP 443 from 4.185.182.62 and 4.182.105.72.
  - SSH from `BREAK_GLASS_IP`, when set.
  - Hetzner's own services (`whitelist_hos`).
- **Host firewall** (`host/nftables.conf`):
  - Admits the tailnet and pod interfaces, and Tailscale's UDP 41641.
  - Drops new public connections to pods unless their original port is 443.
- **Disk layout** (`installimage.conf`, `host/bootstrap.sh`):
  - RAID 1 with `/boot` and a 40 GB root.
  - `vg0/data` takes 80% of the free space, as XFS with reflinks. The other 20% is room for snapshots.
- **Backup** (`host/backup.sh`, 03:15 UTC):
  - Takes an LVM snapshot (the filesystem is frozen while it is taken) and mounts it read-only.
  - Runs restic over SFTP, keeping 7 daily, 5 weekly and 12 monthly copies, and reads back 2% each night.
- **Setup** (in `infra/hetzner`, with `.env` from `env.example`):
  1. Order the server and a Storage Box in another location.
  2. Create a Robot webservice user, a tagged auth key and the operator's OAuth client. Merge
     `tailnet-policy.hujson` into your tailnet policy.
  3. Install from the Rescue System with `installimage.conf`.
  4. Run `make host HOST=root@<public ip>`, then reconnect over the tailnet.
  5. Run `make firewall kubeconfig secrets platform`.
  6. Put the bot token in `.env`, then run `make secrets` again.
  7. Run `make images catalog-image apps tailnet`. For ENTSO-E's pushes, also run `make public` and register
     `https://<PUBLIC_HOST>/subscriptions`.
  8. Put `host/backup.env.example` on the server, then run `make backup-now backup-status`.
