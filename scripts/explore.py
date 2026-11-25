"""Step 1: reproducible source profiling, cautious integration, and evidence exports."""
# %% Setup and provenance
from pathlib import Path
from datetime import datetime, timezone
import gc
import hashlib
import html
import json
import re
import sys
import time
import pandas as pd
import numpy as np

STARTED = time.perf_counter()
ROOT = Path.cwd()
if not (ROOT / 'data/raw/opd').exists():
    for candidate in [ROOT / 'step1_v2', ROOT.parent]:
        if (candidate / 'data/raw/opd').exists():
            ROOT = candidate
            break
RAW, OUT, PREP = ROOT / 'data/raw', ROOT / 'reports', ROOT / 'data/exploration'
OUT.mkdir(parents=True, exist_ok=True)
PREP.mkdir(parents=True, exist_ok=True)
specs = json.loads((ROOT / 'data/metadata/sources.json').read_text(encoding='utf-8'))
for spec in specs:
    path = ROOT / spec['path']
    h = hashlib.new(spec['algorithm'])
    with path.open('rb') as f:
        while block := f.read(1024 * 1024):
            h.update(block)
    assert h.hexdigest() == spec['checksum'], f'Source changed: {path.name}'
print(f'Verified {len(specs)} pinned source files. Python {sys.version.split()[0]}, pandas {pd.__version__}, NumPy {np.__version__}.')

def show(df, n=18):
    print(df.head(n).to_string(index=False))

def md(df):
    def clean(x): return str(x).replace('|', '/').replace('\n', ' ')
    return '\n'.join(['| ' + ' | '.join(map(clean, df.columns)) + ' |',
                      '| ' + ' | '.join(['---'] * len(df.columns)) + ' |'] +
                     ['| ' + ' | '.join(map(clean, row)) + ' |' for row in df.itertuples(index=False, name=None)])

checks, samples = [], []
def check(table, rule, mask, evaluated=None, severity='review', interpretation=''):
    mask = pd.Series(mask).fillna(False).astype(bool)
    checks.append({'table': table, 'rule': rule, 'evaluated': len(mask) if evaluated is None else int(evaluated),
                   'flagged': int(mask.sum()), 'severity': severity,
                   'status': 'NOT_EVALUATED' if evaluated == 0 else ('REVIEW' if mask.any() else 'PASS'),
                   'interpretation': interpretation})
    for index in mask[mask].index[:5]:
        samples.append({'table': table, 'rule': rule, 'zero_based_index': str(index),
                        'csv_record_including_header': int(index) + 2 if isinstance(index, (int, np.integer)) else ''})

def load(path):
    return pd.read_csv(path, dtype='string', keep_default_na=False).apply(lambda s: s.str.strip().replace('', pd.NA))

def opd_datetime(series):
    return pd.to_datetime(series, format='%m/%d/%Y %H:%M', errors='coerce')

def utc_datetime(series):
    return pd.to_datetime(series, format='ISO8601', utc=True, errors='coerce')

def hhmm_minutes(series):
    bits = series.str.extract(r'^(\d+):(\d{2})$')
    hours, minutes = pd.to_numeric(bits[0], errors='coerce'), pd.to_numeric(bits[1], errors='coerce')
    return (hours * 60 + minutes).where(minutes.between(0, 59))

