"""Package the complete reproducible Step 1 handoff, including licensed raw data."""
from pathlib import Path
import json
import zipfile

ROOT = Path(__file__).resolve().parents[1]
verification = json.loads((ROOT / 'reports/verification.json').read_text(encoding='utf-8'))
assert verification['passed']
target = ROOT.parent / 'Healthcare_Friction_Step1_v2_Full.zip'
included = []
with zipfile.ZipFile(target, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as z:
    for path in sorted(ROOT.rglob('*')):
        if not path.is_file() or '__pycache__' in path.parts or path.suffix == '.part':
            continue
        # Do not present rejected candidate metadata as an included data source.
        if path.name == 'ed_record.json':
            continue
        z.write(path, 'step1_v2/' + path.relative_to(ROOT).as_posix())
        included.append(path.relative_to(ROOT).as_posix())
with zipfile.ZipFile(target) as z:
    assert z.testzip() is None
    assert 'step1_v2/data/raw/opd/HospitalOPD-noname.csv' in z.namelist()
    assert 'step1_v2/notebooks/01_operational_data_collection_and_exploration.ipynb' in z.namelist()
print('Package:', target)
print('Files:', len(included), '| MiB:', round(target.stat().st_size / 2**20, 2))
