# Running and handing over Step 1

## Google Colab

1. Upload `notebooks/01_operational_data_collection_and_exploration.ipynb`.
2. Select **Runtime > Run all**. pandas and NumPy are normally preinstalled.
3. The bootstrap downloads the pinned public files when missing. It verifies hashes.
4. Open the Files panel and inspect `reports/` and `data/exploration/`.
5. Download the outputs before the runtime ends. Source data can be reacquired.

If a repository blocks a download from Colab, upload the complete handoff ZIP,
extract it and run using its supplied raw files. Do not replace sources with
unverified similarly named files.

The supplied notebook has real saved local execution results. Colab's web
interface has not been exercised in this environment.

## Load only what your task needs

From the extracted package directory:

```python
import sys
sys.path.insert(0, 'scripts')
from load_data import read_prepared

events = read_prepared(
    'events.csv.gz',
    usecols=['source_system', 'case_key', 'activity',
             'elapsed_minutes', 'eligible_interval_summary'],
)
valid = events[events['eligible_interval_summary']]
summary = valid.groupby(['source_system', 'activity'])['elapsed_minutes'].agg(['size', 'median'])
```

For validated synthetic exam waits:

```python
exams = read_prepared('radiology_exams.csv.gz')
waits = exams[exams['wait_validated']]
summary = waits.groupby('modality')['wait_before_exam_minutes'].agg(['size', 'median'])
```

For low-memory processing:

```python
for chunk in read_prepared('events.csv.gz', chunksize=50_000):
    # Aggregate per source/activity. Do not average chunk means without weighting.
    print(chunk.groupby('source_system').size())
```

The helper keeps identifiers as strings, reads flags as booleans, and interprets
only empty CSV values as missing. This avoids mixed-type warnings and prevents
literal source labels such as `None` from being silently reinterpreted.
It is supplied in the full ZIP. In a standalone Colab notebook, the prepared
`events` dataframe is already available after Run all.

## Handoff by teammate

| Teammate | Give them | Decisions they must preserve |
| --- | --- | --- |
| ETL | Raw files, source manifest, notebook, quality checks, prepared tables | Keep raw immutable, parse dates explicitly, retain error flags and event lineage |
| Snowflake | Integration contract and dictionaries | Source-specific keys and fact grains; no cross-source patient joins |
| Analytics | KPI feasibility table and exploratory summaries | Correct denominators; distinguish interval, proxy gap and validated simulated queue wait |
| Simulation | Radiology config JSONs, exams, cases and resource logs | Resolve clock mismatch, validate model reproduction, use multiple seeds and report assumptions |
| Power BI | Source-labeled prepared tables and metric definitions | Separate real-source observations from simulation; show coverage and exclusions |

## Your presentation

Explain why the earlier Synthea selection was replaced: it did not describe
operational service stages. Then explain the selected sources, their true row
grains, the measured size, one data-quality issue and its handling, and one valid
relationship. Demonstrate a radiology exam whose queue, scan start and completion
times reconcile. State that missing events do not establish abandonment.

Step 1 is complete when the team receives these artifacts and understands the
remaining KPI limitations. Confirm the instructor's submission format separately.