# %% Raw inventory, field types and missingness
tables, inventory, dictionary = {}, [], []
definitions = {
 'record_no': ('string', 'Source row identifier; not a patient or visit key.', 'identifier'),
 'patient_id': ('string', 'Anonymized patient identifier within HospitalOPD only.', 'identifier'),
 'appointment_id': ('string', 'Appointment identifier; repeats across source rows and is the candidate OPD visit key.', 'identifier'),
 'appointment_start_datetime': ('opd_datetime', 'Recorded appointment start; physical arrival is not established.', 'local datetime, timezone unspecified'),
 'prescription_doctor_id': ('string', 'Source clinician/account ID attached to the prescription record; not a roster or capacity.', 'identifier'),
 'prescription_doctor_name': ('string', 'Source clinician/account label, including administrative labels. Excluded from prepared tables.', 'text'),
 'prescription_order_id': ('string', 'Prescription-order identifier. A consultation proxy, not a guaranteed service-start event.', 'identifier'),
 'lab_id': ('string', 'Source lab identifier. Multiple variants and appointment associations occur; global visit linkage is not guaranteed.', 'identifier'),
 'lab_name': ('string', 'Source laboratory service/test label.', 'text'),
 'imaging_request_id': ('string', 'Source imaging request identifier; some IDs link to multiple appointments.', 'identifier'),
 'imaging_result_id': ('string', 'Source imaging result identifier.', 'identifier'),
 'imaging_name': ('string', 'Source imaging service label.', 'text'),
 'pharmacy_sale_line_id': ('string', 'Source pharmacy sale-line identifier; some IDs have multiple record variants.', 'identifier'),
 'medicine_name': ('string', 'Source medication/item label. Not used to infer disease.', 'text'),
 'flow_code': ('string', 'Source row-level pathway category. Not a documented intended treatment plan.', 'category'),
 'flow_name': ('string', 'Text for the recorded row-level pathway; a visit can have multiple row variants.', 'text'),
 'case_id': ('string', 'Synthetic radiology visit identifier. Event log includes cases absent from the completed-case summary.', 'identifier'),
 'exam_id': ('string', 'Exam identifier. Validate with case_id before joining; blank on non-exam events.', 'identifier'),
 'arrival_time': ('utc_datetime', 'Synthetic case arrival timestamp.', 'UTC datetime'),
 'end_time': ('utc_datetime', 'Synthetic case completion timestamp.', 'UTC datetime'),
 'patient_type': ('string', 'Radiology category: A outpatient, S emergency, H inpatient, D day-hospital.', 'category'),
 'exam_types': ('string', 'Source list-like text of modalities; preserve raw representation.', 'text list'),
 'exam_count': ('number', 'Number of exams in the completed-case summary.', 'count'),
 'total_wait_time': ('hhmm', 'Source case-level wait summary. It exceeds summed exam waits in many cases; scope is unverified and not used for exam-wait KPIs.', 'HH:MM duration'),
 'total_scan_time': ('hhmm', 'Source sum of scan durations for a completed case.', 'HH:MM duration'),
 'throughput_time': ('timedelta', 'Source duration from case arrival to completion.', 'days HH:MM:SS'),
 'week_day_of_arrival': ('string', 'Weekday derived in source case summary; differs from resource-log calendar convention.', 'weekday'),
 'hour_day_of_arrival': ('number', 'Hour of case arrival.', 'hour 0..23'),
 'modality': ('string', 'Source imaging modality label. Literal None denotes not applicable in events.', 'category'),
 'start_exam': ('utc_datetime', 'Scan service start. Verified against scan duration and the matching event interval.', 'UTC datetime'),
 'end_exam': ('utc_datetime', 'End of source exam interval.', 'UTC datetime'),
 'wait_before_exam': ('hhmm', 'Explicit source-defined pre-scan waiting duration; distinct from total exam interval.', 'HH:MM duration'),
 'scan_time_duration': ('hhmm', 'Explicit source-defined scan duration.', 'HH:MM duration'),
 'total_exam_duration': ('hhmm', 'Wait plus scan duration. This differs from end_exam minus start_exam, which measures scan service only.', 'HH:MM duration'),
 'activity': ('string', 'Source Spanish activity label; preserve to avoid guessing workflow semantics.', 'category'),
 'timestamp_start': ('utc_datetime', 'Source event interval start.', 'UTC datetime'),
 'timestamp_end': ('utc_datetime', 'Source event interval end.', 'UTC datetime'),
 'total_duration': ('hhmm', 'Source event interval duration.', 'HH:MM duration'),
 'scenario_id': ('string', 'Source subprocess/scenario label, not a unique replication ID.', 'category'),
 'avgUsage': ('number', 'Source usage statistic. Averaging-window semantics are not specified; not used as instantaneous occupancy.', 'source ratio'),
 'avail': ('number', 'Available units at the resource snapshot.', 'units'),
 'limit': ('number', 'Total units at the resource snapshot.', 'units'),
 'waitingProcesses': ('number', 'Processes waiting for this resource at the snapshot.', 'count'),
 'maxWaitTime': ('number', 'Source maximum-wait statistic; time unit/window not explicitly established in field documentation.', 'unconfirmed source unit'),
 'averageWaitTime': ('number', 'Source average-wait statistic; time unit/window not explicitly established in field documentation.', 'unconfirmed source unit'),
 'currentSimulationLocalTime': ('string', 'Snapshot clock time; has no calendar date.', 'HH:MM clock'),
 'currentSimulationDay': ('string', 'Snapshot weekday; starts Monday although case timestamps begin Sunday.', 'weekday'),
}
for stage in ['prescription', 'lab', 'imaging', 'pharmacy']:
    for endpoint in ['start', 'end']:
        definitions[f'{stage}_{endpoint}_datetime'] = ('opd_datetime',
            f'Recorded {stage} {endpoint} timestamp. Workflow meaning is not independently verified; lab end includes malformed time fragments.',
            'local datetime, timezone unspecified')

for path in sorted(RAW.rglob('*.csv')):
    source, name = path.parent.name, path.stem
    key = source + '.' + name
    df = load(path)
    tables[key] = df
    inventory.append({'source': source, 'table': name, 'rows': len(df), 'columns': len(df.columns),
                      'bytes': path.stat().st_size, 'memory_mib_strings': round(df.memory_usage(deep=True).sum() / 2**20, 3),
                      'exact_duplicates_after_first': int(df.duplicated().sum())})
    check(key, 'exact_duplicate_rows', df.duplicated(), interpretation='Source row duplicates only; repeated service data across a wide row is assessed separately.')
    for col in df:
        if col.startswith('Unnamed:'):
            kind, desc, unit = 'string', 'Empty source header/column artifact; remove only from prepared copies.', 'none'
        else:
            assert col in definitions, f'Undocumented column: {col}'
            kind, desc, unit = definitions[col]
        series = df[col]
        if kind == 'opd_datetime': parsed = opd_datetime(series)
        elif kind == 'utc_datetime': parsed = utc_datetime(series)
        elif kind == 'number': parsed = pd.to_numeric(series, errors='coerce')
        elif kind == 'hhmm': parsed = hhmm_minutes(series)
        elif kind == 'timedelta': parsed = pd.to_timedelta(series, errors='coerce')
        else: parsed = series
        invalid = series.notna() & parsed.isna()
        if kind != 'string': check(key, col + ': parse', invalid, series.notna().sum(), 'error')
        dictionary.append({'source': source, 'table': name, 'column': col, 'description': desc,
                           'expected_type': kind, 'analysis_dtype': str(parsed.dtype), 'unit': unit,
                           'missing': int(series.isna().sum()), 'missing_pct': round(series.isna().mean() * 100, 3),
                           'distinct_non_null': int(series.nunique()), 'invalid_nonempty': int(invalid.sum()),
                           'missing_interpretation': 'Usually not-applicable if service absent; otherwise review' if source == 'opd' and col.startswith(('lab_', 'imaging_', 'pharmacy_', 'medicine_')) else 'Field-specific; see description'})
