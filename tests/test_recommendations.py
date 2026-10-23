"""Real persistence, cancellation, stale evidence, provider boundaries; no paid calls."""
import functools
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from credential_companion import Runner
from judge_settings import JudgeSettings
from recommendations import Recommendations, ledger
import judge_provider

RUN='a'*32
class Vault:
    def get_password(self,*args):return 'judge-secret'


def fixture(tmp):
    runner=Runner(Path(tmp));runner.judge_settings=JudgeSettings(tmp,lambda:Vault())
    runner.judge_settings.path.write_text(json.dumps({'provider':'openai','model':'gpt-6-astra'}))
    services=[{'id':provider,'candidateId':f'{provider}-{i}','name':'Claude Code' if provider=='claude' else 'Codex','model':f'{provider}-test-{i}'} for i,provider in enumerate(['claude','claude','codex','codex','codex'])]
    tasks=[{'index':i,'name':'Task '+str(i),'acceptance':'Pass independent checks','suite':'Team tasks'} for i in range(3)]
    results=[{'candidateId':s['candidateId'],'agent':s['id'],'taskIndex':t['index'],'status':'completed','suite':t['suite'],'checkPassed':True,'durationSeconds':20+i,'usage':{'inputTokens':100,'outputTokens':50,'cacheReadTokens':0,'cacheWriteTokens':0,'estimatedCostUsd':.01,'tokenStatus':'complete','costStatus':'complete'}} for i,s in enumerate(services) for t in tasks]
    job={'id':RUN,'status':'completed','startedAt':1,'total':len(results),'plan':{'services':services,'tasks':tasks,'setup':{'gates':[{'id':'retention','name':'Retention','required':True}],'platforms':[{'id':'claude','enabled':True},{'id':'codex','enabled':True}],'org':{'developers':10},'weights':{'quality':40,'cost':20}}},'results':results}
    directory=runner.folder/'evaluations'/RUN;directory.mkdir(parents=True)
    (directory/'result.json').write_text(json.dumps(job));(directory/'plan.json').write_text(json.dumps(job['plan']))
    for s in services:
        for t in tasks:
            work=directory/'attempts'/str(t['index'])/s['candidateId'];work.mkdir(parents=True)
            (work/'solution.py').write_text('def add(a,b):\n    return a+b\n')
    return runner


def fake_request(provider,model,key,instructions,evidence,schema):
    candidates=schema['properties']['candidates']['items']['properties']['candidate']['enum']
    ref='task:0'
    finding={'text':'Independent checks passed for the sampled task.','evidence':[ref]}
    if 'headline' in schema['properties']:
        out={'headline':'Continue with a controlled pilot.','summary':'All models passed this sample; review effort is still unknown.',
             'preferredCandidate':candidates[0],'outcome':'preference','candidates':[{'candidate':c,'assessment':'Passed sampled checks','evidence':[ref]} for c in candidates],
             'reasons':[finding],'tradeoffs':[finding],'nextSteps':['Review implementations.','Repeat on harder tasks.'],'limitations':['Small sample; reliability is not established.']}
    else:
        out={'candidates':[{'candidate':c,'assessment':'Simple implementation; broader review needed.','strengths':[finding],'weaknesses':[]} for c in candidates], 'limitations':['Not independently calibrated.']}
    return {'id':'response-test','status':'completed','usage':{'input_tokens':1000,'input_tokens_details':{'cached_tokens':100},'output_tokens':200},'output':[{'type':'message','content':[{'type':'output_text','text':json.dumps(out)}]}]}


