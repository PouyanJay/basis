import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from integrated_swebench import LiteBenchmark, REVISION, HARNESS, clean_env
from local_evaluation import EvaluationRunner
from credential_companion import required_key, ALLOWED


class Vault:
    def get_password(self, *args):
        return 'test-key-not-real'


class LiteTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.folder = Path(self.temp.name)
        self.root = Path(__file__).resolve().parents[1]
        self.runner = EvaluationRunner(self.folder, self.root, Vault, lambda: True, required_key, ALLOWED)
        self.lite = self.runner.lite

    def tearDown(self):
        self.temp.cleanup()

    def plan(self):
        return {'setup': {'platforms': [{'id': 'claude', 'enabled': True, 'models': ['one', 'two']}], 'tasks': []},
                'integratedBenchmarks': [{'id': 'swebench-lite', 'count': 1}]}

    def seed(self):
        source = self.folder / 'source'
        source.mkdir()
        (source / 'greeting.py').write_text('value = "before"\n')
        private = self.folder / 'instance.json'
        private.write_text(json.dumps({'patch': 'PRIVATE GOLD', 'test_patch': 'PRIVATE CHECKS'}))
        self.lite.python.parent.mkdir(parents=True)
        self.lite.python.touch()
        pack = {'name': 'SWE-bench Lite', 'revision': REVISION, 'harness': HARNESS, 'tasks': [
            {'id': 'repo__project-1', 'name': 'Fix greeting', 'acceptance': 'Return hello', 'sourcePath': str(source),
             'grader': 'swebench-lite', 'instancePath': str(private), 'imageTag': 'basis-test', 'imageDigest': 'sha256:test'}]}
        (self.lite.folder / 'selection-1.json').write_text(json.dumps(pack))
        return pack

    def test_only_prepared_lite_is_accepted(self):
        with self.assertRaisesRegex(ValueError, 'Prepare SWE-bench Lite'):
            self.runner.start(self.plan(), True)
        for suite in ['swebench-verified', 'terminalbench-2.1', 'swebench-pro']:
            plan = self.plan(); plan['integratedBenchmarks'][0]['id'] = suite
            with self.assertRaisesRegex(ValueError, 'Only SWE-bench Lite'):
                self.runner.start(plan, True)
        for count in [0, 301, True, '5']:
            with self.assertRaises(ValueError):
                self.lite.start(count)

    def test_same_tasks_separate_models_and_private_checks(self):
        self.seed()
        with patch('local_evaluation.threading.Thread'):
            job = self.runner.start(self.plan(), True)
        self.assertEqual(job['total'], 2)
        self.assertNotIn('PRIVATE', json.dumps(job))
        task = job['plan']['tasks'][0]
        self.assertEqual(task['instanceId'], 'repo__project-1')
        def agent(work, checks, args, timeout, *credentials):
            self.assertNotIn('PRIVATE', args[-1])
            self.assertFalse((work / 'instance.json').exists())
            (work / 'greeting.py').write_text('value = "after"\n')
            return 0
        with patch.object(self.runner, 'command', return_value=0), patch.object(self.runner, 'container', side_effect=agent), patch.object(self.runner, 'grade_lite', side_effect=[{'checkPassed': True}, {'checkPassed': False}]):
            self.runner.execute([('claude', model, 'ANTHROPIC_API_KEY', 'test-only') for model in ['one', 'two']])
        results = self.runner.snapshot()['results']
        self.assertEqual([r['checkPassed'] for r in results], [True, False])
        self.assertNotEqual(results[0]['folder'], results[1]['folder'])
        self.assertEqual({r['suite'] for r in results}, {'SWE-bench Lite'})

    def test_patch_is_created_outside_agent_control(self):
        work = self.folder / 'work'; work.mkdir()
        (work / 'value.py').write_text('old\n')
        self.runner.prepare_patch(work)
        (work / 'value.py').write_text('new\n')
        (work / 'added.py').write_text('added\n')
        # Agent's forged .git never controls patch generation.
        (work / '.git').mkdir(); (work / '.git/config').write_text('[core]\n hooksPath = /untrusted\n')
        self.runner.git(work, 'add', '-A', '--', '.')
        tree = (work.parent / (work.name + '-base-tree')).read_text()
        diff = self.runner.git(work, 'diff', '--cached', '--binary', '--no-ext-diff', '--no-textconv', tree, '--', '.').stdout.decode()
        self.assertIn('-old', diff); self.assertIn('+new', diff); self.assertIn('b/added.py', diff)
        self.assertNotIn('.git/config', diff)

    def test_grader_timeout_is_distinct_from_failed_checks(self):
        self.seed()
        with patch('local_evaluation.threading.Thread'):
            job = self.runner.start(self.plan(), True)
        work = self.folder / 'attempt'; work.mkdir()
        (work / 'file.py').write_text('before\n')
        self.runner.prepare_patch(work)
        (work / 'file.py').write_text('after\n')
        with patch.object(self.runner, 'command', return_value=124), patch.object(self.runner, 'remove_container'):
            with self.assertRaises(subprocess.TimeoutExpired):
                self.runner.grade_lite(job['plan']['tasks'][0], work, 30)
        self.assertIsNone(self.runner.snapshot().get('container'))

    def test_failure_is_actionable_and_restart_recovers(self):
        with patch('integrated_swebench.subprocess.run', side_effect=FileNotFoundError):
            self.lite.start(5); self.lite.worker.join(5)
        self.assertEqual(self.lite.snapshot()['status'], 'error')
        self.assertIn('Start Docker', self.lite.snapshot()['message'])
        self.lite.update(status='preparing')
        restored = LiteBenchmark(self.folder, self.root)
        self.assertEqual(restored.snapshot()['status'], 'error')
        self.assertIn('interrupted', restored.snapshot()['message'])

    def test_preparation_and_grading_do_not_inherit_credentials(self):
        with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'secret', 'GITHUB_TOKEN': 'secret', 'OTHER_PASSWORD': 'secret'}):
            env = clean_env()
        self.assertNotIn('ANTHROPIC_API_KEY', env)
        self.assertNotIn('GITHUB_TOKEN', env)
        self.assertNotIn('OTHER_PASSWORD', env)

    def test_team_tasks_cannot_request_private_grader(self):
        plan = self.plan(); plan['integratedBenchmarks'] = []
        plan['setup']['tasks'] = [{'name': 'Task', 'acceptance': 'Pass', 'grader': 'swebench-lite', 'instancePath': '/private/file'}]
        with patch('local_evaluation.threading.Thread'):
            job = self.runner.start(plan, True)
        self.assertNotIn('grader', job['plan']['tasks'][0])
        self.assertNotIn('instancePath', job['plan']['tasks'][0])


if __name__ == '__main__':
    unittest.main()