inventory, dictionary = pd.DataFrame(inventory), pd.DataFrame(dictionary)
opd = tables['opd.HospitalOPD-noname']
cases, exams, revents = [tables['radiology.' + name] for name in ['cases', 'exams', 'events']]
show(inventory.groupby('source').agg(csv_files=('table', 'size'), rows=('rows', 'sum'), bytes=('bytes', 'sum'), memory_mib_strings=('memory_mib_strings', 'sum')).reset_index())
print('OPD patients:', opd.patient_id.nunique(), '| distinct appointments:', opd.appointment_id.nunique())

# %% OPD checks and safe stage extraction
OPD_KEY = 'opd.HospitalOPD-noname'
for col in ['record_no', 'patient_id', 'appointment_id', 'appointment_start_datetime', 'prescription_order_id']:
    check(OPD_KEY, col + ': required_missing', opd[col].isna(), severity='error')
check(OPD_KEY, 'record_no_duplicate', opd.record_no.duplicated(), severity='error')
check(OPD_KEY, 'duplicate_business_row_excluding_record_no', opd.drop(columns='record_no').duplicated())
appointment_people = opd.groupby('appointment_id').patient_id.nunique()
check(OPD_KEY, 'appointment_multiple_patients', appointment_people > 1, severity='error')
date_ranges = []
for col in [c for c in opd if c.endswith('_datetime')]:
    parsed = opd_datetime(opd[col])
    date_ranges.append({'source': 'opd', 'field': col, 'valid_rows': int(parsed.notna().sum()),
                        'min': str(parsed.min()), 'max': str(parsed.max()), 'timezone': 'unspecified local'})
for stage in ['prescription', 'lab', 'imaging', 'pharmacy']:
    start, end = [opd_datetime(opd[f'{stage}_{edge}_datetime']) for edge in ['start', 'end']]
    valid = start.notna() & end.notna()
    check(OPD_KEY, stage + ': end_before_start', valid & (end < start), valid.sum(), 'error')
    check(OPD_KEY, stage + ': start_before_appointment', start.notna() & (start < opd_datetime(opd.appointment_start_datetime)), start.notna().sum(), 'review', 'An association or date issue; do not interpret negative gaps as waiting.')

# Construct stage records from the wide file without multiplying rows by joining its services.
# A record variant is a distinct payload, not a claim that every variant is a separate service.
stage_specs = {
 'appointment': ('appointment_id', 'appointment_start_datetime', None, None, None),
 'prescription': ('prescription_order_id', 'prescription_start_datetime', 'prescription_end_datetime', 'prescription_doctor_id', None),
 'lab': ('lab_id', 'lab_start_datetime', 'lab_end_datetime', None, 'lab_name'),
 'imaging': ('imaging_request_id', 'imaging_start_datetime', 'imaging_end_datetime', None, 'imaging_name'),
 'pharmacy': ('pharmacy_sale_line_id', 'pharmacy_start_datetime', 'pharmacy_end_datetime', None, 'medicine_name'),
}
opd_events, lineage_parts, stage_profiles = [], [], []
for stage, (id_col, start_col, end_col, resource_col, label_col) in stage_specs.items():
    sub = opd.loc[opd[id_col].notna()].copy()
    payload = ['patient_id', id_col, start_col] + [c for c in [end_col, resource_col, label_col] if c]
    signatures = sub[payload].apply(lambda row: hashlib.sha256(json.dumps([None if pd.isna(x) else str(x) for x in row], separators=(',', ':')).encode()).hexdigest()[:24], axis=1)
    sub['_event_key'] = 'opd:' + stage + ':' + signatures
    links = pd.DataFrame({'event_key': sub['_event_key'], 'case_key': 'opd:' + sub.appointment_id,
                          'source_row': sub.record_no, 'source_activity': stage,
                          'source_natural_id': sub[id_col]})
    lineage_parts.append(links)
    natural_case_counts = sub.groupby(id_col).appointment_id.nunique()
    natural_variant_counts = sub.groupby(id_col)['_event_key'].nunique()
    unique = sub.drop_duplicates('_event_key').copy()
    event_case_counts = sub.groupby('_event_key').appointment_id.nunique()
    start = opd_datetime(unique[start_col])
    end = opd_datetime(unique[end_col]) if end_col else pd.Series(pd.NaT, index=unique.index)
    duration = (end - start).dt.total_seconds() / 60
    natural_ambiguous = unique[id_col].map(natural_case_counts) > 1
    variant_conflict = unique[id_col].map(natural_variant_counts) > 1
    precedes_appointment = (start < opd_datetime(unique.appointment_start_datetime)).fillna(False)
    duration_valid = start.notna() & end.notna() & (duration >= 0)
    frame = pd.DataFrame({
        'source_system': 'opd', 'source_nature': 'publisher_reported_anonymized_observational',
        'event_key': unique['_event_key'],
        'case_key': ('opd:' + unique.appointment_id).mask(natural_ambiguous),
        'patient_key': 'opd:' + unique.patient_id, 'activity': stage,
        'source_natural_id': unique[id_col], 'source_row': unique.record_no,
        'start_raw': unique[start_col], 'end_raw': unique[end_col] if end_col else pd.NA,
        'start_time': start.astype('string'), 'end_time': end.astype('string'),
        'clock_basis': 'local_timezone_unspecified', 'elapsed_minutes': duration.where(duration_valid),
        'duration_valid': duration_valid, 'ambiguous_visit_link': natural_ambiguous,
        'multiple_payload_variants': variant_conflict,
        'precedes_linked_appointment': precedes_appointment,
        'eligible_interval_summary': duration_valid & ~natural_ambiguous & ~variant_conflict & ~precedes_appointment,
        'resource_key': ('opd:provider:' + unique[resource_col]) if resource_col else pd.NA,
        'source_label': unique[label_col] if label_col else pd.NA,
        'metric_semantics': 'appointment_anchor' if stage == 'appointment' else 'recorded_interval_not_verified_queue_wait',
    })
    opd_events.append(frame)
    stage_profiles.append({'stage': stage, 'source_rows': len(sub), 'natural_ids': sub[id_col].nunique(),
                           'record_variants': len(unique), 'ids_linked_to_multiple_visits': int((natural_case_counts > 1).sum()),
                           'ids_with_multiple_payloads': int((natural_variant_counts > 1).sum()),
                           'eligible_nonnegative_intervals': int(frame.eligible_interval_summary.sum())})
    check(OPD_KEY, stage + ': natural_id_multiple_visits', natural_case_counts > 1,
          interpretation='Retain associations in lineage; do not assign these records to a single visit.')
    check(OPD_KEY, stage + ': natural_id_multiple_payloads', natural_variant_counts > 1,
          interpretation='Keep variants. Excluded from default interval summaries until source grain is resolved.')
