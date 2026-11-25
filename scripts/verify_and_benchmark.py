"""Independent checks of the handoff files and a measured pandas loading benchmark."""
from pathlib import Path
import gc
import json
import time
import pandas as pd
from load_data import read_prepared

ROOT = Path(__file__).resolve().parents[1]
OUT, PREP = ROOT / 'reports', ROOT / 'data/exploration'
results = []

def load_timed(name, columns=None, mode='full'):
    started = time.perf_counter()
    frame = read_prepared(name, usecols=columns)
    results.append({'file': name, 'mode': mode, 'rows': len(frame), 'columns': len(frame.columns),
                    'load_seconds': round(time.perf_counter() - started, 4),
                    'dataframe_mib': round(frame.memory_usage(deep=True).sum() / 2**20, 3),
                    'compressed_mib': round((PREP / name).stat().st_size / 2**20, 3)})
    return frame

events = load_timed('events.csv.gz')
assert events.event_key.is_unique
assert events.event_key.str.startswith(tuple(['opd:', 'radiology:'])).all()
assert events.loc[events.source_system.eq('opd'), 'patient_key'].str.startswith('opd:').all()
assert events.loc[events.source_system.eq('radiology'), 'patient_key'].isna().all()
assert events.loc[events.ambiguous_visit_link, 'case_key'].isna().all()
eligible = events.loc[events.eligible_interval_summary]
assert eligible.elapsed_minutes.notna().all() and eligible.elapsed_minutes.ge(0).all()
assert not eligible[['ambiguous_visit_link', 'multiple_payload_variants', 'precedes_linked_appointment']].any().any()
visits = load_timed('opd_visits.csv.gz')
lineage = load_timed('opd_event_lineage.csv.gz')
assert visits.case_key.is_unique
assert lineage.event_key.isin(events.event_key).all()
assert lineage.case_key.isin(visits.case_key).all()
raw_opd = pd.read_csv(ROOT / 'data/raw/opd/HospitalOPD-noname.csv', dtype='string')
stage_ids = {'appointment': 'appointment_id', 'prescription': 'prescription_order_id',
             'lab': 'lab_id', 'imaging': 'imaging_request_id', 'pharmacy': 'pharmacy_sale_line_id'}
for stage, col in stage_ids.items():
    actual = lineage.loc[lineage.source_activity.eq(stage), 'source_row'].astype(str).sort_values().tolist()
    expected = raw_opd.loc[raw_opd[col].notna(), 'record_no'].astype(str).sort_values().tolist()
    assert actual == expected, 'Source-row association lost or invented: ' + stage
del raw_opd, lineage, eligible
gc.collect()

exams = load_timed('radiology_exams.csv.gz')
assert len(exams) == 3503 and exams.wait_validated.all()
wait = (pd.to_datetime(exams.service_start_time, utc=True) - pd.to_datetime(exams.queue_entry_time, utc=True)).dt.total_seconds() / 60
scan = (pd.to_datetime(exams.service_end_time, utc=True) - pd.to_datetime(exams.service_start_time, utc=True)).dt.total_seconds() / 60
assert ((wait - exams.wait_before_exam_minutes).abs() < 1e-8).all()
assert ((scan - exams.scan_time_duration_minutes).abs() < 1e-8).all()
assert ((wait + scan - exams.total_exam_duration_minutes).abs() < 1e-8).all()
radio_context = load_timed('radiology_events_with_context.csv.gz')
assert len(radio_context) == len(events[events.source_system.eq('radiology')]) == 27343
resources = load_timed('resource_snapshots.csv.gz')
assert not resources.duplicated(['resource_id', 'relative_minute_monday_origin']).any()
assert resources.snapshot_occupancy_fraction.between(0, 1).all()
assert not resources.calendar_join_validated.any()
assert len(resources) == 50375
del exams, radio_context, resources, visits, events
gc.collect()
projected = load_timed('events.csv.gz', ['source_system', 'case_key', 'activity', 'elapsed_minutes', 'eligible_interval_summary'], 'selected_columns')
row_count = len(projected)
del projected
gc.collect()
started = time.perf_counter()
chunk_rows = 0
max_chunk_mib = 0
for chunk in read_prepared('events.csv.gz', chunksize=50000):
    chunk_rows += len(chunk)
    max_chunk_mib = max(max_chunk_mib, chunk.memory_usage(deep=True).sum() / 2**20)
assert chunk_rows == row_count
results.append({'file': 'events.csv.gz', 'mode': '50000_row_chunks', 'rows': chunk_rows,
                'columns': len(chunk.columns), 'load_seconds': round(time.perf_counter() - started, 4),
                'dataframe_mib': round(max_chunk_mib, 3), 'compressed_mib': round((PREP / 'events.csv.gz').stat().st_size / 2**20, 3)})
pd.DataFrame(results).to_csv(OUT / 'loading_benchmark.csv', index=False)
nb = json.loads((ROOT / 'notebooks/01_operational_data_collection_and_exploration.ipynb').read_text(encoding='utf-8'))
code_cells = [c for c in nb['cells'] if c['cell_type'] == 'code']
assert len(code_cells) == 8 and all(c['execution_count'] for c in code_cells)
assert not any(o['output_type'] == 'error' for c in code_cells for o in c['outputs'])
for script in (ROOT / 'scripts').glob('*.py'):
    compile(script.read_text(encoding='utf-8'), str(script), 'exec')
(OUT / 'verification.json').write_text(json.dumps({
    'passed': True, 'executed_notebook_code_cells': len(code_cells),
    'verified': ['event keys and source isolation', 'ambiguous links remain unassigned',
                 'every expected OPD source-stage association preserved exactly once',
                 'all 3503 radiology waits and scan durations reconcile',
                 'radiology context joins preserve all 27343 event rows',
                 'resource snapshots have unique relative-time keys',
                 'full, projected and chunked loading agree on row count'],
    'benchmark_note': 'Measured locally, with OS filesystem cache possible. Dataframe deep memory is not total/peak process RAM. Chunk memory is the largest chunk, not total retained memory.'
}, indent=2), encoding='utf-8')
print(pd.DataFrame(results).to_string(index=False))
print('All handoff checks passed.')
