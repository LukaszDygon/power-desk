# ADR 0004: REMIT as immutable event messages; resources keyed in each publisher's scheme

- **Status:** accepted, 2026-11-02; amended 2026-11-05 (no marts)
- **Details:** [architecture](../architecture.md) (Ingestion, Dimensions)

## Context

Elexon publishes REMIT inside information (urgent market messages) on unavailability of electricity
facilities. ACER's Manual of Procedures (Annex VII) makes published UMMs immutable: an update is a new
message of the same event (mRID) with a higher version, and only the latest applies. The documented key
(mRID, revision) is not unique in Elexon's data: it republishes some revisions, and one message can list
several units. Only Elexon's message id, from the `/remit` endpoints, is. A revision can shorten, withdraw
(`Dismissed`) or open-end an event, so the hours a revision drops must leave the marts.

REMIT names units by Elexon's BM Unit Id. Most GB unit EICs that REMIT carries are not in ENTSO-E's EIC
list, and REMIT's EIC is at times a station, party or interconnector code rather than the unit's.

## Decision

- **Fetch by message id:** list by publish time (every revision), then fetch the messages by id. Raw loads
  scd2 merged on the id (`merge_key` = `primary_key`): every message kept, a replay changes nothing.
- **Latest revision in staging:** staging flags each event's latest revision (highest revision, latest
  publication, once per unit). The entity keeps every revision; the marts use the latest.
- **Rebuild whole events:** the entity and the hourly mart delete every event a pending load touched and
  append it rebuilt; the GB business mart does the same for every hour any revision of the event spans
  (`macros/dlt/replace_touched.sql`). `delete+insert` and `hourly_series`, which replace only the keys or
  hours the new rows carry, would keep a dropped tail.
- **Resources in their own scheme:** `dim_resource` holds ENTSO-E resources by EIC and Elexon's BM Units
  by BM Unit Id, from Elexon's BM unit list (never from REMIT). Each source joins on its own scheme;
  `bridge_resource_eic` relates the two only where Elexon lists an EIC for a unit.

## Consequences

- Two request types per window, about as many requests as one per day: the list takes 7 days, the bulk
  fetch takes the ids in batches.
- Unavailable capacity adds up across concurrent events (ACER field 9); available capacity does not.
  The data contracts state both, and the business mart sums unavailable capacity only.
- Assets that are not listed BM Units (about 3% of REMIT units) stay unresolved, and their test warns.
  The unregistered `10YGB----------B` zone resolves to GB since [ADR 0005](0005-nonconforming-eic-codes.md).
- Open-ended events stay in the entity but are not placed on the hourly spine.

**Amendment (2026-11-05):** REMIT messages stay in their entity, combined with the data they concern in
analytical queries. The hourly and GB marts and `replace_touched.sql` are removed; the entity rebuilds every
message of an event a pending load touched, like any partition (`pending_partitions`, keyed on the event).
