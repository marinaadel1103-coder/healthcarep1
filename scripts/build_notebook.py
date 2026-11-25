"""Create a self-contained notebook and execute its cells with real captured outputs."""
from pathlib import Path
from contextlib import redirect_stdout, redirect_stderr
import io
import json
import os

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
cells = []

def markdown(text):
    cells.append({'cell_type': 'markdown', 'metadata': {}, 'source': text.splitlines(keepends=True)})

def code(text):
    cells.append({'cell_type': 'code', 'metadata': {}, 'source': text.splitlines(keepends=True), 'execution_count': None, 'outputs': []})

markdown('''# Healthcare Friction Observatory
## Revised Step 1: Collection, exploration and data-quality handoff

**Sources:** [HospitalOPD v1](https://data.mendeley.com/datasets/j2hd2239dr/1), described by its publisher as anonymized outpatient records;
and [radiology workflow simulation v2](https://data.mendeley.com/datasets/jsg8c4yhxy/2), explicitly synthetic.
Both are published under CC BY 4.0. They are different populations and must remain distinguishable.

**Scale:** Full downloaded sources are used. No rows were duplicated or new patients simulated to increase size.
The notebook computes the actual counts, load sizes and quality results.

**Colab:** Upload this notebook, choose **Runtime > Run all**, and allow the first cell to download about 16 MiB of pinned sources if missing.
Outputs appear in `reports/` and `data/exploration/` in the Files panel. Download them before the session ends.
Alternatively, extract the full handoff ZIP and run locally from its folder. pandas and NumPy are the only analytical dependencies.

The saved outputs were produced by executing these Python cells locally in a shared namespace.
The Google Colab interface itself has not been used to validate this notebook.

**Question:** Which journey and resource measures are supported, and what must be resolved before the team reports them?
''')
manifest = json.loads((ROOT / 'data/metadata/sources.json').read_text(encoding='utf-8'))
download_source = (ROOT / 'scripts/download.py').read_text(encoding='utf-8')
download_source = download_source.replace('ROOT = Path(__file__).resolve().parents[1]', 'ROOT = Path.cwd()')
download_source = download_source.replace("if __name__ == '__main__':\n    download()", 'download()')
bootstrap = '''from pathlib import Path
import os, json
if Path.cwd().name == 'notebooks':
    os.chdir(Path.cwd().parent)
if (Path.cwd() / 'step1_v2/data/metadata/sources.json').exists():
    os.chdir(Path.cwd() / 'step1_v2')
Path('data/metadata').mkdir(parents=True, exist_ok=True)
'''
bootstrap += 'pinned_sources = ' + repr(manifest) + '\n'
bootstrap += "Path('data/metadata/sources.json').write_text(json.dumps(pinned_sources, indent=2), encoding='utf-8')\n"
code(bootstrap + download_source)
explanations = {
 'Setup and provenance': 'Verify the source hashes before analysis. Source files are never edited. Each rule records its denominator and flagged count.',
 'Raw inventory, field types and missingness': 'Load source IDs as strings. Explicit date parsers prevent malformed values from being silently accepted. Optional absent services are different from invalid supplied timestamps.',
 'OPD checks and safe stage extraction': 'One wide OPD row is not one patient or one visit. Extract unique service payloads and preserve every source association. Conflicting IDs remain flagged and are excluded from default duration summaries.',
 'Radiology relationships and duration consistency': 'Validate case and exam joins without changing event counts. Reconstruct wait from the enclosing event start to scan start, and check scan duration independently. Cases missing from completed summaries remain visible.',
 'Resource snapshots and safe integration': 'Resource observations are at resource/time grain. Keep their relative Monday-origin clock separate because their weekdays disagree with the event calendar. UNION the event schemas with source labels; do not match patients across sources.',
 'Exploratory summaries and exports': 'Report denominators. OPD intervals are source-record durations, not verified queue waits. Radiology waits are simulation outputs validated against timestamps. Save portable gzip CSVs for pandas, S3 and later ETL.',
 'Reports and measured footprint': 'Generate the dictionary, quality report, inventory and technical evidence. These are a Step 1 handoff; unresolved limitations remain explicit rather than being filled with invented data.'}
for part in (ROOT / 'scripts/explore.py').read_text(encoding='utf-8').split('# %% ')[1:]:
    title, body = part.split('\n', 1)
    markdown('## ' + title + '\n\n' + explanations[title])
    code(body)
markdown('''## Handoff checklist

- Read `reports/data_quality_report.md`, particularly the KPI feasibility table.
- Use `reports/data_dictionary.csv` and `docs/integration_contract.md` for types, keys and grains.
- Keep `source_system` and `source_nature` in every combined analysis.
- Preserve `opd_event_lineage.csv.gz` when implementing ETL.
- Do not classify absent services or missing case summaries as abandonment.
- Build what-if simulations only with documented capacity, arrival/service distributions and multiple replications.
- Use `docs/colab_and_handoff.md` to load one prepared file or selected columns at a time.
''')
namespace = {'__name__': '__notebook__'}
execution = 0
for i, cell in enumerate(cells):
    cell['id'] = f'cell-{i:02d}'
    if cell['cell_type'] != 'code': continue
    execution += 1
    stdout, stderr = io.StringIO(), io.StringIO()
    cell['execution_count'] = execution
    try:
        with redirect_stdout(stdout), redirect_stderr(stderr):
            exec(compile(''.join(cell['source']), f'notebook-cell-{execution}', 'exec'), namespace)
    except Exception:
        print(stdout.getvalue(), stderr.getvalue())
        raise
    for name, stream in [('stdout', stdout), ('stderr', stderr)]:
        if stream.getvalue():
            cell['outputs'].append({'output_type': 'stream', 'name': name, 'text': stream.getvalue().splitlines(keepends=True)})
    print(f'Executed cell {execution}', flush=True)
notebook = {'nbformat': 4, 'nbformat_minor': 5,
            'metadata': {'kernelspec': {'display_name': 'Python 3', 'name': 'python3', 'language': 'python'},
                         'language_info': {'name': 'python', 'version': namespace['sys'].version.split()[0]},
                         'execution_note': 'Cells executed in a shared local Python namespace. Real stdout/stderr saved. Colab UI not tested.'},
            'cells': cells}
path = ROOT / 'notebooks/01_operational_data_collection_and_exploration.ipynb'
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(json.dumps(notebook, indent=1, ensure_ascii=False), encoding='utf-8')
print('Saved notebook with', execution, 'executed code cells.')