opd_events = pd.concat(opd_events, ignore_index=True)
lineage = pd.concat(lineage_parts, ignore_index=True)
stage_profiles = pd.DataFrame(stage_profiles)
visits = opd[['appointment_id', 'patient_id', 'appointment_start_datetime']].drop_duplicates().copy()
assert visits.appointment_id.is_unique
visits['case_key'], visits['patient_key'] = 'opd:' + visits.appointment_id, 'opd:' + visits.patient_id
visits['source_system'] = 'opd'
visit_flow_codes = opd.groupby('appointment_id').flow_code.agg(lambda x: ','.join(sorted(x.dropna().unique())))
visits['recorded_flow_codes'] = visits.appointment_id.map(visit_flow_codes)
print('Distinct source record variants, not new synthetic observations:')
show(stage_profiles)

# %% Radiology relationships and duration consistency
check('radiology.cases', 'case_id_duplicate', cases.case_id.duplicated(), severity='error')
check('radiology.exams', 'case_exam_key_duplicate', exams.duplicated(['case_id', 'exam_id']), severity='error')
check('radiology.exams', 'case_missing_from_case_summary', ~exams.case_id.isin(cases.case_id), severity='error')
check('radiology.events', 'case_missing_from_case_summary', ~revents.case_id.isin(cases.case_id), interpretation='Incomplete/snapshot-boundary cases are possible. This is not an abandonment indicator.')
exam_index = pd.MultiIndex.from_frame(exams[['case_id', 'exam_id']])
event_exam_index = pd.MultiIndex.from_frame(revents[['case_id', 'exam_id']])
check('radiology.events', 'nonempty_exam_reference_missing', revents.exam_id.notna() & ~event_exam_index.isin(exam_index), revents.exam_id.notna().sum(), 'error')
case_patient_type = revents.case_id.map(cases.set_index('case_id').patient_type)
check('radiology.events', 'patient_type_disagrees_with_case', case_patient_type.notna() & (revents.patient_type != case_patient_type), case_patient_type.notna().sum(), 'error')

numeric_exams = exams.copy()
for col in ['wait_before_exam', 'scan_time_duration', 'total_exam_duration']:
    numeric_exams[col + '_minutes'] = hhmm_minutes(exams[col])
ex_elapsed = (utc_datetime(exams.end_exam) - utc_datetime(exams.start_exam)).dt.total_seconds() / 60
check('radiology.exams', 'end_before_start', ex_elapsed < 0, ex_elapsed.notna().sum(), 'error')
check('radiology.exams', 'scan_interval_disagrees_with_scan_duration', (ex_elapsed - numeric_exams.scan_time_duration_minutes).abs() > 1e-6, ex_elapsed.notna().sum(), 'error')
check('radiology.exams', 'wait_plus_scan_disagrees_with_total', (numeric_exams.wait_before_exam_minutes + numeric_exams.scan_time_duration_minutes - numeric_exams.total_exam_duration_minutes).abs() > 1e-6, severity='error')
case_sums = numeric_exams.groupby('case_id').agg(n=('exam_id', 'size'), wait=('wait_before_exam_minutes', 'sum'), scan=('scan_time_duration_minutes', 'sum'))
for field, aggregate in [('exam_count', 'n'), ('total_wait_time', 'wait'), ('total_scan_time', 'scan')]:
    observed = pd.to_numeric(cases[field]) if field == 'exam_count' else hhmm_minutes(cases[field])
    expected = cases.case_id.map(case_sums[aggregate])
    check('radiology.cases', field + ': disagrees_with_exam_aggregate', expected.isna() | ((observed - expected).abs() > 1e-6),
          severity='review' if field == 'total_wait_time' else 'error',
          interpretation='Case-level wait scope differs from exam-level sums; do not use it as an exam-wait KPI.' if field == 'total_wait_time' else '')
case_elapsed = (utc_datetime(cases.end_time) - utc_datetime(cases.arrival_time)).dt.total_seconds() / 60
check('radiology.cases', 'throughput_disagrees_with_interval', (case_elapsed - pd.to_timedelta(cases.throughput_time).dt.total_seconds() / 60).abs() > 1e-6, severity='error')

