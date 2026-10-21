import importlib.util
import http.server
import json
import pathlib
import subprocess
import tempfile
import threading
import urllib.request
import urllib.error
import unittest
from unittest.mock import patch

SCRIPT=pathlib.Path(__file__).resolve().parents[1]/'scripts'/'credential_companion.py'
spec=importlib.util.spec_from_file_location('bridge',SCRIPT)
bridge=importlib.util.module_from_spec(spec);spec.loader.exec_module(bridge)

class CompanionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from functools import partial
        cls.token='test-csrf-token'
        cls.server=http.server.ThreadingHTTPServer(('127.0.0.1',0),partial(bridge.Handler,token=cls.token))
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
        cls.base=f'http://127.0.0.1:{cls.server.server_port}'
    @classmethod
    def tearDownClass(cls):cls.server.shutdown();cls.server.server_close()
    def request(self,obj,origin=None,token=None):
        data=json.dumps(obj).encode()
        req=urllib.request.Request(self.base+'/api/secrets',data=data,headers={'Content-Type':'application/json','Origin':origin or self.base,'X-Basis-Token':token or self.token},method='POST')
        try:
            with urllib.request.urlopen(req) as r:return r.status,json.loads(r.read())
        except urllib.error.HTTPError as e:return e.code,json.loads(e.read())
    def test_blocks_cross_origin(self):
        status,_=self.request({'repo':'a/b','secret':'OPENAI_API_KEY','value':'fake-key-value'},origin='https://evil.example')
        self.assertEqual(status,403)
    def test_blocks_wrong_token(self):
        status,_=self.request({'repo':'a/b','secret':'OPENAI_API_KEY','value':'fake-key-value'},token='bad-token')
        self.assertEqual(status,403)
    def test_blocks_unknown_secret(self):
        status,_=self.request({'repo':'a/b','secret':'ADMIN_TOKEN','value':'fake-key-value'})
        self.assertEqual(status,400)
    def test_blocks_newline(self):
        status,_=self.request({'repo':'a/b','secret':'OPENAI_API_KEY','value':'fake-key-value\nSECRET=other'})
        self.assertEqual(status,400)
    def test_gh_stdin_handoff(self):
        def fake_run(argv,**kw):
            self.assertEqual(argv,['gh','secret','set','-f','-','-R','org/repo'])
            self.assertEqual(kw['input'],'OPENAI_API_KEY=fake-key-value\n')
            return subprocess.CompletedProcess(argv,0)
        with patch.object(bridge.shutil,'which',return_value='/usr/bin/gh'),patch.object(bridge.subprocess,'run',side_effect=fake_run):
            status,response=self.request({'repo':'org/repo','secret':'OPENAI_API_KEY','value':'fake-key-value'})
        self.assertEqual(status,200)
        self.assertEqual(response,{'saved':True,'name':'OPENAI_API_KEY'})
if __name__=='__main__':unittest.main()
