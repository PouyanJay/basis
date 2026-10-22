"""Pinned historical HumanEval tasks adapted to Basis's isolated agent workflow."""
import gzip
import hashlib
import json
from pathlib import Path
import random
import urllib.request

REVISION = 'b9453e8f1865df0a0057a1383767caa400acfbcf'
SHA256 = 'b796127e635a67f93fb35c04f4cb03cf06f38c8072ee7cee8833d7bee06979ef'
URL = f'https://raw.githubusercontent.com/openai/human-eval/{REVISION}/data/HumanEval.jsonl.gz'


def prepare(folder, count=5):
    if type(count) is not int or not 1 <= count <= 50:
        raise ValueError('Select 1–50 HumanEval tasks.')
    folder = Path(folder) / 'benchmarks' / f'human-eval-{REVISION}'
    folder.mkdir(parents=True, exist_ok=True)
    cache = folder / 'dataset.jsonl.gz'
    if not cache.exists():
        with urllib.request.urlopen(URL, timeout=30) as response:
            data = response.read(2000000)
    else:
        data = cache.read_bytes()
    if hashlib.sha256(data).hexdigest() != SHA256:
        raise ValueError('HumanEval download failed its pinned dataset integrity check.')
    cache.write_bytes(data)
    rows = [json.loads(line) for line in gzip.decompress(data).decode().splitlines() if line]
    random.Random(0).shuffle(rows)
    tasks = []
    for row in rows[:count]:
        task_id = row['task_id'].replace('/', '-')
        source, checks = folder / task_id / 'source', folder / task_id / 'checks'
        source.mkdir(parents=True, exist_ok=True); checks.mkdir(parents=True, exist_ok=True)
        (source / 'solution.py').write_text(row['prompt'])
        # Only mounted in the separate credential-free verifier, never in the agent container.
        (checks / 'check.py').write_text("import runpy\nnamespace = runpy.run_path('/work/solution.py')\n" + row['test'] + '\ncheck(namespace[' + repr(row['entry_point']) + '])\n')
        tasks.append({'id': row['task_id'], 'name': row['task_id'], 'type': 'Features',
                      'acceptance': f"Complete {row['entry_point']} in solution.py according to its docstring. Pass the held-out original HumanEval checks.",
                      'sourcePath': str(source), 'checksPath': str(checks), 'checkCommand': 'python3 /checks/check.py'})
    manifest = {'schemaVersion': 1, 'name': 'HumanEval (Basis adapter)', 'revision': REVISION,
                'source': 'https://github.com/openai/human-eval', 'datasetDigest': SHA256, 'seed': 0, 'tasks': tasks}
    path = folder / f'pack-{count}.json'
    path.write_text(json.dumps(manifest, indent=2))
    return str(path)
