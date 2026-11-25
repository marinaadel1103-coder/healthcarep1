# Integration contract

Prepared files are exploratory handoff tables. Production ETL should preserve
their quality decisions and lineage, or document any reviewed changes.

## Grains and relationships

| File under data/exploration | One row represents | Key / allowed relationship |
| --- | --- | --- |
| events.csv.gz | One distinct OPD stage payload variant, or one radiology source event row | event_key is unique and source-prefixed |
| opd_visits.csv.gz | One distinct OPD appointment | case_key unique; patient_key may repeat |
| opd_event_lineage.csv.gz | One OPD source-row-to-stage association | event_key maps to events; case_key maps to opd_visits. Multiple rows can repeat the same pair legitimately |
| radiology_cases.csv.gz | One completed source case summary | case_id unique within radiology |
| radiology_exams.csv.gz | One source exam with validated timing context | (case_id, exam_id) unique within radiology |
| radiology_events_with_context.csv.gz | One event with attached case/exam attributes | Same row count as raw events; case/exam fields can repeat |
| resource_snapshots.csv.gz | One resource observation at a relative simulation minute | (resource_id, relative_minute_monday_origin) unique |

The source `scenario_id` is a subprocess label, not a simulation replication ID.
Radiology has case IDs, not a reusable patient master ID. Its patient_key is therefore null.
Resource names are inferred from the original filenames and remain source-specific.

## Common event schema

| Column | Type and meaning |
| --- | --- |
| source_system | String: opd or radiology. Mandatory grouping/filter field |
| source_nature | String: publisher_reported_anonymized_observational or synthetic_simulation |
| event_key | String: stable key for this pinned snapshot. OPD uses a 24-hex SHA-256 payload digest; radiology uses source row order |
| case_key | String: source-prefixed appointment/case ID. Null for ambiguous OPD natural-ID visit associations |
| patient_key | String: OPD-only source-prefixed patient ID. Null for radiology |
| activity | String: OPD stage label or unchanged Spanish radiology activity |
| source_natural_id | String: OPD stage ID or radiology exam ID. Not globally unique by itself |
| source_row | OPD record_no for the first occurrence of a payload; radiology CSV record position including header. Full OPD membership is in lineage |
| start_raw, end_raw | Original source strings, including malformed ones |
| start_time, end_time | Parsed timestamp text. OPD timezone unspecified; radiology includes UTC offset. Missing for failed parses |
| clock_basis | String documenting the time convention. Do not blindly convert OPD local timestamps to UTC |
| elapsed_minutes | Numeric nonnegative interval, null for missing/invalid/inverted endpoints and appointment anchors |
| duration_valid | Boolean: both endpoints parse and end is at/after start |
| ambiguous_visit_link | Boolean: natural service ID is associated with multiple OPD appointments |
| multiple_payload_variants | Boolean: one natural service ID has more than one distinct payload |
| precedes_linked_appointment | Boolean: parsed service start precedes its source appointment start |
| eligible_interval_summary | Boolean: valid interval with no ambiguous link, variant conflict or negative appointment ordering. Radiology uses valid event duration |
| resource_key | Source-prefixed clinician/account ID for OPD prescription records only. Not a capacity/roster field |
| source_label | Source lab/imaging/medicine label or radiology modality |
| metric_semantics | String explaining that event elapsed duration is not automatically queue waiting |

Payload hashes use patient ID, natural stage ID, raw timestamps, provider ID where
available, and service label where available. Appointment association is tracked
separately so the same source service is not duplicated into different journeys.
Hash uniqueness is asserted during preparation. Multiple lab labels under one
lab ID may represent a different source grain rather than an error; they remain
flagged rather than arbitrarily collapsed.

## Valid joins

- OPD events → OPD visits only when case_key is populated. For uncertain records,
  inspect the lineage table; it is an association bridge, not permission to
  multiply an event's duration across visits.
- Radiology events → cases on case_id, many-to-one, left join. Missing summaries stay missing.
- Radiology events → exams on (case_id, exam_id), many-to-one, left join.
- Radiology exams → their matching exam event is verified one-to-one when reconstructing waiting.
- Common event view = UNION ALL of source-specific prepared event records. Every source stays labeled.

Do not join OPD and radiology on patient, case, date or modality to manufacture a
continuous journey. Do not join the earlier Synthea population to either source.
Do not sum repeated case/exam measures from the enriched event table.

## Time and resource semantics

OPD dates use explicit `%m/%d/%Y %H:%M`. Values such as `53:45.0` in lab end fields
are not complete timestamps and cannot be repaired by guessing an hour/date.
Radiology `HH:MM` fields are durations, not clock times.

Radiology exam service is `[start_exam, end_exam]`. The matching event spans
queue entry through exam completion. The checks verify:

```
wait_before_exam = start_exam - event.timestamp_start
scan_time_duration = end_exam - start_exam
total_exam_duration = wait_before_exam + scan_time_duration
```

The prepared exam table adds numeric minute versions, queue_entry_time,
service_start_time, service_end_time, timestamp_wait_minutes and wait_validated.
Only wait_validated exams enter the modality waiting summary.
Case-level total_wait_time has unresolved scope and is not substituted for exam waits.

Resource snapshots use a relative Monday-origin minute coordinate. Their source
weekdays start Monday; case timestamps start on Sunday, 2023-01-01. No absolute
calendar mapping is assumed. Snapshot occupancy is `(limit - avail) / limit`
when capacity is positive. Its average is an equal-weight snapshot estimate,
not exact continuous-time utilization. `avgUsage` is retained with its original
meaning unresolved. Queue-statistic time units/windows remain unconfirmed.

## Reporting rules

- Group by source and compatible activity/metric. Never publish a pooled hospital-wide wait from these sources.
- Include eligible record counts and the filtering rules for every duration metric.
- Do not treat absent optional services as abandoned treatment.
- Do not treat pharmacy's small recorded coverage as unmet demand.
- OPD lab intervals can indicate recorded turnaround, not the cause of delays or a proven staffing shortage.
- Any what-if result belongs to a separately documented simulation with assumptions and uncertainty.