ev_start, ev_end = utc_datetime(revents.timestamp_start), utc_datetime(revents.timestamp_end)
ev_elapsed = (ev_end - ev_start).dt.total_seconds() / 60
check('radiology.events', 'end_before_start', ev_elapsed < 0, ev_elapsed.notna().sum(), 'error')
check('radiology.events', 'duration_disagrees_with_interval', (ev_elapsed - hhmm_minutes(revents.total_duration)).abs() > 1e-6, severity='error')
case_arrival = utc_datetime(revents.case_id.map(cases.set_index('case_id').arrival_time))
case_end = utc_datetime(revents.case_id.map(cases.set_index('case_id').end_time))
check('radiology.events', 'event_outside_completed_case_interval', (ev_start < case_arrival) | (ev_end > case_end), case_end.notna().sum())
exam_event_rows = revents.loc[revents.exam_id.notna(), ['case_id', 'exam_id', 'timestamp_start', 'timestamp_end']]
assert not exam_event_rows.duplicated(['case_id', 'exam_id']).any()
numeric_exams = numeric_exams.merge(exam_event_rows, on=['case_id', 'exam_id'], how='left', validate='one_to_one')
numeric_exams['queue_entry_time'] = numeric_exams.timestamp_start
numeric_exams['service_start_time'] = numeric_exams.start_exam
numeric_exams['service_end_time'] = numeric_exams.end_exam
numeric_exams['timestamp_wait_minutes'] = (utc_datetime(numeric_exams.start_exam) - utc_datetime(numeric_exams.timestamp_start)).dt.total_seconds() / 60
numeric_exams['wait_validated'] = ((numeric_exams.timestamp_wait_minutes - numeric_exams.wait_before_exam_minutes).abs() <= 1e-6) & (numeric_exams.timestamp_wait_minutes >= 0)
check('radiology.exams', 'explicit_wait_disagrees_with_linked_timestamps', ~numeric_exams.wait_validated, severity='error')
check('radiology.exams', 'exam_end_disagrees_with_event_end', utc_datetime(numeric_exams.end_exam) != utc_datetime(numeric_exams.timestamp_end), severity='error')
radio_join = revents.merge(cases[['case_id', 'arrival_time', 'end_time']], on='case_id', how='left', validate='many_to_one', indicator=True)
assert len(radio_join) == len(revents)
radio_join = radio_join.merge(exams[['case_id', 'exam_id', 'wait_before_exam', 'scan_time_duration']], on=['case_id', 'exam_id'], how='left', validate='many_to_one')
assert len(radio_join) == len(revents)
radio_join['case_summary_present'] = radio_join['_merge'].eq('both')
radio_join = radio_join.drop(columns='_merge')
# Joined exam/case measures repeat across events: never sum them at event grain.
radio_join.to_csv(PREP / 'radiology_events_with_context.csv.gz', index=False, compression='gzip')
radio_events = pd.DataFrame({
    'source_system': 'radiology', 'source_nature': 'synthetic_simulation',
    'event_key': ['radiology:event:' + str(i + 1) for i in revents.index],
    'case_key': 'radiology:' + revents.case_id, 'patient_key': pd.NA,
    'activity': revents.activity, 'source_natural_id': revents.exam_id,
    'source_row': revents.index + 2, 'start_raw': revents.timestamp_start, 'end_raw': revents.timestamp_end,
    'start_time': ev_start.astype('string'), 'end_time': ev_end.astype('string'),
    'clock_basis': 'UTC', 'elapsed_minutes': ev_elapsed.where(ev_elapsed >= 0),
    'duration_valid': ev_elapsed.notna() & (ev_elapsed >= 0),
    'ambiguous_visit_link': False, 'multiple_payload_variants': False, 'precedes_linked_appointment': False,
    'eligible_interval_summary': ev_elapsed.notna() & (ev_elapsed >= 0),
    'resource_key': pd.NA, 'source_label': revents.modality,
    'metric_semantics': 'source_activity_interval_may_include_wait_and_service',
})
case_coverage = pd.DataFrame({'case_id': sorted(set(revents.case_id.dropna()) | set(cases.case_id.dropna()))})
case_coverage['case_summary_present'] = case_coverage.case_id.isin(cases.case_id)
case_coverage['event_rows'] = case_coverage.case_id.map(revents.case_id.value_counts()).fillna(0).astype(int)
case_coverage['interpretation'] = np.where(case_coverage.case_summary_present, 'completed_case_summary_available', 'case_summary_missing_outcome_unknown')
show(pd.DataFrame(checks).query('flagged > 0')[['table', 'rule', 'evaluated', 'flagged']], 25)

# %% Resource snapshots and safe integration
resource_parts, resource_profiles = [], []
days = {day: i for i, day in enumerate(['MONDAY', 'TUESDAY', 'WEDNESDAY', 'THURSDAY', 'FRIDAY', 'SATURDAY', 'SUNDAY'])}
for key, frame in tables.items():
    if not key.endswith('_usage'):
        continue
    name = key.split('.', 1)[1].removeprefix('Escenario_Examinacion_').removesuffix('_usage')
    df = frame.copy()
    for col in ['avgUsage', 'avail', 'limit', 'waitingProcesses', 'maxWaitTime', 'averageWaitTime']:
        df[col] = pd.to_numeric(df[col], errors='coerce')
        check(key, col + ': negative', df[col] < 0, df[col].notna().sum())
    check(key, 'available_exceeds_capacity', df.avail > df['limit'], severity='error')
    clock = df.currentSimulationLocalTime.str.split(':', expand=True).astype(int)
    relative_minutes = df.currentSimulationDay.map(days) * 1440 + clock[0] * 60 + clock[1]
    check(key, 'non_five_minute_step', relative_minutes.diff().dropna() != 5, len(df) - 1, 'error')
    check(key, 'duplicate_relative_time', relative_minutes.duplicated(), severity='error')
    df['resource_id'], df['source_system'] = name, 'radiology'
    df['relative_minute_monday_origin'] = relative_minutes
    df['occupied_units'] = df['limit'] - df.avail
    df['snapshot_occupancy_fraction'] = df.occupied_units / df['limit'].where(df['limit'] > 0)
    df['calendar_join_validated'] = False
    resource_parts.append(df)
    # Equal-weight snapshot mean only, not exact continuous-time utilization.
    resource_profiles.append({'resource_id': name, 'snapshots': len(df),
                               'capacity_min': df['limit'].min(), 'capacity_max': df['limit'].max(),
                               'snapshot_occupancy_pct': round(df.snapshot_occupancy_fraction.mean() * 100, 3),
                               'mean_queue_count': round(df.waitingProcesses.mean(), 3),
                               'max_queue_count': df.waitingProcesses.max(),
                               'calendar_join_validated': False})
