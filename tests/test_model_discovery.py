import io
import json
import pathlib
import sys
import unittest
import urllib.error
from unittest.mock import Mock, patch
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]/'scripts'))
import model_discovery as models

class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.store=Mock()
        self.store.get_password.return_value='test-only-secret'

    def test_missing_key_never_calls_provider(self):
        self.store.get_password.return_value=None
        with patch.object(models,'request_json') as request:
            with self.assertRaises(ValueError):models.discover('codex',None,self.store)
            request.assert_not_called()

    def test_authenticated_anthropic_pagination_and_opencode_prefix(self):
        with patch.object(models,'request_json',side_effect=[
            {'data':[{'id':'claude-fixture-a','display_name':'Claude fixture A'}],'has_more':True,'last_id':'claude-fixture-a'},
            {'data':[{'id':'claude-fixture-b','display_name':'Claude fixture B'}],'has_more':False}
        ]) as request:
            result=models.discover('opencode','anthropic',self.store)
            self.assertEqual([m['id'] for m in result['models']],['anthropic/claude-fixture-a','anthropic/claude-fixture-b'])
            self.assertIn('after_id=claude-fixture-a',request.call_args.args[0])
            self.assertEqual(request.call_args.args[1]['x-api-key'],'test-only-secret')
            self.assertNotIn('test-only-secret',json.dumps(result))

    def test_openai_uses_only_returned_ids_without_static_fallback(self):
        with patch.object(models,'request_json',return_value={'data':[{'id':'future-model-123'},{'id':'future-model-123'}]}) as request:
            result=models.discover('codex',None,self.store)
            self.assertEqual(result['models'],[{'id':'future-model-123','name':'future-model-123'}])
            self.assertEqual(request.call_args.args[0],'https://api.openai.com/v1/models')
            self.assertEqual(request.call_args.args[1]['Authorization'],'Bearer test-only-secret')
        with patch.object(models,'request_json',return_value={'data':[]}):
            self.assertEqual(models.discover('claude',None,self.store)['models'],[])

    def test_repeated_pagination_and_bad_responses_fail_closed(self):
        for response in [{},[],{'data':None},{'data':[],'has_more':True,'last_id':'same'}]:
            with patch.object(models,'request_json',return_value=response):
                with self.assertRaises(RuntimeError):models.discover('claude',None,self.store)

    def test_errors_do_not_expose_provider_body_or_key(self):
        for code in [401,403,429,500,302]:
            error=urllib.error.HTTPError('https://api.openai.com/v1/models',code,'test-only-secret',{},io.BytesIO(b'test-only-secret'))
            with patch.object(models.urllib.request,'build_opener') as opener:
                opener.return_value.open.side_effect=error
                with self.assertRaises(RuntimeError) as caught:models.request_json('https://api.openai.com/v1/models',{})
                self.assertNotIn('test-only-secret',str(caught.exception))
        self.assertIsNone(models.NoRedirect().redirect_request(None,None,None,None,None,None))

    def test_cursor_parses_actual_cli_format_not_headers_or_tips(self):
        rows=models.parse_cursor_models('Available models\n\n\x1b[36mfixture-coder\x1b[0m - Fixture Coder (current, default)\nother-id - Other\n\nTip: use --model <id>\n')
        self.assertEqual(rows,[{'id':'fixture-coder','name':'Fixture Coder'},{'id':'other-id','name':'Other'}])
        self.assertEqual(models.parse_cursor_models('No models available for this account.'),[])

    def test_cursor_saved_key_in_environment_not_arguments(self):
        with patch.object(models.shutil,'which',return_value='/usr/bin/cursor-agent'),patch.object(models.subprocess,'run',return_value=Mock(returncode=0,stdout='Available models\nfixture-id - Fixture\n')) as run:
            result=models.discover('cursor',None,self.store)
            self.assertEqual(result['models'][0]['id'],'fixture-id')
            self.assertEqual(run.call_args.kwargs['env']['CURSOR_API_KEY'],'test-only-secret')
            self.assertNotIn('test-only-secret',' '.join(run.call_args.args[0]))

if __name__=='__main__':unittest.main()
