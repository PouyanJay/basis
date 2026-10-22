import functools
import http.server
import importlib.util
import json
import pathlib
import subprocess
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch, MagicMock

SCRIPT = pathlib.Path(__file__).resolve().parents[1] / 'scripts/credential_companion.py'
spec = importlib.util.spec_from_file_location('bridge', SCRIPT)
bridge = importlib.util.module_from_spec(spec); spec.loader.exec_module(bridge)

class Store:
    def __init__(self): self.values = {}
    def get_password(self, service, name): return self.values.get((service, name))
    def set_password(self, service, name, value): self.values[service, name] = value

class CompanionTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.runner = bridge.Runner(self.folder.name)
        self.store = Store()
        self.vault = patch.object(bridge, 'vault', return_value=self.store); self.vault.start()
        self.docker = patch.object(bridge, 'docker_ready', return_value=True); self.docker.start()
        self.server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(bridge.Handler, token='test-token', runner=self.runner))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True); self.thread.start()
        self.base = f'http://127.0.0.1:{self.server.server_port}'
    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.vault.stop(); self.docker.stop(); self.folder.cleanup()
    def request(self, path, data=None, **headers):
        defaults = {'Content-Type':'application/json', 'Origin':self.base, 'X-Basis-Token':'test-token'}
        defaults.update(headers)
        req = urllib.request.Request(self.base + path, data=None if data is None else json.dumps(data).encode(), headers=defaults)
        try:
            with urllib.request.urlopen(req) as r: return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e: return e.code, json.loads(e.read())
    def test_boundaries(self):
        for headers in [{'Origin':'https://evil.example'}, {'X-Basis-Token':'bad'}, {'Host':'evil.example'}]:
            self.assertEqual(self.request('/api/local/status', {}, **headers)[0], 403)
        self.assertEqual(self.request('/api/health', Host='evil.example')[0], 403)
        for path in ['/.git/config', '/scripts/credential_companion.py', '/requirements-local.txt', '/api/local/status']:
            self.assertEqual(self.request(path)[0], 404)
    def test_save_and_detect_without_disclosing(self):
        code, _ = self.request('/api/local/credentials', {'secret':'OPENAI_API_KEY', 'value':'test-secret-value'})
        self.assertEqual(code, 200)
        code, result = self.request('/api/local/status', {})
        self.assertTrue(result['configured']['OPENAI_API_KEY'])
        self.assertNotIn('test-secret-value', json.dumps(result))
        self.assertFalse(result['configured']['ANTHROPIC_API_KEY'])
    def test_invalid_credentials(self):
        for data in [{'secret':'ADMIN_KEY','value':'test-key-value'}, {'secret':'OPENAI_API_KEY','value':'test\nkey-value'}, {'secret':'OPENAI_API_KEY','value':'short'}]:
            self.assertEqual(self.request('/api/local/credentials', data)[0], 400)
    def test_locked_store(self):
        with patch.object(bridge, 'vault', side_effect=RuntimeError('locked')):
            result = self.request('/api/local/status', {})[1]
            self.assertTrue(result['credentialError'])
            self.assertEqual(result['configured'], {})
    def test_requires_key_and_explicit_consent(self):
        data = {'agents':[{'agent':'codex'}], 'consent':True}
        self.assertEqual(self.request('/api/local/run', data)[0], 400)
        self.store.set_password('basis-local','OPENAI_API_KEY','test-secret')
        self.assertEqual(self.request('/api/local/run', {**data,'consent':False})[0], 400)
        self.assertEqual(self.request('/api/local/run', {**data,'agents':[{'agent':'opencode','model':'unknown/model'}]})[0],400)
    def test_invalid_plan_rejected(self):
        self.store.set_password('basis-local','OPENAI_API_KEY','test-secret')
        self.assertEqual(self.request('/api/local/run', {'consent':True,'plan':{}})[0],400)

if __name__ == '__main__': unittest.main()
