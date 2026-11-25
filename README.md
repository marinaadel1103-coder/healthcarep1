# Healthcare Friction Observatory — revised Step 1

This is the active data collection and exploration package. It replaces the earlier
Synthea/small-emergency selection for the operational project. The earlier files
remain in the parent folder for reference and are not loaded here.

## What to open

1. `reports/data_quality_report.md`: actual findings and which project questions are supported.
2. `notebooks/01_operational_data_collection_and_exploration.ipynb`: executed, self-contained notebook.
3. `reports/data_dictionary.md`: source field definitions, types and units.
4. `docs/integration_contract.md`: safe keys, grains, flags and join rules.
5. `docs/colab_and_handoff.md`: loading instructions and team handoff.

## The selected data

| Source | Scale | Contribution |
| --- | --- | --- |
| HospitalOPD v1 | 62,422 source rows, 39,442 patients, 49,912 appointments | Recorded outpatient journey/service intervals |
| Radiology simulation v2 | 27,343 events, 3,503 exams, 3,193 completed case summaries | Explicit exam wait and scan times |
| Radiology resource logs | 50,375 snapshots across 25 resources | Capacity, available units and queue observations |

There are 3,254 radiology case IDs in the event log; 61 lack a completed-case summary.
The prepared common view has 151,319 source record variants, not 151,319 patients.
These counts come from the files, not only the repository descriptions.

The complete downloads are about 16 MiB and compressed exploratory outputs about
10 MiB. No sampling or artificial row duplication was needed. See `reports/run_summary.json`
and `reports/loading_benchmark.csv` for measured runtime and memory details.

## Run

From this directory:

```powershell
python -m pip install -r requirements.txt
python scripts/download.py
python scripts/explore.py
```

The downloader verifies pinned public-source hashes and skips valid local files.
The notebook includes this bootstrap, so it also works as a standalone Colab upload.
Its cells were executed locally with captured outputs; the Colab UI was not tested.
Full source files are included in the complete handoff ZIP, so downloading is
unnecessary after extracting it unless a file is missing or changed.

## Integration and interpretation

- Sources are combined as a labeled UNION. They do not describe the same patients or hospital.
- OPD stage payloads are extracted with original-row lineage. Repeated source associations
  are not multiplied into independent services. Ambiguous visit links remain null and flagged.
- Radiology cases and exams are joined only within that source, with row-preserving cardinality checks.
- Resources remain at snapshot grain. Their calendar mismatch prevents an unverified event-time join.
- Explicit radiology exam waiting is verified against linked timestamps. OPD appointment/prescription
  gaps remain proxies, not verified door-to-doctor waits.
- There is no validated abandonment outcome in these sources. Missing events are not dropout labels.
- No cloud deployment, production ETL, warehouse, staffing simulation or final dashboard was built.

## Files

`data/raw/` holds unchanged source downloads and source documentation.
`data/metadata/sources.json` pins URLs, versions through dataset records, sizes and published hashes.
`data/exploration/` holds compact preliminary tables with flags and lineage.
`reports/` holds profiles, checks, dictionaries and source-specific exploratory summaries.
`docs/` explains source selection and how the team should use the outputs.

## Attribution

HospitalOPD: batool, komal; Mehmood, Arshad; Zafar, Saad (2026).
[HospitalOPD, v1](https://doi.org/10.17632/j2hd2239dr.1).

Radiology: Serrano Pérez, Fernando; Ilarri Artigas, Sergio (2025).
[Radiology Workflow Simulation Dataset, v2](https://doi.org/10.17632/jsg8c4yhxy.2).

Both sources: [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
Raw source bytes are unchanged. Prepared exports reshape, deduplicate identical
payloads, parse types, calculate durations, attach provenance and flag issues as
documented. The authors have not endorsed this project.
