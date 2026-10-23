"""Opt-in Docker integration smoke: two simulated agents, real pinned official grading.

First prepare one Lite task in Basis. This test never reads credentials or calls a model.
Artifacts stay in a temporary directory, separate from user evaluation history.
"""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from integrated_swebench import LiteBenchmark, clean_env
from local_evaluation import EvaluationRunner
from credential_companion import required_key, ALLOWED

ROOT = Path(__file__).resolve().parents[1]
class TestVault:
    def get_password(self, *args):
        return 'integration-fixture-key-not-real'

class GradingSmoke(EvaluationRunner):
    def command(self, args, *rest, **kwargs):
        if args[:2] == ['docker', 'build']:
            return 0  # Agents are simulated; real official grading still runs.
        return super().command(args, *rest, **kwargs)

    def container(self, work, checks, args, timeout, *credentials):
        instance = json.loads((Path(self.job['folder']) / 'inputs/0/instance.json').read_text())
        if args[2] == 'correct-fixture':
            subprocess.run(['git', 'apply', '-'], input=instance['patch'].encode(), cwd=work, env=clean_env(), check=True)
        else:
            (work / 'BASIS_SMOKE.txt').write_text('No solution\n')
        return 0

folder = Path(tempfile.mkdtemp(prefix='basis-lite-integration-'))
runner = GradingSmoke(folder, ROOT, TestVault, lambda: True, required_key, ALLOWED)
runner.lite = LiteBenchmark(Path.home() / '.local/share/basis', ROOT)
plan = {'setup': {'platforms': [{'id': 'claude', 'name': 'Claude Code', 'enabled': True,
                                'models': ['correct-fixture', 'unchanged-fixture']}], 'tasks': []},
        'integratedBenchmarks': [{'id': 'swebench-lite', 'count': 1}], 'timeoutSeconds': 300}
with patch('local_evaluation.threading.Thread'):
    runner.start(plan, True)
runner.execute([('claude', model, 'ANTHROPIC_API_KEY', 'integration-fixture-key-not-real')
                for model in ['correct-fixture', 'unchanged-fixture']])
job = runner.snapshot()
assert job['status'] == 'completed', job['message']
assert [r['checkPassed'] for r in job['results']] == [True, False], [(r['status'],r['checkPassed']) for r in job['results']]
assert all(Path(r['gradingReport']).exists() for r in job['results'])
assert all(r['harness'] == 'swebench==3.0.15' for r in job['results'])
assert 'integration-fixture-key-not-real' not in (folder / 'latest-run.json').read_text()
print('PASS: real official grading through EvaluationRunner; correct patch passes, unchanged solution fails; distinct candidate evidence; no model calls.')
print('Artifacts:', folder)
