import copy
import json
import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'scripts'))
from local_evaluation import EvaluationRunner
from run_workspaces import RunWorkspaces
from credential_companion import required_key, ALLOWED
class Vault:
 def get_password(self,*args):return 'test-key'
class WorkspaceTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.root=pathlib.Path(self.temp.name)
  self.runner=EvaluationRunner(self.root/'state',self.root,Vault,lambda:True,required_key,ALLOWED);self.manager=RunWorkspaces(self.runner)
  self.source=self.root/'source';self.source.mkdir();(self.source/'main.py').write_text('original = True')
  self.setup={'meta':{'name':'Original'},'platforms':[{'id':'codex','name':'Codex','enabled':True,'models':['test-model']}],'tasks':[{'id':'T1','name':'Task','acceptance':'Pass checks','sourcePath':str(self.source)}],'execution':{'timeoutSeconds':30,'platformReview':False}}
 def tearDown(self):self.temp.cleanup()
 def start(self,w):
  with patch('local_evaluation.threading.Thread'):j=self.manager.start(w['id'],w['revision'],True)
  self.runner.worker=None
  return j
 def finish(self):self.runner.update(status='completed',finishedAt=123)
 def test_drafts_persist_revision_conflicts_and_credentials(self):
  setup=copy.deepcopy(self.setup);setup['platforms'][0]['apiKey']='secret';w=self.manager.create(setup)
  self.assertNotIn('secret',json.dumps(self.manager.get(w['id'])))
  updated=copy.deepcopy(w['setup']);updated['meta']['name']='Edited';saved=self.manager.save(w['id'],updated,w['revision'])
  self.assertEqual(RunWorkspaces(self.runner).get(w['id'])['name'],'Edited')
  with self.assertRaises(ValueError):self.manager.save(w['id'],self.setup,w['revision'])
  self.assertEqual(saved['revision'],2)
 def test_two_executions_clone_frozen_inputs_and_independent_outputs(self):
  w=self.manager.create(self.setup);first=self.start(w);self.finish()
  old=(self.manager.directory(w['id'])/'result.json').read_bytes()
  (self.source/'main.py').write_text('changed = True')
  clone=self.manager.clone(w['id']);self.assertEqual(clone['parentId'],w['id']);self.assertEqual(clone['status'],'draft')
  self.assertFalse((self.manager.directory(clone['id'])/'result.json').exists())
  second=self.start(clone);self.finish()
  self.assertNotEqual(first['id'],second['id'])
  self.assertEqual((self.manager.directory(second['id'])/'inputs/0/source/main.py').read_text(),'original = True')
  self.assertEqual((self.manager.directory(first['id'])/'result.json').read_bytes(),old)
  self.assertEqual(len(self.manager.listing()),2)
  self.assertEqual(len(self.runner.history()),2)
  with self.assertRaises(ValueError):self.manager.start(first['id'],1,True)
  with self.assertRaises(ValueError):self.manager.save(first['id'],self.setup,1)
 def test_explicit_new_source_and_clone_of_draft(self):
  w=self.manager.create(self.setup);self.start(w);self.finish();child=self.manager.clone(w['id']);grandchild=self.manager.clone(child['id'])
  other=self.root/'other';other.mkdir();(other/'main.py').write_text('replacement')
  setup=grandchild['setup'];setup['tasks'][0]['sourcePath']=str(other);grandchild=self.manager.save(grandchild['id'],setup,grandchild['revision'])
  j=self.start(grandchild);self.finish();self.assertEqual((self.manager.directory(j['id'])/'inputs/0/source/main.py').read_text(),'replacement')
 def test_failure_keeps_draft_and_concurrency_does_not_overwrite(self):
  w=self.manager.create(self.setup)
  with self.assertRaises(ValueError):self.manager.start(w['id'],w['revision'],False)
  self.assertEqual(self.manager.get(w['id'])['status'],'draft')
  self.start(w);other=self.manager.create(self.setup)
  with self.assertRaises(ValueError):self.start(other)
  self.assertEqual(self.manager.get(other['id'])['status'],'draft')
  self.finish()
  bad=other['setup'];bad['tasks'][0]['sourcePath']='/does-not-exist';other=self.manager.save(other['id'],bad,other['revision'])
  with self.assertRaises(ValueError):self.start(other)
  self.assertTrue((self.manager.directory(other['id'])/'workspace.json').exists())
  self.assertFalse((self.manager.directory(other['id'])/'inputs').exists())
 def test_legacy_runs_list_and_restart_preserves_drafts(self):
  with patch('local_evaluation.threading.Thread'):job=self.runner.start({'setup':self.setup,'timeoutSeconds':30},True)
  self.runner.worker=None;self.finish();self.assertEqual(self.manager.get(job['id'])['name'],'Original')
  draft=self.manager.create(self.setup)
  reopened=EvaluationRunner(self.runner.folder,self.root,Vault,lambda:True,required_key,ALLOWED)
  self.assertEqual(len(RunWorkspaces(reopened).listing()),2);self.assertEqual(RunWorkspaces(reopened).get(draft['id'])['status'],'draft')
 def test_benchmark_clone_pins_selection(self):
  task={'id':'repo__1','name':'Fix issue','acceptance':'Tests pass','sourcePath':str(self.source),'grader':'swebench-lite','instancePath':str(self.root/'instance.json'),'imageTag':'pinned','imageDigest':'pinned-digest'}
  (self.root/'instance.json').write_text('{}');self.runner.lite.selection=lambda count:{'name':'SWE-bench Lite','revision':'pinned','harness':'3.0','tasks':[task]}
  self.setup['execution']['integratedBenchmarks']=[{'id':'swebench-lite','count':1}];w=self.manager.create(self.setup);self.start(w);self.finish();child=self.manager.clone(w['id'])
  self.runner.lite.selection=lambda count:(_ for _ in ()).throw(AssertionError('Must use saved selection'))
  j=self.start(child);self.finish();self.assertEqual(j['plan']['tasks'][1]['instanceId'],'repo__1')
 def test_ids_and_symlinks_rejected(self):
  with self.assertRaises(ValueError):self.manager.get('../secret')
  w=self.manager.create(self.setup);p=self.manager.directory(w['id']);(p/'workspace.json').unlink();(p/'workspace.json').symlink_to(self.source/'main.py')
  with self.assertRaises(ValueError):self.manager.get(w['id'])

 def test_benchmark_preparation_owned_by_draft(self):
  first=self.manager.create(self.setup);second=self.manager.create(self.setup)
  with patch('integrated_swebench.threading.Thread'):
   state=self.runner.lite.start(2,workspace_id=first['id'])
   self.assertEqual(state['workspaceId'],first['id'])
   with self.assertRaisesRegex(ValueError,'another run'):self.runner.lite.start(2,workspace_id=second['id'])
   self.assertEqual(self.runner.lite.snapshot()['workspaceId'],first['id'])
 def test_delete_removes_all_run_files_and_latest_copy_preserves_clone(self):
  w=self.manager.create(self.setup);self.start(w);self.finish();child=self.manager.clone(w['id'])
  folder=self.manager.directory(w['id'])
  for name in ['recommendations.json','platform-review.json','judge-evidence-snapshot.json','attempts/0/artifacts/code.py']:
   p=folder/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('{}')
  (folder/'external-link').symlink_to(self.source,target_is_directory=True)
  self.manager.delete(w['id'])
  self.assertFalse(folder.exists());self.assertFalse(self.runner.file.exists());self.assertIsNone(self.runner.job)
  self.assertTrue((self.source/'main.py').exists())
  self.assertEqual(self.manager.get(child['id'])['status'],'draft')
  self.start(child);self.finish()
  self.assertEqual((self.manager.directory(child['id'])/'inputs/0/source/main.py').read_text(),'original = True')
  with self.assertRaises(ValueError):self.manager.get(w['id'])
 def test_delete_draft_and_nonlatest_preserves_latest(self):
  old=self.manager.create(self.setup);self.start(old);self.finish()
  latest=self.manager.create(self.setup);self.start(latest);self.finish();data=self.runner.file.read_bytes()
  self.manager.delete(old['id']);self.assertEqual(self.runner.file.read_bytes(),data)
  draft=self.manager.create(self.setup);self.manager.delete(draft['id'])
  self.assertEqual([r['id'] for r in self.manager.listing()],[latest['id']])
 def test_delete_blocks_all_active_work(self):
  from types import SimpleNamespace
  import threading
  w=self.manager.create(self.setup);self.start(w)
  with self.assertRaises(ValueError):self.manager.delete(w['id'])
  self.finish()
  for name in ['recommendations','platform_reviews']:
   setattr(self.runner,name,SimpleNamespace(lock=threading.RLock(),worker=SimpleNamespace(is_alive=lambda:True),active_run=w['id']))
   with self.assertRaises(ValueError):self.manager.delete(w['id'])
   delattr(self.runner,name)
  self.runner.lite.state={'status':'preparing','workspaceId':w['id']}
  with self.assertRaises(ValueError):self.manager.delete(w['id'])
  self.runner.lite.state={'status':'ready','workspaceId':w['id']}
  self.manager.delete(w['id']);self.assertEqual(self.runner.lite.snapshot()['status'],'idle')
