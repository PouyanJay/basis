import json
import pathlib
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'scripts'))
from local_evaluation import EvaluationRunner, copy_source, benchmark_pack
from credential_companion import required_key, ALLOWED

class Vault:
    def get_password(self, service, name): return 'test-secret-never-real'

class EvaluationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = pathlib.Path(self.temp.name)
        self.runner = EvaluationRunner(self.base/'state', self.base, Vault, lambda:True, required_key, ALLOWED)
        self.plan = {'setup':{'meta':{'name':'Original'},'platforms':[{'id':'codex','name':'Codex','model':'test-model','enabled':True}],
                             'tasks':[{'id':'T1','name':'Implement greeting','acceptance':'Return hello'}],
                             'org':{'privacy':'Public source only'},'gates':[{'id':'retention','name':'Retention','required':True}], 'gateResults':{}},'timeoutSeconds':30}
    def tearDown(self): self.temp.cleanup()
    def start_paused(self, plan=None):
        with patch('local_evaluation.threading.Thread'):
            return self.runner.start(plan or self.plan, True)
    def test_artifact_access_is_scoped_to_saved_outputs(self):
        import base64
        run_id = 'a' * 32
        directory = self.runner.folder / 'evaluations' / run_id
        work = directory / 'attempts' / '0' / 'claude-test'
        work.mkdir(parents=True)
        (directory / 'result.json').write_text(json.dumps({'results':[{'taskIndex':0,'agent':'claude','candidateId':'claude-test'}]}))
        (directory / 'plan.json').write_text('{}')
        (work / 'solution.py').write_text('print("hello")')
        (work / '.env').write_text('PRIVATE')
        (work / 'escape').symlink_to(self.base)
        (work / 'linked.py').symlink_to(work / 'solution.py')
        grading = work.parent / 'claude-test-grading'
        grading.mkdir()
        (grading / 'config.json').write_text('PRIVATE GOLD')
        (grading / 'report.json').write_text('{}')
        key = '0:claude-test'
        names = [f['name'] for f in self.runner.artifacts(run_id,key)['files']]
        self.assertEqual(names, ['workspace/solution.py','grading/report.json'])
        artifact = self.runner.artifact(run_id,'workspace/solution.py',key)
        self.assertEqual(base64.b64decode(artifact['base64']).decode(), artifact['text'])
        for name in ('../result.json','workspace/.env','grading/config.json','workspace/linked.py'):
            with self.assertRaises(ValueError): self.runner.artifact(run_id,name,key)
        with self.assertRaises(ValueError): self.runner.artifacts('../outside')
        with self.assertRaises(ValueError): self.runner.artifacts(run_id,'0:other')
        (work / 'large.txt').write_bytes(b'x' * (5*1024*1024+1))
        with self.assertRaises(ValueError): self.runner.artifact(run_id,'workspace/large.txt',key)
        (work / 'binary.bin').write_bytes(b'\x00\xff')
        self.assertIsNone(self.runner.artifact(run_id,'workspace/binary.bin',key)['text'])

    def test_output_stream_redacts_split_secret_and_bounds_history(self):
        self.start_paused()
        self.runner._secrets = ['secret-example-123']
        code = "import os,time;os.write(1,b'secret-example-');time.sleep(.05);os.write(1,b'123\\nhello\\n');time.sleep(.3)"
        worker = threading.Thread(target=lambda:self.runner.command([sys.executable, '-c', code], 3))
        worker.start()
        import time
        deadline = time.time()+2
        while not self.runner.snapshot().get('activity') and time.time()<deadline:
            time.sleep(.01)
        self.assertTrue(worker.is_alive(), 'Output must arrive before process exit')
        worker.join()
        output = json.dumps(self.runner.snapshot()['activity'])
        self.assertIn('[REDACTED]', output)
        self.assertNotIn('secret-example', output)
        self.assertNotIn('secret-example', self.runner.file.read_text())
        for i in range(400): self.runner.output(str(i))
        self.assertEqual(len(self.runner.snapshot()['activity']),300)
        self.assertTrue(self.runner.snapshot()['activityTruncated'])

    def test_claude_output_excludes_private_and_initialization_payloads(self):
        self.start_paused()
        self.runner._stream='claude'
        self.runner.update(phase='agent')
        self.runner.output(json.dumps({'type':'assistant','message':{'content':[{'type':'thinking','thinking':'PRIVATE'},{'type':'tool_use','name':'Read','input':{'secret':'PRIVATE'}},{'type':'text','text':'Public update'}]}}))
        self.runner.output(json.dumps({'type':'system','subtype':'init','environment':'PRIVATE'}))
        output=json.dumps(self.runner.snapshot()['activity'])
        self.assertNotIn('PRIVATE',output)
        self.assertIn('Tool: Read',output)
        self.assertIn('Public update',output)

    def test_multiple_models_are_isolated_and_reviewed_independently(self):
        self.plan['setup']['platforms'][0]['models']=['model-a','model-b']
        job=self.start_paused()
        self.assertEqual(job['total'],2)
        candidates=job['plan']['services']
        self.assertEqual(len({p['candidateId'] for p in candidates}),2)
        def container(work, checks, args, timeout, *credentials):
            (work/'solution.txt').write_text(args[2])
            return 0 if args[2]=='model-a' else 1
        with patch.object(self.runner,'command',return_value=0),patch.object(self.runner,'container',side_effect=container):
            self.runner.execute([('codex',m,'OPENAI_API_KEY','test-secret') for m in ['model-a','model-b']])
        job=self.runner.snapshot()
        first,second=job['results']
        self.assertNotEqual(first['folder'],second['folder'])
        self.assertEqual(pathlib.Path(first['folder'],'solution.txt').read_text(),'model-a')
        self.assertEqual(pathlib.Path(second['folder'],'solution.txt').read_text(),'model-b')
        self.assertEqual(first['status'],'completed')
        self.assertEqual(second['status'],'error')
        self.assertEqual({e['stream'] for e in job['activity']},{p['candidateId'] for p in candidates})
        key=f"0:{first['candidateId']}"
        self.runner.review(job['id'],key,{'accepted':True,'notes':'Reviewed model A'})
        self.assertNotIn(f"0:{second['candidateId']}",self.runner.snapshot()['reviews'])
        with self.assertRaises(ValueError):
            self.runner.review(job['id'],'0:codex',{'accepted':True,'notes':'Ambiguous'})
        restored=EvaluationRunner(self.base/'state',self.base,Vault,lambda:True,required_key,ALLOWED)
        self.assertEqual(len(restored.snapshot()['plan']['services']),2)
        self.assertTrue(restored.snapshot()['reviews'][key]['accepted'])

    def test_invalid_model_selections_are_rejected(self):
        for models in [[],['model-a','model-a'],['model-a',1],[''],['../bad model'],[str(n) for n in range(11)],'model-a']:
            self.plan['setup']['platforms'][0]['models']=models
            with self.subTest(models=models),self.assertRaises(ValueError):
                self.start_paused()

    def test_snapshot_history_and_reviews(self):
        job=self.start_paused()
        self.plan['setup']['tasks'][0]['name']='Changed later'
        commands=[]
        def container(*args):
            commands.append(args)
            (args[0]/'solution.py').write_text("print('hello')")
            return 0
        with patch.object(self.runner,'command',return_value=0),patch.object(self.runner,'container',side_effect=container):
            self.runner.execute([('codex','test-model','OPENAI_API_KEY','test-secret-never-real')])
        job=self.runner.snapshot()
        self.assertEqual(job['status'],'completed')
        self.assertEqual(job['plan']['tasks'][0]['name'],'Implement greeting')
        self.assertIsNone(job['results'][0]['checkPassed'])
        self.assertIsNone(job['results'][0]['accepted'])
        self.assertEqual(job['plan']['setup']['gateResults'],{})
        self.assertEqual(len(self.runner.history()),1)
        self.runner.review(job['id'],'0:codex',{'accepted':True,'notes':'Inspected source','humanMinutes':2,'usageCost':None})
        restored=EvaluationRunner(self.base/'state',self.base,Vault,lambda:True,required_key,ALLOWED)
        self.assertTrue(restored.snapshot()['reviews']['0:codex']['accepted'])
        self.assertIsNone(restored.snapshot()['results'][0]['accepted'])
        self.assertNotIn('test-secret-never-real',self.runner.file.read_text())
        self.assertTrue((pathlib.Path(job['results'][0]['folder'])/'solution.py').exists())
    def test_source_is_copied_and_checks_immutable(self):
        source=self.base/'source';source.mkdir();(source/'input.py').write_text('BASE=1')
        (source/'.env').write_text('NEVER_COPY=secret')
        checks=self.base/'checks';checks.mkdir();(checks/'test.py').write_text('assert True')
        self.plan['setup']['tasks'][0].update(sourcePath=str(source),checksPath=str(checks),checkCommand='python3 /checks/test.py')
        job=self.start_paused();(source/'input.py').write_text('BASE=2')
        copied=pathlib.Path(job['folder'])/'inputs/0/source'
        self.assertEqual((copied/'input.py').read_text(),'BASE=1');self.assertFalse((copied/'.env').exists())
        calls=[]
        with patch.object(self.runner,'command',side_effect=lambda args,*a,**kw:calls.append((args,a,kw)) or 0),patch.object(self.runner,'remove_container'):
            self.runner.container(copied,checks,['agent','codex','','prompt'],30,'OPENAI_API_KEY','test-secret-never-real')
            self.runner.container(copied,checks,['check','python3 /checks/test.py'],30)
        agent,verifier=calls
        self.assertIn('--read-only',agent[0]);self.assertNotIn('test-secret-never-real',' '.join(agent[0]))
        self.assertNotIn('target=/checks', ' '.join(agent[0]))
        self.assertIn('target=/checks,readonly',' '.join(verifier[0]));self.assertIn('--network=none',verifier[0])
        self.assertNotIn('OPENAI_API_KEY',verifier[1][1])
    def test_partial_run_keeps_failed_attempt(self):
        self.start_paused()
        with patch.object(self.runner,'command',return_value=0),patch.object(self.runner,'container',side_effect=subprocess.TimeoutExpired('docker',30)):
            self.runner.execute([('codex','','OPENAI_API_KEY','test-secret')])
        self.assertEqual(self.runner.snapshot()['status'],'partial')
        self.assertEqual(self.runner.snapshot()['results'][0]['status'],'timeout')
    def test_cancel_preserves_evidence_and_skips_remaining(self):
        self.plan['setup']['tasks'].append({'id':'T2','name':'Second','acceptance':'Works'})
        self.start_paused()
        def cancel(*args):
            self.runner.stop()
            raise InterruptedError()
        with patch.object(self.runner,'command',return_value=0),patch.object(self.runner,'container',side_effect=cancel):
            self.runner.execute([('codex','','OPENAI_API_KEY','test-secret')])
        self.assertEqual(self.runner.snapshot()['status'],'stopped')
        self.assertEqual(len(self.runner.snapshot()['results']),1)
    def test_validation_and_benchmark_pack(self):
        checks=self.base/'checks';checks.mkdir();(checks/'check.py').write_text('assert True')
        pack=self.base/'pack.json';pack.write_text(json.dumps({'schemaVersion':1,'name':'External','revision':'v1','tasks':[{'name':'Case','acceptance':'Works','checksPath':'checks','checkCommand':'python3 /checks/check.py'}]}))
        self.assertEqual(benchmark_pack(str(pack))['tasks'][0]['checksPath'],str(checks.resolve()))
        self.plan['benchmarkPaths']=[str(pack)]
        job=self.start_paused()
        self.assertEqual(job['total'],2);self.assertEqual(job['plan']['tasks'][1]['sourceKind'],'benchmark')
        self.assertEqual(len(job['plan']['benchmarks'][0]['manifestDigest']),64)
        with self.assertRaises(ValueError):self.runner.start(self.plan,True)
        with self.assertRaises(ValueError):self.runner.review('../../outside','0:codex',{})
    def test_restart_marks_unfinished_interrupted(self):
        self.start_paused()
        restored=EvaluationRunner(self.base/'state',self.base,Vault,lambda:True,required_key,ALLOWED)
        self.assertEqual(restored.history()[0]['status'],'interrupted')
    def test_symlinks_rejected(self):
        source=self.base/'source';source.mkdir();(source/'secret').symlink_to('/etc/passwd')
        with self.assertRaises(ValueError):copy_source(str(source),self.base/'copy')

if __name__=='__main__':unittest.main()
