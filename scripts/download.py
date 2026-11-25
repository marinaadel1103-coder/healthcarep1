"""Reproduce the pinned, public source downloads. No credentials are needed."""
from pathlib import Path
import hashlib
import json
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]

def digest(path, algorithm='sha256'):
    h = hashlib.new(algorithm)
    with path.open('rb') as f:
        while chunk := f.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest()

def download(root=ROOT):
    specs = json.loads((root / 'data/metadata/sources.json').read_text(encoding='utf-8'))
    for spec in specs:
        target = (root / spec['path']).resolve()
        if not target.is_relative_to(root.resolve()):
            raise ValueError('Invalid manifest path')
        if target.exists() and digest(target, spec['algorithm']) == spec['checksum']:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        for attempt in range(3):
            try:
                request = urllib.request.Request(spec['url'], headers={'User-Agent': 'Mozilla/5.0'})
                temp = target.with_suffix(target.suffix + '.part')
                with urllib.request.urlopen(request, timeout=120) as response, temp.open('wb') as out:
                    while chunk := response.read(1024 * 1024):
                        out.write(chunk)
                if digest(temp, spec['algorithm']) != spec['checksum']:
                    raise ValueError('Published checksum mismatch: ' + spec['original_filename'])
                temp.replace(target)
                break
            except Exception:
                if attempt == 2:
                    raise
                time.sleep(2)
        print('Downloaded', target.relative_to(root))
    print('All pinned source files are present and verified.')

if __name__ == '__main__':
    download()
