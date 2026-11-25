# Source selection and reasons

Sources checked on 16 November 2026. Versions and published checksums are pinned
in `data/metadata/sources.json`; repository records are saved beside it.

## Selected

**HospitalOPD v1** — [dataset page](https://data.mendeley.com/datasets/j2hd2239dr/1),
[DOI](https://doi.org/10.17632/j2hd2239dr.1).

This source directly addresses outpatient pathways across appointment,
prescription/consultation, laboratory, imaging and pharmacy records. The inspected
file contains 62,422 wide records, 49,912 distinct appointments and 39,442 patients.
The publisher describes the data as anonymized observational records. The facility
and precise system-event semantics are not sufficiently described to treat every
timestamp as physical queue arrival or clinical service start.

Appointment records span 25 April 2024 to 7 April 2026. Other stages have different
coverage periods. Some prescription start dates fall outside the stated source
period and produce invalid intervals; these are identified in the quality report.

**Radiology workflow simulation v2** —
[dataset page](https://data.mendeley.com/datasets/jsg8c4yhxy/2),
[DOI](https://doi.org/10.17632/jsg8c4yhxy.2).

This source adds the information missing from OPD: explicit exam waiting and scan
times, case/exam/event relationships, resource capacity and available-unit logs,
and simulation parameters. It is synthetic, based on a published radiology
workflow. It covers one simulated week and provides 27,343 events, 3,503 exams,
3,193 completed case summaries and 50,375 resource snapshots. Its small duration
limits seasonal inference; its detailed structure makes it useful for validating
the project's queue/resource analysis and later what-if model.

All 3,503 exam waits are checked against matching event and scan-start timestamps.
No claim is made that the two datasets describe the same hospital or population.

## Other sources assessed

| Candidate | Assessment | Decision |
| --- | --- | --- |
| Existing Synthea sample | Clinical history and encounters; little stage queue timing | Preserve earlier work but exclude from active operational package |
| Existing small emergency simulation | Very small, ambiguous waiting labels | Preserve earlier work but replace as the active queue/resource source |
| [ED research log, Zenodo 18785676](https://zenodo.org/records/18785676) | Approximately 50 MB; source describes a synthetic reproduction with BPMN process model | Host blocked downloads with an unusual-traffic HTTP 403. Not included or profiled |
| [Auric Grid hospital operations](https://huggingface.co/datasets/AuricGrid-Laboratory/E3.H2-Synthetic_Hospital_Operations_Environment) | Advertised 1.55 million events; about 500 MB CSV; API reports manual gating | Not downloaded; requires approval from repository owner and has a larger load footprint |
| [MIMIC-IV-ED](https://physionet.org/content/mimic-iv-ed/2.2/) | Large real deidentified ED source | Credentialed access; patient-specific shifted dates also complicate cross-patient congestion. Not required for this package |

## Why this size

The selected data provide nearly 50,000 outpatient visits without a large loading
burden: about 16 MiB of complete raw downloads, including documentation and the
source process diagram. The 151,319-record prepared event view results from
extracting documented source stages and retaining variants; it does not create
extra independent patients or observations.

The earlier package had many clinical-observation rows. Its raw row total was
not a good measure of support for operational analysis. Source relevance, unique
journeys, time coverage, linkage quality and usable denominators matter more than
adding unrelated records. No source is duplicated, sampled up or joined by an
invented patient identity.

## Attribution and reuse

Both selected sources are CC BY 4.0. Cite their authors, DOI and version, link the
license, and state that the exploratory exports reshape and flag the original
data. See the package README for attribution. The unchanged original files and
published source hashes are retained for reproducibility.
