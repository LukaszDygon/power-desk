#!/usr/bin/env bash
# Nightly backup of the data volume (/srv/power-desk) to restic, off the server (backup.env.example).
#
# LVM snapshots the volume while it is in use: the filesystem is frozen for the instant it is taken, so the copy is
# what a power cut at that instant would leave, which DuckDB (its WAL), MySQL (InnoDB) and SQLite recover from on
# restore. Runs need not stop. Rebuildable data is left out: OpenSearch's index (OpenMetadata reindexes from
# MySQL), Loki's logs, dlt's working directory and DuckDB's spill files.
set -euo pipefail

# shellcheck source=/dev/null
source /etc/power-desk/backup.env  # RESTIC_REPOSITORY, RESTIC_PASSWORD_FILE, SNAPSHOT_SIZE, KEEP_*
export RESTIC_REPOSITORY RESTIC_PASSWORD_FILE

SNAPSHOT=data-backup
MOUNT=/mnt/power-desk-backup

release() {
  if mountpoint -q "$MOUNT"; then umount "$MOUNT"; fi
  if lvs "vg0/$SNAPSHOT" >/dev/null 2>&1; then lvremove -qy "vg0/$SNAPSHOT"; fi
}
trap release EXIT
release  # a snapshot left by an interrupted run

restic cat config >/dev/null 2>&1 || restic init

lvcreate -qs -L "${SNAPSHOT_SIZE:-50G}" -n "$SNAPSHOT" vg0/data
mkdir -p "$MOUNT"
# a snapshot of XFS shares the origin's UUID
mount -o ro,nouuid "/dev/vg0/$SNAPSHOT" "$MOUNT"

# a fixed path, so each backup finds its parent and reads only changed files
cd "$MOUNT"
restic backup --tag nightly --host power-desk \
  --exclude 'volumes/*opensearch*' \
  --exclude 'volumes/*loki*' \
  --exclude 'data/dlt/pipelines' \
  --exclude '*.duckdb.tmp' \
  .
cd /

restic forget --tag nightly --host power-desk --prune \
  --keep-daily "${KEEP_DAILY:-7}" --keep-weekly "${KEEP_WEEKLY:-5}" --keep-monthly "${KEEP_MONTHLY:-12}"
# a sample of the stored data, read back each night
restic check --read-data-subset=2%