resources = pd.concat(resource_parts, ignore_index=True)
resource_profiles = pd.DataFrame(resource_profiles)
events = pd.concat([opd_events, radio_events], ignore_index=True)
assert events.event_key.is_unique, 'Prepared event keys are not unique.'
assert len(events) == len(opd_events) + len(revents), 'Source union changed event counts.'
assert lineage.event_key.isin(opd_events.event_key).all()
assert lineage.case_key.isin(visits.case_key).all()
print('Integrated record variants:', len(events), '| resource snapshots:', len(resources))
print('Integration is a source-labeled UNION, never a cross-source patient join.')
print('Radiology resource weekdays start Monday; case timestamps start Sunday. No absolute-time join is made.')

# %% Exploratory summaries and exports
# Summaries establish feasibility and exclusions; they are not final hospital-performance claims.
interval_summary = events.loc[events.eligible_interval_summary].groupby(['source_system', 'activity']).elapsed_minutes.agg(
    eligible_records='size', median_minutes='median', mean_minutes='mean', p95_minutes=lambda x: x.quantile(.95)).reset_index()
radio_wait_summary = numeric_exams.loc[numeric_exams.wait_validated].groupby('modality').wait_before_exam_minutes.agg(
    exams='size', median_wait_minutes='median', mean_wait_minutes='mean', p95_wait_minutes=lambda x: x.quantile(.95)).reset_index()
appointment_times = opd_datetime(visits.appointment_start_datetime)
monthly = visits.assign(month=appointment_times.dt.to_period('M').astype('string')).groupby('month').agg(appointments=('case_key', 'size'), patients=('patient_key', 'nunique')).reset_index()
service_coverage = lineage.groupby('source_activity').agg(source_rows=('source_row', 'size'), recorded_appointments=('case_key', 'nunique')).reset_index()
service_coverage['all_appointments'] = len(visits)
service_coverage['recorded_appointment_pct'] = service_coverage.recorded_appointments / len(visits) * 100
service_coverage['interpretation'] = 'Recorded associations, not eligible-pathway completion or abandonment'
check_frame = pd.DataFrame(checks)
dictionary.to_csv(OUT / 'data_dictionary.csv', index=False, encoding='utf-8-sig')
exports = {'table_inventory': inventory, 'validation_checks': check_frame, 'anomaly_record_positions': pd.DataFrame(samples),
           'opd_stage_grain_audit': stage_profiles, 'radiology_case_coverage': case_coverage,
           'source_interval_summary': interval_summary.round(3), 'radiology_wait_summary': radio_wait_summary.round(3),
           'resource_snapshot_summary': resource_profiles, 'opd_monthly_coverage': monthly,
           'opd_recorded_service_coverage': service_coverage.round(3), 'date_ranges': pd.DataFrame(date_ranges)}
for name, frame in exports.items():
    frame.to_csv(OUT / (name + '.csv'), index=False, encoding='utf-8-sig')
for name, frame in [('events', events), ('opd_visits', visits), ('opd_event_lineage', lineage),
                    ('radiology_exams', numeric_exams), ('radiology_cases', cases), ('resource_snapshots', resources)]:
    frame.to_csv(PREP / (name + '.csv.gz'), index=False, compression='gzip')
show(radio_wait_summary.round(3))
show(stage_profiles)

# %% Reports and measured footprint
raw_bytes = sum((ROOT / s['path']).stat().st_size for s in specs)
prepared_bytes = sum(p.stat().st_size for p in PREP.glob('*.csv.gz'))
mem_events = events.memory_usage(deep=True).sum() / 2**20
stats = {'opd_source_rows': len(opd), 'opd_patients': int(opd.patient_id.nunique()), 'opd_visits': len(visits),
         'radiology_completed_cases': len(cases), 'radiology_cases_in_event_log': int(revents.case_id.nunique()),
         'radiology_exams': len(exams), 'radiology_events': len(revents), 'resource_snapshots': len(resources),
         'resource_series': len(resource_profiles), 'prepared_event_variants': len(events),
         'raw_csv_rows': int(inventory.rows.sum()), 'raw_csv_files': len(inventory),
         'raw_download_mib': round(raw_bytes / 2**20, 2), 'prepared_compressed_mib': round(prepared_bytes / 2**20, 2),
         'raw_dataframes_mib': round(inventory.memory_mib_strings.sum(), 2),
         'events_dataframe_mib': round(mem_events, 2), 'validation_rules': len(check_frame),
         'rules_flagging_records': int((check_frame.flagged > 0).sum()),
         'elapsed_seconds_before_report_write': round(time.perf_counter() - STARTED, 2),
         'python': sys.version.split()[0], 'pandas': pd.__version__, 'numpy': np.__version__,
         'verified_at_utc': datetime.now(timezone.utc).isoformat()}
