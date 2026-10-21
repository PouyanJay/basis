import unittest,sys,pathlib
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'scripts'))
from sample_swebench import make_manifest
from compare_swebench import compare
class BenchmarkFlowTest(unittest.TestCase):
 def setUp(self): self.rows=[{'repo':['org/A','org/B','org/C'][i%3],'instance_id':f'case-{i:03d}'} for i in range(300)]
 def test_counts_and_nested(self):
  a=make_manifest(self.rows,42,10,'a'*40);b=make_manifest(self.rows,42,25,'a'*40)
  self.assertEqual(a['selectedCount'],30);self.assertEqual(b['selectedCount'],75)
  self.assertEqual(b['instanceIds'][:30],a['instanceIds']);self.assertEqual(len(set(b['instanceIds'])),75)
 def test_repeatable_and_seed(self):
  self.assertEqual(make_manifest(self.rows,42,10,'sha'),make_manifest(self.rows,42,10,'sha'))
  self.assertNotEqual(make_manifest(self.rows,42,10,'sha')['instanceIds'],make_manifest(self.rows,43,10,'sha')['instanceIds'])
 def test_full(self):self.assertEqual(make_manifest(self.rows,'anything',100,'sha')['selectedCount'],300)
 def test_invalid_dataset(self):
  with self.assertRaises(ValueError):make_manifest(self.rows[:299],42,10,'sha')
 def test_compare(self):
  base={'datasetRevision':'x','harnessRevision':'h','tasks':[{'id':'one','status':'resolved'},{'id':'two','status':'error'}],'agent':'codex','model':'z'}
  out=compare([base,{**base,'agent':'claude'}]);self.assertEqual(out['candidates'][0]['resolvedRate'],.5)
  with self.assertRaises(ValueError):compare([base,{**base,'agent':'claude','tasks':base['tasks'][:1]}])
if __name__=='__main__':unittest.main()
