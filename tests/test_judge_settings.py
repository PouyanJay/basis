import json
import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'scripts'))
from judge_settings import JudgeSettings
from evidence_package import requirements, build_package

class Vault:
    def __init__(self):self.values={}
    def get_password(self,scope,key):return self.values.get((scope,key))
    def set_password(self,scope,key,value):self.values[(scope,key)]=value

class JudgeTests(unittest.TestCase):
    def test_separate_credentials_real_catalog_and_persistence(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault=Vault();vault.set_password('basis-local','OPENAI_API_KEY','candidate-secret')
            manager=JudgeSettings(tmp,lambda:vault)
            self.assertFalse(manager.status()['configured'])
            with patch('model_discovery.request_json',return_value={'data':[{'id':'judge-test'}]}) as request:
                manager.models('openai','judge-secret')
                self.assertEqual(request.call_args.args[1]['Authorization'],'Bearer judge-secret')
                self.assertEqual(vault.get_password('basis-local','OPENAI_API_KEY'),'candidate-secret')
                manager.save('openai','judge-test')
                with self.assertRaises(ValueError):manager.save('openai','invented-model')
            raw=manager.path.read_text();self.assertNotIn('judge-secret',raw)
            self.assertEqual(JudgeSettings(tmp,lambda:vault).status()['model'],'judge-test')
            self.assertFalse(manager.status('anthropic')['configured'])
            with patch('model_discovery.request_json',side_effect=RuntimeError('Rejected')):
                with self.assertRaises(RuntimeError):manager.models('openai','invalid-secret')
            self.assertEqual(vault.get_password('basis-judge','openai'),'judge-secret')

    def test_evidence_required_and_legacy_pass_is_not_verified(self):
        setup={'platforms':[{'id':'claude','enabled':True}],'gates':[{'id':'retention','name':'Retention','required':True}],'gateResults':{'claude':{'retention':'pass'}}}
        self.assertEqual(requirements(setup)[0]['status'],'unverified')
        review={'status':'pass','url':'https://example.com/policy','notes':'Account configuration checked','reviewer':'Alex','reviewedAt':'2026-10-22T20:00:00Z'}
        setup['gateEvidence']={'claude':{'retention':review}}
        self.assertEqual(requirements(setup)[0]['status'],'pass')
        review['url']='javascript:alert(1)'
        self.assertEqual(requirements(setup)[0]['status'],'unverified')

    def test_package_is_bounded_uses_artifact_boundary_and_digest_changes(self):
        class Runner:
            def artifact_files(self,run):
                if run!='test':raise ValueError('Invalid run')
            def history(self):return [job]
            def artifacts(self,*args):return {'files':[{'name':'workspace/a.py','size':10},{'name':'workspace/large','size':500001}]}
            def artifact(self,*args):return {'text':'print(1)'}
        job={'id':'test','plan':{'services':[{'id':'claude','model':'test-model'}],'tasks':[{'index':0,'name':'Task','acceptance':'Pass tests'}],'setup':{}},'results':[{'agent':'claude','taskIndex':0,'status':'completed','checkPassed':True}]}
        runner=Runner();package=build_package(runner,'test')
        self.assertEqual(package['evidence']['attempts'][0]['candidate'],'C1')
        self.assertFalse(package['evidence']['attempts'][0]['artifacts'][1]['included'])
        self.assertEqual(package,build_package(runner,'test'))
        job['reviews']={'0:claude':{'accepted':True}}
        self.assertNotEqual(package['evidenceDigest'],build_package(runner,'test')['evidenceDigest'])
        with self.assertRaises(ValueError):build_package(runner,'../outside')