(OUT / 'run_summary.json').write_text(json.dumps(stats, indent=2), encoding='utf-8')

dictionary_sections = ['# Data dictionary',
    'These definitions describe the inspected source files. Source-specific IDs are strings. '
    'OPD times are timezone-unspecified local times; radiology event times are UTC. '
    'HH:MM duration strings are hours and minutes. Empty optional stage columns often mean not applicable, not a failed service. '
    'See [HospitalOPD](https://data.mendeley.com/datasets/j2hd2239dr/1) and '
    '[radiology dataset documentation](https://data.mendeley.com/datasets/jsg8c4yhxy/2).']
for (source, table), group in dictionary.groupby(['source', 'table']):
    if table.endswith('_usage'):
        continue
    dictionary_sections += ['## ' + source + '.' + table, md(group[['column', 'expected_type', 'unit', 'description', 'missing', 'invalid_nonempty']])]
resource_dict = dictionary[dictionary.table.str.endswith('_usage')].drop_duplicates('column')
dictionary_sections += ['## Radiology resource snapshot files',
    'The following schema is shared by all 25 resource CSVs. Missingness for each individual file is in data_dictionary.csv.',
    md(resource_dict[['column', 'expected_type', 'unit', 'description']])]
(OUT / 'data_dictionary.md').write_text('\n\n'.join(dictionary_sections), encoding='utf-8')

