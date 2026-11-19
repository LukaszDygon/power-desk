# ADR 0004: REMIT as immutable event messages; resources keyed in each publisher's scheme

- **Status:** accepted, 2026-11-02; amended 2026-11-05 (no marts)
- **Details:** [architecture](../architecture.md) (Ingestion, Dimensions)

## Context

- REMIT messages (Elexon's UMMs) are immutable: an update is a new message of the event, and the latest
  applies.
- Only Elexon's message id is unique, and a revision can shorten, withdraw or open-end an event.
- REMIT names units by BM Unit Id; its EICs are often missing from ENTSO-E's list, or are not the unit's.

## Decision

- **Fetch by message id:** list by publish time, fetch by id, and load `scd2` merged on the id.
- **Latest revision in staging:** staging flags each event's latest revision; the entity keeps every one.
- **Rebuild whole events:** the entity rebuilds every message of an event a pending load touched.
- **No marts:** REMIT stays in its entity and is combined with the data it concerns in queries.
- **Resources in their own scheme:** ENTSO-E resources by EIC, BM Units by BM Unit Id, bridged only where
  Elexon lists the EIC.

## Consequences

- **Requests:** two request types per window, about as many requests as one per day.
- **Capacity:** unavailable capacity adds up across concurrent events; available capacity does not.
- **Unresolved units:** units that are not listed BM Units (about 3%) stay unresolved, and their test warns.
- **Open-ended events** stay in the entity.

## Appendix: Evidence and method

- **Immutability:** ACER's Manual of Procedures (Annex VII) makes published UMMs immutable: an update is a
  new message of the same event (mRID) with a higher version, and only the latest applies.
- **Keys:** the documented key (mRID, revision) is not unique in Elexon's data. Elexon republishes some
  revisions, and one message can list several units. Only Elexon's message id, from the `/remit`
  endpoints, is unique.
- **Why rebuild whole events:** a revision can shorten, withdraw (`Dismissed`) or open-end an event, so the
  hours a revision drops must leave the downstream tables. `delete+insert` and `hourly_series` replace only
  the keys or hours the new rows carry, and would keep a dropped tail.
- **Fetching:** the list takes 7 days; the bulk fetch takes the ids in batches. Raw loads `scd2` with
  `merge_key` = `primary_key`: every message is kept, and a replay changes nothing.
- **Latest revision:** the highest revision, then the latest publication, once per unit.
- **Resources:** `dim_resource` holds ENTSO-E resources by EIC and Elexon's BM Units by BM Unit Id, from
  Elexon's BM unit list (never from REMIT). Each source joins on its own scheme; `bridge_resource_eic`
  relates the two only where Elexon lists an EIC for a unit. Most GB unit EICs in REMIT are not in
  ENTSO-E's EIC list, and REMIT's EIC is at times a station, party or interconnector code.
- **Capacity rule:** ACER field 9. The data contracts state both rules.
- **Zone:** the unregistered `10YGB----------B` zone resolves to GB since
  [ADR 0005](0005-nonconforming-eic-codes.md).
- **Amendment (2026-11-05):** the hourly and GB marts were removed, along with
  `macros/dlt/replace_touched.sql`. That macro deleted every touched event from the entity and hourly mart
  and appended it rebuilt, and for the GB business mart (which summed unavailable capacity only) it did
  the same for every hour any revision spanned. The entity now rebuilds touched events like any partition
  (`pending_partitions`, keyed on the event). Open-ended events were not placed on the hourly spine.