class RecommendationTests(unittest.TestCase):
    def test_success_persists_and_stale_reviews_and_exclusions(self):
        with tempfile.TemporaryDirectory() as tmp:
            runner=fixture(tmp);seen=[]
            def request(*args):seen.append(args);return fake_request(*args)
            manager=Recommendations(runner,runner.judge_settings,request)
            with self.assertRaises(ValueError):manager.start(RUN,[],False)
            manager.start(RUN,[],True);manager.worker.join(5)
            value=manager.status(RUN,[]);r=value['recommendation']
            self.assertEqual(r['status'],'completed');self.assertFalse(r['stale'])
            self.assertEqual(len(value['judgeRuns']),2);self.assertEqual(value['usage']['inputTokens']['value'],1800)
            self.assertAlmostEqual(value['usage']['estimatedCostUsd']['value'],.0382)
            self.assertEqual(r['readiness']['status'],'needs_review')
            self.assertEqual(r['readiness']['blocking'][0]['status'],'unverified')
            self.assertNotIn('candidateMap',seen[0][4]);self.assertNotIn('model',json.dumps(seen[0][4]['attempts']))
            self.assertEqual(seen[1][4]['candidateOrder'],list(reversed(seen[0][4]['candidates'])))
            self.assertTrue((runner.folder/'evaluations'/RUN/r['evidenceSnapshot']).exists())
            runner.review(RUN,'0:claude-0',{'accepted':True,'notes':'Human reviewed'})
            self.assertTrue(manager.status(RUN,[])['recommendation']['stale'])
            self.assertTrue(manager.status(RUN,['Team tasks'])['recommendation']['stale'])
            self.assertEqual(runner.history()[0]['usageSummary']['judge']['attempts'],2)
            self.assertNotIn('judge-secret',(runner.folder/'evaluations'/RUN/'recommendations.json').read_text())

    def test_invalid_output_preserves_billed_usage_no_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            runner=fixture(tmp);calls=[]
            def invalid(*args):
                calls.append(1);response=fake_request(*args);response['output'][0]['content'][0]['text']='{"unexpected": true}';return response
            manager=Recommendations(runner,runner.judge_settings,invalid);manager.start(RUN,[],True);manager.worker.join(5)
            status=manager.status(RUN)
            self.assertEqual(status['recommendation']['status'],'failed');self.assertEqual(len(calls),1)
            self.assertEqual(status['judgeRuns'][0]['usage']['inputTokens'],900)
            manager.request=fake_request;manager.start(RUN,[],True);manager.worker.join(5)
            self.assertEqual(len(manager.status(RUN)['judgeRuns']),3)

    def test_stop_blocks_next_call_and_rejects_duplicate_start(self):
        with tempfile.TemporaryDirectory() as tmp:
            runner=fixture(tmp);entered=threading.Event();release=threading.Event()
            def delayed(*args):entered.set();release.wait(5);return fake_request(*args)
            manager=Recommendations(runner,runner.judge_settings,delayed);manager.start(RUN,[],True)
            self.assertTrue(entered.wait(3))
            with self.assertRaises(ValueError):manager.start(RUN,[],True)
            manager.stop(RUN);self.assertEqual(manager.status(RUN)['recommendation']['status'],'stopping')
            release.set();manager.worker.join(5)
            status=manager.status(RUN);self.assertEqual(status['recommendation']['status'],'stopped')
            self.assertEqual(len(status['judgeRuns']),1);self.assertEqual(status['usage']['outputTokens']['value'],200)

    def test_restart_interrupted_and_invalid_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            runner=fixture(tmp);path=runner.folder/'evaluations'/RUN/'recommendations.json'
            path.write_text(json.dumps({'generations':[{'status':'comparing'}],'calls':[{'status':'running'}]}))
            manager=Recommendations(runner,runner.judge_settings,fake_request)
            self.assertEqual(ledger(path.parent)['generations'][0]['status'],'interrupted')
            with self.assertRaises(ValueError):manager.status('../outside')

    def test_usage_exact_prices_unknown_and_cache(self):
        response={'usage':{'input_tokens':1000,'input_tokens_details':{'cached_tokens':100},'output_tokens':200}}
        self.assertEqual(judge_provider.usage('openai','unknown',response)['estimatedCostUsd'],None)
        self.assertEqual(judge_provider.usage('openai','gpt-6-astra',{})['tokenStatus'],'unavailable')
        response['service_tier']='priority'
        self.assertEqual(judge_provider.usage('openai','gpt-6-astra',response)['estimatedCostUsd'],None)
        row=judge_provider.usage('anthropic','claude-sonnet-4-6',{'usage':{'input_tokens':1000,'output_tokens':100,'cache_read_input_tokens':100}})
        self.assertEqual(row['inputTokens'],1000);self.assertAlmostEqual(row['estimatedCostUsd'],.00453)

    def test_provider_payload_is_structured_separate_credentials_no_tools_execute(self):
        class Response:
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self,*args):return b'{"status":"completed"}'
        with patch('urllib.request.urlopen',return_value=Response()) as call:
            judge_provider.request('openai','catalog-model','judge-key','Instructions',{'data':'untrusted'}, {'type':'object'})
            request=call.call_args.args[0];body=json.loads(request.data)
            self.assertEqual(request.full_url,'https://api.openai.com/v1/responses')
            self.assertEqual(request.headers['Authorization'],'Bearer judge-key')
            self.assertFalse(body['store']);self.assertTrue(body['text']['format']['strict']);self.assertNotIn('tools',body)
            judge_provider.request('anthropic','catalog-model','judge-key','Instructions',{}, {'type':'object'})
            body=json.loads(call.call_args.args[0].data)
            self.assertEqual(body['tool_choice'],{'type':'tool','name':'report'})
            self.assertEqual(body['tools'][0]['name'],'report')