flagged = check_frame[check_frame.flagged > 0]
bad_lab = int((opd.lab_end_datetime.notna() & opd_datetime(opd.lab_end_datetime).isna()).sum())
missing_case_count = int((~case_coverage.case_summary_present).sum())
report = f'''# Data quality and source suitability report

Healthcare Friction Observatory. Revised Step 1. Verified on {stats['verified_at_utc']}.

## Decision and scale

Use HospitalOPD as the main recorded outpatient-workflow source and the radiology simulation as a separate resource/queue benchmark.
HospitalOPD is described by its publisher as anonymized observational data; its collection and timestamp semantics were not independently audited.
Radiology is explicitly synthetic. No new patients were generated and no source rows were repeated to inflate dataset size.

The package contains {stats['opd_visits']:,} distinct OPD appointments for {stats['opd_patients']:,} patients in {len(opd):,} wide source rows.
Radiology adds {len(revents):,} event rows, {len(exams):,} exams, {len(cases):,} completed-case summaries and {len(resources):,} resource snapshots.
The prepared event view contains {len(events):,} source record variants across the two systems. This is not a patient count or a count of independent observations.
The old Synthea and small emergency datasets remain in the original project folder as prior work. They are excluded from this package's active data and KPIs.

## Loading size

Full downloads, including documentation/image/configuration: {stats['raw_download_mib']} MiB.
Prepared gzip CSVs: {stats['prepared_compressed_mib']} MiB. All raw CSV dataframes together: {stats['raw_dataframes_mib']} MiB as measured by pandas deep memory usage.
Prepared event dataframe: {stats['events_dataframe_mib']} MiB. These are object sizes, not peak process RAM; joins and copies need extra memory.
Load one prepared file at a time, or use read_csv(..., chunksize=50000). No patient sampling was required.
Dates and categoricals can be converted after selecting columns. The notebook does not load the old datasets.

## Inventory

{md(inventory[['source', 'table', 'rows', 'columns', 'exact_duplicates_after_first']])}

## Important findings and actions

| Issue | Evidence / meaning | Required handling |
| --- | --- | --- |
| OPD row grain | Multiple prescriptions/services repeat appointment data | Count visits by appointment_id, not raw rows. Use the stage-grain audit. |
| Incomplete lab end timestamps | {bad_lab:,} nonempty source lab_end_datetime values fail the documented date parser, including fragments such as 53:45.0 | Keep raw values, leave parsed end time/duration missing, and exclude from duration denominators. Do not invent a date or hour. |
| Cross-appointment service associations | Some lab and imaging IDs occur against multiple appointments | Retain lineage. Leave the prepared case_key null for ambiguous natural IDs. Do not count them as independently completed services in every visit. |
| Multiple payload variants | Some natural service IDs have different labels/times | Retain distinct payloads, flag them and exclude from default interval summaries pending grain confirmation. |
| Negative prescription intervals | See exact source-row counts below | Quarantine for duration reporting; do not swap endpoints automatically. |
| Case-level radiology wait has a different scope | Many case totals exceed summed exam waits | Do not substitute case total_wait_time for exam waiting. The exam wait values are independently checked against queue-entry and scan-start timestamps. |
| Missing radiology case summaries | {missing_case_count} event-log cases lack completed-case summaries | Retain events and mark outcome unknown. Possible window truncation is not proven abandonment. |
| Resource calendar mismatch | Resource logs start Monday; Jan 1, 2023 case events start Sunday | Use relative resource time only. Do not join resource snapshots to event calendar dates without confirmation. |
| Small pharmacy coverage | See recorded service coverage | Report sample size and missing applicability; avoid unstable pharmacy rankings. |
| OPD service availability differs over time | Lab, imaging and pharmacy have shorter observed coverage than appointments | Compare periods with matched coverage; do not read early blanks as no demand. |
| Source names are not physical queue states | Prescription and appointment timestamps have limited definitions | Label appointment-to-prescription gap as a proxy. Never call it verified door-to-doctor wait. |

## Checks and evidence

{len(check_frame)} rules executed. {len(flagged)} rules flag records/groups. Counts below use each rule's stated denominator; flagged counts overlap and must not be added as unique bad rows.
Raw files passed published SHA-256 checks. All source rows remain available. Source record examples are located by file and row position in anomaly_record_positions.csv.

{md(flagged[['table', 'rule', 'evaluated', 'flagged', 'interpretation']])}

## Missing values

Only empty/whitespace values become missing during parsing. Literal None is preserved in the raw radiology modality field because it means not applicable.
Optional OPD stage columns are often structurally absent. A requested-but-not-completed service cannot be distinguished from not-required using blanks alone.
The empty Unnamed: 2 column in OPD is a file artifact. It is omitted from prepared tables but documented in the raw dictionary.
Clinician names are preserved in the licensed raw file but omitted from prepared records; provider IDs remain available.

{md(dictionary[(dictionary.source == 'opd') & (dictionary.missing > 0)][['column', 'missing', 'missing_pct', 'invalid_nonempty']])}

## Safe integration

1. OPD appointments map to patients within OPD only. Stage payloads are extracted without cross-multiplying lab, imaging, prescription and pharmacy rows.
2. Every extracted OPD payload links back to all of its source rows and candidate appointments through opd_event_lineage.csv.gz.
3. Radiology events join cases and exams using validated many-to-one joins. Event row counts are preserved. Orphan case summaries remain missing.
4. The common event file is a UNION with source_system and source_nature. It is not one hospital population. Patient and case IDs are namespaced.
5. Resource snapshots are a separate fact-like table at resource/relative-time grain, not attached to patients. No unsupported date alignment is applied.

Never sum repeated case or exam measures in radiology_events_with_context. Aggregate case/exam measures in their own tables.
Do not pool OPD and radiology elapsed times into an overall hospital average.

## What the six project questions can support

| Question | Support in revised package | Remaining limit |
| --- | --- | --- |
| Wait before doctor | OPD appointment-to-prescription-start gap is calculable after visit filtering | A proxy only: appointment timestamp is not confirmed physical arrival; prescription start is not confirmed physician contact. |
| Longest waiting stage | Radiology has explicit exam wait and scan duration, grouped by modality | OPD service durations/gaps are different metrics and must not be ranked as the same queue wait. |
| Lab bottleneck | OPD lab intervals and workload patterns for valid, unambiguous records | No separate lab queue-entry/service-start or lab staffing. Call findings long recorded turnaround, not proven capacity shortage. |
| Journey noncompletion | Missing summaries and service coverage can be reported | No validated abandonment/disposition field or intended-route denominator. Do not publish abandonment rates. |
| Resource sufficiency | Radiology capacity, available-unit snapshots, queues and configuration | Synthetic benchmark; snapshot occupancy is approximate and calendar alignment remains unresolved. |
| Add a staff member/device | Radiology arrival/service distributions and resource configuration support model development | Person 5 must implement and validate a simulator; no causal improvement percentages are claimed here. |

## Exploratory queue evidence

The table below uses explicit wait_before_exam values that agree with (scan start minus matching event start).
The exam interval end minus start also agrees with scan_time_duration. The enclosing event interval includes wait plus scan.
Only validated exam waits enter this table. These are synthetic baseline statistics, not actual hospital performance.

{md(radio_wait_summary.round(3))}

## Source selection and limits

- [HospitalOPD v1](https://data.mendeley.com/datasets/j2hd2239dr/1), DOI 10.17632/j2hd2239dr.1, CC BY 4.0. Main outpatient source. Full source retained.
- [Radiology workflow simulation v2](https://data.mendeley.com/datasets/jsg8c4yhxy/2), DOI 10.17632/jsg8c4yhxy.2, CC BY 4.0. Supporting queue/resource source. Full source retained.
- A larger [research ED event log](https://zenodo.org/records/18785676) was considered, but download requests were blocked by the host's unusual-traffic filter. Its content was not profiled or included.
- A [1.55-million-event synthetic hospital dataset](https://huggingface.co/datasets/AuricGrid-Laboratory/E3.H2-Synthetic_Hospital_Operations_Environment) requires manual access approval and is approximately 500 MB CSV. Not included.
- MIMIC-IV requires credentialed access and is not needed for this manageable Step 1 package.

More rows do not repair missing timestamps, invalid linkage or unrepresentative source assumptions.
No dataset here establishes Egyptian hospital performance. Report source-specific findings and denominators.

## Reproducibility and handoff

Python {stats['python']}; pandas {stats['pandas']}; NumPy {stats['numpy']}.
Source hashes and URLs: data/metadata/sources.json. Full outputs: reports/ and data/exploration/.
Run scripts/download.py then scripts/explore.py from step1_v2, or use the self-contained notebook.
The prepared tables are exploratory exports with flags and lineage; production ETL and warehouse design remain the next teammates' responsibility.
'''
(OUT / 'data_quality_report.md').write_text(report, encoding='utf-8')
# Portable HTML view of the report, preserving readable Markdown as preformatted text.
html_report = '<!doctype html><html lang="en"><meta charset="utf-8"><title>Healthcare Friction — Step 1</title><style>body{margin:36px auto;max-width:1500px;padding:0 24px;background:#f7f9fc;color:#15253a;font:16px/1.6 system-ui}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:white;padding:28px;border:1px solid #d8e1ea;border-radius:10px;font:14px/1.6 ui-monospace,monospace}</style><h1>Healthcare Friction Observatory</h1><p>Revised data collection and exploration report</p><pre>' + html.escape(report) + '</pre></html>'
(OUT / 'data_quality_report.html').write_text(html_report, encoding='utf-8')
print(json.dumps(stats, indent=2))
print('Saved complete source profiles, evidence, dictionaries and compressed exploratory tables.')
