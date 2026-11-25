# Data dictionary

These definitions describe the inspected source files. Source-specific IDs are strings. OPD times are timezone-unspecified local times; radiology event times are UTC. HH:MM duration strings are hours and minutes. Empty optional stage columns often mean not applicable, not a failed service. See [HospitalOPD](https://data.mendeley.com/datasets/j2hd2239dr/1) and [radiology dataset documentation](https://data.mendeley.com/datasets/jsg8c4yhxy/2).

## opd.HospitalOPD-noname

| column | expected_type | unit | description | missing | invalid_nonempty |
| --- | --- | --- | --- | --- | --- |
| record_no | string | identifier | Source row identifier; not a patient or visit key. | 0 | 0 |
| patient_id | string | identifier | Anonymized patient identifier within HospitalOPD only. | 0 | 0 |
| Unnamed: 2 | string | none | Empty source header/column artifact; remove only from prepared copies. | 62422 | 0 |
| appointment_id | string | identifier | Appointment identifier; repeats across source rows and is the candidate OPD visit key. | 0 | 0 |
| appointment_start_datetime | opd_datetime | local datetime, timezone unspecified | Recorded appointment start; physical arrival is not established. | 0 | 0 |
| prescription_doctor_id | string | identifier | Source clinician/account ID attached to the prescription record; not a roster or capacity. | 0 | 0 |
| prescription_doctor_name | string | text | Source clinician/account label, including administrative labels. Excluded from prepared tables. | 0 | 0 |
| prescription_order_id | string | identifier | Prescription-order identifier. A consultation proxy, not a guaranteed service-start event. | 0 | 0 |
| prescription_start_datetime | opd_datetime | local datetime, timezone unspecified | Recorded prescription start timestamp. Workflow meaning is not independently verified; lab end includes malformed time fragments. | 12 | 0 |
| prescription_end_datetime | opd_datetime | local datetime, timezone unspecified | Recorded prescription end timestamp. Workflow meaning is not independently verified; lab end includes malformed time fragments. | 1 | 0 |
| lab_id | string | identifier | Source lab identifier. Multiple variants and appointment associations occur; global visit linkage is not guaranteed. | 44393 | 0 |
| lab_name | string | text | Source laboratory service/test label. | 44393 | 0 |
| lab_start_datetime | opd_datetime | local datetime, timezone unspecified | Recorded lab start timestamp. Workflow meaning is not independently verified; lab end includes malformed time fragments. | 44393 | 0 |
| lab_end_datetime | opd_datetime | local datetime, timezone unspecified | Recorded lab end timestamp. Workflow meaning is not independently verified; lab end includes malformed time fragments. | 44393 | 4702 |
| imaging_request_id | string | identifier | Source imaging request identifier; some IDs link to multiple appointments. | 56899 | 0 |
| imaging_result_id | string | identifier | Source imaging result identifier. | 56899 | 0 |
| imaging_name | string | text | Source imaging service label. | 56899 | 0 |
| imaging_start_datetime | opd_datetime | local datetime, timezone unspecified | Recorded imaging start timestamp. Workflow meaning is not independently verified; lab end includes malformed time fragments. | 56899 | 0 |
| imaging_end_datetime | opd_datetime | local datetime, timezone unspecified | Recorded imaging end timestamp. Workflow meaning is not independently verified; lab end includes malformed time fragments. | 56909 | 0 |
| pharmacy_sale_line_id | string | identifier | Source pharmacy sale-line identifier; some IDs have multiple record variants. | 62120 | 0 |
| medicine_name | string | text | Source medication/item label. Not used to infer disease. | 62120 | 0 |
| pharmacy_start_datetime | opd_datetime | local datetime, timezone unspecified | Recorded pharmacy start timestamp. Workflow meaning is not independently verified; lab end includes malformed time fragments. | 62120 | 0 |
| pharmacy_end_datetime | opd_datetime | local datetime, timezone unspecified | Recorded pharmacy end timestamp. Workflow meaning is not independently verified; lab end includes malformed time fragments. | 62120 | 0 |
| flow_code | string | category | Source row-level pathway category. Not a documented intended treatment plan. | 0 | 0 |
| flow_name | string | text | Text for the recorded row-level pathway; a visit can have multiple row variants. | 0 | 0 |

## radiology.cases

| column | expected_type | unit | description | missing | invalid_nonempty |
| --- | --- | --- | --- | --- | --- |
| case_id | string | identifier | Synthetic radiology visit identifier. Event log includes cases absent from the completed-case summary. | 0 | 0 |
| arrival_time | utc_datetime | UTC datetime | Synthetic case arrival timestamp. | 0 | 0 |
| end_time | utc_datetime | UTC datetime | Synthetic case completion timestamp. | 0 | 0 |
| patient_type | string | category | Radiology category: A outpatient, S emergency, H inpatient, D day-hospital. | 0 | 0 |
| exam_types | string | text list | Source list-like text of modalities; preserve raw representation. | 0 | 0 |
| exam_count | number | count | Number of exams in the completed-case summary. | 0 | 0 |
| total_wait_time | hhmm | HH:MM duration | Source case-level wait summary. It exceeds summed exam waits in many cases; scope is unverified and not used for exam-wait KPIs. | 0 | 0 |
| total_scan_time | hhmm | HH:MM duration | Source sum of scan durations for a completed case. | 0 | 0 |
| throughput_time | timedelta | days HH:MM:SS | Source duration from case arrival to completion. | 0 | 0 |
| week_day_of_arrival | string | weekday | Weekday derived in source case summary; differs from resource-log calendar convention. | 0 | 0 |
| hour_day_of_arrival | number | hour 0..23 | Hour of case arrival. | 0 | 0 |

## radiology.events

| column | expected_type | unit | description | missing | invalid_nonempty |
| --- | --- | --- | --- | --- | --- |
| case_id | string | identifier | Synthetic radiology visit identifier. Event log includes cases absent from the completed-case summary. | 0 | 0 |
| exam_id | string | identifier | Exam identifier. Validate with case_id before joining; blank on non-exam events. | 23840 | 0 |
| activity | string | category | Source Spanish activity label; preserve to avoid guessing workflow semantics. | 0 | 0 |
| timestamp_start | utc_datetime | UTC datetime | Source event interval start. | 0 | 0 |
| timestamp_end | utc_datetime | UTC datetime | Source event interval end. | 0 | 0 |
| total_duration | hhmm | HH:MM duration | Source event interval duration. | 0 | 0 |
| modality | string | category | Source imaging modality label. Literal None denotes not applicable in events. | 0 | 0 |
| patient_type | string | category | Radiology category: A outpatient, S emergency, H inpatient, D day-hospital. | 0 | 0 |
| scenario_id | string | category | Source subprocess/scenario label, not a unique replication ID. | 0 | 0 |

## radiology.exams

| column | expected_type | unit | description | missing | invalid_nonempty |
| --- | --- | --- | --- | --- | --- |
| case_id | string | identifier | Synthetic radiology visit identifier. Event log includes cases absent from the completed-case summary. | 0 | 0 |
| exam_id | string | identifier | Exam identifier. Validate with case_id before joining; blank on non-exam events. | 0 | 0 |
| modality | string | category | Source imaging modality label. Literal None denotes not applicable in events. | 0 | 0 |
| start_exam | utc_datetime | UTC datetime | Scan service start. Verified against scan duration and the matching event interval. | 0 | 0 |
| end_exam | utc_datetime | UTC datetime | End of source exam interval. | 0 | 0 |
| wait_before_exam | hhmm | HH:MM duration | Explicit source-defined pre-scan waiting duration; distinct from total exam interval. | 0 | 0 |
| scan_time_duration | hhmm | HH:MM duration | Explicit source-defined scan duration. | 0 | 0 |
| total_exam_duration | hhmm | HH:MM duration | Wait plus scan duration. This differs from end_exam minus start_exam, which measures scan service only. | 0 | 0 |

## Radiology resource snapshot files

The following schema is shared by all 25 resource CSVs. Missingness for each individual file is in data_dictionary.csv.

| column | expected_type | unit | description |
| --- | --- | --- | --- |
| avgUsage | number | source ratio | Source usage statistic. Averaging-window semantics are not specified; not used as instantaneous occupancy. |
| avail | number | units | Available units at the resource snapshot. |
| limit | number | units | Total units at the resource snapshot. |
| waitingProcesses | number | count | Processes waiting for this resource at the snapshot. |
| maxWaitTime | number | unconfirmed source unit | Source maximum-wait statistic; time unit/window not explicitly established in field documentation. |
| averageWaitTime | number | unconfirmed source unit | Source average-wait statistic; time unit/window not explicitly established in field documentation. |
| currentSimulationLocalTime | string | HH:MM clock | Snapshot clock time; has no calendar date. |
| currentSimulationDay | string | weekday | Snapshot weekday; starts Monday although case timestamps begin Sunday. |