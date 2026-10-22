"""Opt-in real Docker boundary test. No provider calls or production records."""
import gzip
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from credential_companion import ALLOWED, ROOT, required_key
from local_evaluation import EvaluationRunner, benchmark_pack
from humaneval_pack import prepare, REVISION

class Store:
    def get_password(self, *args): return 'isolated-test-key-not-valid'

with tempfile.TemporaryDirectory(prefix='basis-container-test-') as directory:
    base=Path(directory)
    # Install a deterministic executable in a separate test image. Never replace the production image.
    (base/'codex').write_text('''#!/usr/bin/env python3
import os
from pathlib import Path
assert os.environ.get('OPENAI_API_KEY') == 'isolated-test-key-not-valid'
assert not Path('/checks').exists()
Path('/work/solution.py').write_text('def greeting(): return "hello"\\n')
''')
    (base/'codex').chmod(0o755)
    (base/'Dockerfile').write_text('FROM basis-local-runner:v2\nUSER root\nRUN rm /usr/local/bin/codex\nCOPY codex /usr/local/bin/codex\nUSER node\n')
    subprocess.run(['docker','build','-q','-t','basis-evaluation-test:local',str(base)],check=True,stdout=subprocess.DEVNULL)
    checks=base/'checks';checks.mkdir()
    (checks/'check.py').write_text('''import os, runpy
from pathlib import Path
assert not os.environ.get('OPENAI_API_KEY')
assert runpy.run_path('/work/solution.py')['greeting']() == 'hello'
try:
    Path('/checks/forbidden').write_text('must fail')
except OSError:
    pass
else:
    raise AssertionError('checks must be read-only')
''')
    runner=EvaluationRunner(base/'state',ROOT,Store,lambda:True,required_key,ALLOWED)
    runner.image='basis-evaluation-test:local'
    plan={'setup':{'meta':{'name':'Container test only'},'platforms':[{'id':'codex','name':'Codex','enabled':True,'model':''}],
                   'tasks':[{'name':'Greeting','acceptance':'Return hello','checksPath':str(checks),'checkCommand':'python3 /checks/check.py'}],
                   'gates':[], 'gateResults':{}},'timeoutSeconds':30}
    with patch('local_evaluation.threading.Thread'):
        runner.start(plan,True)
    original_command=runner.command
    def command(args,*a,**kw):
        return 0 if args[:2]==['docker','build'] else original_command(args,*a,**kw)
    runner.command=command
    runner.execute([('codex','','OPENAI_API_KEY','isolated-test-key-not-valid')])
    job=runner.snapshot()
    assert job['status']=='completed',job
    assert job['results'][0]['checkPassed'] is True,job
    assert 'isolated-test-key-not-valid' not in (base/'state/latest-run.json').read_text()
    # Real pinned dataset, real original checks, known canonical solutions; not agent performance evidence.
    manifest=prepare(base/'state',5)
    pack=benchmark_pack(manifest)
    rows={r['task_id']:r for r in (json.loads(x) for x in gzip.decompress((base/'state/benchmarks'/f'human-eval-{REVISION}'/'dataset.jsonl.gz').read_bytes()).decode().splitlines())}
    for task in pack['tasks']:
        work=base/task['id'].replace('/','-');work.mkdir()
        row=rows[task['id']]
        (work/'solution.py').write_text(row['prompt']+row['canonical_solution'])
        assert runner.container(work,Path(task['checksPath']),['check',task['checkCommand']],30)==0,task['id']
    # A wrong solution must fail rather than produce a successful benchmark record.
    (work/'solution.py').write_text('raise RuntimeError("intentionally invalid")')
    assert runner.container(work,Path(task['checksPath']),['check',task['checkCommand']],30)!=0
print('PASS real Docker: generated workspace, hidden/read-only checks, credential-free verification; five original HumanEval cases pass canonical solutions and reject an invalid solution. No provider calls.')
