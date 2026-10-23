import json
import pathlib
import sys
import unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'scripts'))
from usage_accounting import UsageTracker, aggregate, summaries


def claude_result(cost=.012345, subtype='success'):
    return {'type':'result','subtype':subtype,'total_cost_usd':cost,'usage':{'input_tokens':999},
            'modelUsage':{'main':{'inputTokens':100,'outputTokens':20,'cacheReadInputTokens':200,'cacheCreationInputTokens':30},
                          'subagent':{'inputTokens':10,'outputTokens':5,'cacheReadInputTokens':0,'cacheCreationInputTokens':0}}}


class UsageTests(unittest.TestCase):
    def test_final_whole_tree_replaces_steps_and_duplicate_results(self):
        t=UsageTracker('claude')
        event={'type':'assistant','message':{'id':'msg_1','usage':{'input_tokens':500,'output_tokens':1,'cache_read_input_tokens':100,'cache_creation_input_tokens':20}}}
        t.consume(event);t.consume(event)
        self.assertEqual(t.snapshot()['inputTokens'],500)
        self.assertIsNone(t.snapshot()['outputTokens'])
        t.consume(claude_result());t.consume(claude_result())
        row=t.snapshot()
        self.assertEqual([row[f] for f in ('inputTokens','outputTokens','cacheReadTokens','cacheWriteTokens')],[110,25,200,30])
        self.assertEqual(row['estimatedCostUsd'],.012345)
        self.assertEqual(row['tokenStatus'],'complete')

    def test_error_result_retains_cost_and_timeout_preserves_partial(self):
        t=UsageTracker('claude');t.consume(claude_result(subtype='error_max_turns'))
        self.assertEqual(t.snapshot()['estimatedCostUsd'],.012345)
        t=UsageTracker('claude');t.consume({'type':'assistant','message':{'id':'x','usage':{'input_tokens':100,'output_tokens':1}}})
        t.consume({'type':'result','subtype':'error_during_execution','usage':{'input_tokens':0,'output_tokens':0},'total_cost_usd':0})
        row=t.snapshot()
        self.assertEqual(row['inputTokens'],100)
        self.assertIsNone(row['outputTokens']);self.assertIsNone(row['estimatedCostUsd'])
        self.assertEqual(row['tokenStatus'],'partial')

    def test_main_loop_fallback_is_not_whole_tree(self):
        t=UsageTracker('claude');t.consume({'type':'result','usage':{'input_tokens':100,'output_tokens':5},'total_cost_usd':.001})
        self.assertEqual(t.snapshot()['tokenStatus'],'partial')
        self.assertEqual(t.snapshot()['costStatus'],'complete')
        self.assertIsNone(t.snapshot()['cacheReadTokens'])

    def test_invalid_and_unknown_prices_are_not_zero_cost(self):
        for value in (-1,float('nan'),float('inf'),True,'1'):
            t=UsageTracker('claude');t.consume(claude_result(value))
            self.assertIsNone(t.snapshot()['estimatedCostUsd'])
        t=UsageTracker('claude');t.consume(claude_result(0));self.assertIsNone(t.snapshot()['estimatedCostUsd'])
        t=UsageTracker('cursor');self.assertIsNone(t.snapshot()['estimatedCostUsd'])
        self.assertEqual(t.snapshot()['tokenStatus'],'unavailable')

    def test_codex_cache_is_not_double_counted(self):
        t=UsageTracker('codex');t.consume({'type':'turn.started'})
        event={'type':'turn.completed','usage':{'input_tokens':1000,'cached_input_tokens':800,'output_tokens':50}}
        t.consume(event);t.consume(event)
        row=t.snapshot(True)
        self.assertEqual(row['inputTokens'],200);self.assertEqual(row['cacheReadTokens'],800)
        self.assertEqual(row['outputTokens'],50);self.assertIsNone(row['cacheWriteTokens'])
        self.assertIsNone(row['estimatedCostUsd'])
        t.consume({'type':'turn.started'});t.consume(event)
        self.assertEqual(t.snapshot(True)['inputTokens'],400)

    def test_opencode_steps_deduplicate(self):
        t=UsageTracker('opencode')
        event={'type':'step_finish','part':{'id':'part1','cost':.002,'tokens':{'input':100,'output':20,'reasoning':10,'cache':{'read':5,'write':0}}}}
        t.consume(event);t.consume(event)
        self.assertEqual(t.snapshot(True)['outputTokens'],30)
        self.assertEqual(t.snapshot(True)['estimatedCostUsd'],.002)
        self.assertEqual(t.snapshot(False)['costStatus'],'partial')

    def test_totals_include_errors_unknown_and_separate_judge(self):
        t=UsageTracker('claude');t.consume(claude_result(.1));row=t.snapshot()
        job={'plan':{'services':[{'candidateId':'c'}]},'results':[{'candidateId':'c','status':'error','usage':row},{'candidateId':'c','status':'completed'}],
             'judgeRuns':[{'usage':{**row,'estimatedCostUsd':.2}}]}
        report=summaries(job)
        self.assertEqual(report['candidates']['estimatedCostUsd'],{'value':.1,'recorded':1,'complete':1,'total':2})
        self.assertEqual(report['judge']['estimatedCostUsd']['value'],.2)
        self.assertEqual(report['models']['c'],report['candidates'])
        self.assertIsNone(aggregate([{}])['inputTokens']['value'])
        self.assertEqual(aggregate([row,{**row,'estimatedCostUsd':.2}])['estimatedCostUsd']['value'],.3)

    def test_active_usage_is_preserved_and_not_counted_twice(self):
        t=UsageTracker('claude');t.consume(claude_result())
        active={'candidateId':'c','taskIndex':0,'usage':t.snapshot()}
        job={'plan':{'services':[{'candidateId':'c'}]},'activeUsage':active,'results':[]}
        self.assertEqual(summaries(job)['candidates']['attempts'],1)
        job['results']=[active]
        self.assertEqual(summaries(job)['candidates']['attempts'],1)

    def test_dropped_output_cannot_claim_complete(self):
        t=UsageTracker('claude');t.consume(claude_result());t.dropped=True
        self.assertEqual(t.snapshot()['tokenStatus'],'partial')
        self.assertEqual(t.snapshot()['costStatus'],'partial')
