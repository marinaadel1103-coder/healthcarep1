"""Typed loading helpers for prepared CSVs; prevents inferred numeric identifiers."""
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
TEXT_COLUMNS = '''source_system source_nature event_key case_key patient_key activity
source_natural_id source_row start_raw end_raw start_time end_time clock_basis
resource_key source_label metric_semantics appointment_id patient_id appointment_start_datetime
recorded_flow_codes source_activity case_id exam_id modality start_exam end_exam wait_before_exam
scan_time_duration total_exam_duration timestamp_start timestamp_end queue_entry_time
service_start_time service_end_time arrival_time end_time patient_type exam_types total_wait_time
total_scan_time throughput_time week_day_of_arrival total_duration scenario_id resource_id
currentSimulationLocalTime currentSimulationDay'''.split()
BOOLEAN_COLUMNS = '''duration_valid ambiguous_visit_link multiple_payload_variants
precedes_linked_appointment eligible_interval_summary wait_validated case_summary_present calendar_join_validated'''.split()
DTYPES = {**{col: 'string' for col in TEXT_COLUMNS}, **{col: 'boolean' for col in BOOLEAN_COLUMNS}}

def read_prepared(filename, usecols=None, chunksize=None, root=ROOT):
    return pd.read_csv(root / 'data/exploration' / filename, dtype=DTYPES,
                       keep_default_na=False, na_values=[''], usecols=usecols, chunksize=chunksize)
