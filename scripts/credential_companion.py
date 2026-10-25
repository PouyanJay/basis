#!/usr/bin/env python3
"""Loopback-only Basis UI, OS credential storage, and isolated public-fixture runner."""
import argparse
import functools
import http.server
import json
import os
import pathlib
import re
import secrets
import shutil
import subprocess
import threading
import time
import urllib.parse
import uuid

ROOT = pathlib.Path(__file__).resolve().parents[1]
KEYS = {'claude': 'ANTHROPIC_API_KEY', 'codex': 'OPENAI_API_KEY', 'cursor': 'CURSOR_API_KEY'}
ALLOWED = frozenset(KEYS.values())
STATIC = {'index.html', 'app.js', 'core.js', 'technology.js', 'benchmarks.js', 'styles.css', 'brand.svg', 'favicon.svg'}
IMAGE = 'basis-local-runner:v1'


def vault():
    try:
        import keyring
        backend = keyring.get_keyring()
        if type(backend).__module__ not in {'keyring.backends.macOS', 'keyring.backends.Windows', 'keyring.backends.SecretService', 'keyring.backends.kwallet'}:
            raise RuntimeError('No supported OS credential store. Enable Keychain, Windows Credential Locker, Secret Service, or KWallet.')
        return backend
    except ImportError:
        raise RuntimeError('Install local dependencies: python3 -m pip install -r requirements-local.txt') from None


def docker_ready():
    try:
        return subprocess.run(['docker', 'info', '--format', '{{.ServerVersion}}'], capture_output=True, timeout=5).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def required_key(agent, model):
    if agent == 'opencode':
        if not model.startswith(('openai/', 'anthropic/')):
            raise ValueError('OpenCode requires an openai/model or anthropic/model identifier.')
        return 'ANTHROPIC_API_KEY' if model.startswith('anthropic/') else 'OPENAI_API_KEY'
    if agent not in KEYS:
        raise ValueError('This service has no local runner yet.')
    return KEYS[agent]


# Permit imports when loaded by the test harness as well as launched as a script.
import sys
sys.path.insert(0, str(ROOT / 'scripts'))
from local_evaluation import EvaluationRunner, benchmark_pack
from humaneval_pack import prepare as prepare_humaneval
from model_discovery import discover

from judge_settings import JudgeSettings
from evidence_package import build_package
from recommendations import Recommendations
from platform_review import PlatformReviews, eligible as review_eligible
from run_workspaces import RunWorkspaces

class Runner(EvaluationRunner):
    def __init__(self, folder=None):
        super().__init__(folder, ROOT, lambda: vault(), lambda: docker_ready(), required_key, ALLOWED)
        self.judge_settings = JudgeSettings(self.folder, lambda: vault())
        self.recommendations = Recommendations(self, self.judge_settings)
        self.platform_reviews = PlatformReviews(self, self.judge_settings)
        self.workspaces = RunWorkspaces(self)

    def start(self, plan, consent, workspace_id=None, frozen_plan=None):
        if not isinstance(plan,dict):raise ValueError('Invalid evaluation plan.')
        setup=plan.get('setup',{})
        include=review_eligible(setup) and plan.get('platformReview',True) is not False
        if include:self.platform_reviews.validate_start(setup)
        job=super().start(plan,consent,workspace_id=workspace_id,frozen_plan=frozen_plan)
        if include:
            try:self.platform_reviews.start(job['id'],consent=True)
            except (ValueError,RuntimeError) as error:
                # Coding has already started; keep research failure isolated and retryable.
                self.platform_reviews.save(job['id'],{'generations':[{'id':uuid.uuid4().hex,'status':'failed','units':[],'requirements':[],'configurations':[],'error':str(error),'startedAt':time.time()}],'calls':[]})
        return job



class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, token, runner, **kwargs):
        self.secret_token, self.runner = token, runner
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def _json(self, code, payload):
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def end_headers(self):
        self.send_header('Content-Security-Policy', "frame-ancestors 'none'")
        super().end_headers()

    def _host_ok(self):
        return self.headers.get('Host') in {f'localhost:{self.server.server_port}', f'127.0.0.1:{self.server.server_port}'}

    def _same_origin(self):
        return self._host_ok() and self.headers.get('Origin') == 'http://' + self.headers.get('Host', '')

    def do_GET(self):
        if not self._host_ok():
            self._json(403, {'error': 'Open the loopback address printed by Basis.'}); return
        if self.path == '/api/health':
            self._json(200, {'service': 'basis-local-companion', 'token': self.secret_token}); return
        name = urllib.parse.urlsplit(self.path).path.lstrip('/') or 'index.html'
        if name not in STATIC:
            self._json(404, {'error': 'Not found'}); return
        self.path = '/' + name
        super().do_GET()

    def do_HEAD(self):
        name = urllib.parse.urlsplit(self.path).path.lstrip('/') or 'index.html'
        if not self._host_ok() or name not in STATIC:
            self.send_error(404); return
        self.path = '/' + name
        super().do_HEAD()

    def do_POST(self):
        if not self._same_origin() or not secrets.compare_digest(self.headers.get('X-Basis-Token', ''), self.secret_token):
            self._json(403, {'error': 'Open Basis from this local companion.'}); return
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if self.headers.get('Content-Type', '').split(';')[0] != 'application/json' or not 1 <= length <= 500000:
                raise ValueError('Expected a JSON request under 500 KB.')
            item = json.loads(self.rfile.read(length))
            if not isinstance(item, dict):
                raise ValueError('Expected a JSON object.')
            if self.path == '/api/local/status':
                configured, issue = {}, ''
                try:
                    store = vault()
                    configured = {name: bool(store.get_password('basis-local', name)) for name in ALLOWED}
                except Exception:
                    issue = 'OS credential store unavailable. Install requirements-local.txt and unlock your OS credential store.'
                self._json(200, {'integratedBenchmarks': True, 'multiModel': True, 'configured': configured, 'credentialError': issue, 'dockerReady': docker_ready(), 'job': self.runner.snapshot()}); return
            if self.path.startswith('/api/local/workspace-'):
                manager=self.runner.workspaces
                if self.path.endswith('-list'):self._json(200,{'runs':manager.listing()});return
                if self.path.endswith('-get'):self._json(200,{'run':manager.get(item.get('id'))});return
                if self.path.endswith('-create'):self._json(201,{'run':manager.create(item.get('setup'))});return
                if self.path.endswith('-save'):self._json(200,{'run':manager.save(item.get('id'),item.get('setup'),item.get('revision'))});return
                if self.path.endswith('-clone'):self._json(201,{'run':manager.clone(item.get('id'))});return
                if self.path.endswith('-start'):self._json(202,{'job':manager.start(item.get('id'),item.get('revision'),item.get('consent'))});return
            if self.path == '/api/local/job':
                self._json(200, {'job': self.runner.snapshot()}); return
            if self.path.startswith('/api/local/judge-'):
                if not hasattr(self.runner,'judge_settings'):
                    self.runner.judge_settings = JudgeSettings(self.runner.folder, vault)
                manager = self.runner.judge_settings
                if self.path == '/api/local/judge-status':
                    self._json(200, manager.status(item.get('provider'))); return
                if self.path == '/api/local/judge-models':
                    self._json(200, manager.models(item.get('provider'), item.get('key'))); return
                if self.path == '/api/local/judge-save':
                    self._json(200, manager.save(item.get('provider'), item.get('model'))); return
            if self.path.startswith('/api/local/platform-review-'):
                manager=self.runner.platform_reviews
                if self.path.endswith('-status'):
                    self._json(200,manager.status(item.get('id')));return
                if self.path.endswith('-start'):
                    self._json(202,manager.start(item.get('id'),item.get('consent'),item.get('refresh') is True));return
                if self.path.endswith('-stop'):
                    self._json(200,manager.stop(item.get('id')));return
            if self.path.startswith('/api/local/recommendation-'):
                manager = self.runner.recommendations
                if self.path == '/api/local/recommendation-status':
                    self._json(200, manager.status(item.get('id'),item.get('excludedSuites'))); return
                if self.path == '/api/local/recommendation-start':
                    self._json(202, manager.start(item.get('id'),item.get('excludedSuites',[]),item.get('consent'))); return
                if self.path == '/api/local/recommendation-stop':
                    self._json(200, manager.stop(item.get('id'))); return
            if self.path == '/api/local/evidence-package':
                self._json(200, build_package(self.runner,item.get('id'))); return
            if self.path == '/api/local/models':
                self._json(200, discover(item.get('service'), item.get('provider'), vault())); return
            if self.path == '/api/local/credentials':
                name, value = item.get('secret'), item.get('value')
                if name not in ALLOWED or not isinstance(value, str) or not 8 <= len(value) <= 8000 or any(c in value for c in '\r\n\x00'):
                    raise ValueError('Choose a supported provider and enter a single-line key.')
                try:
                    vault().set_password('basis-local', name, value)
                except Exception:
                    self._json(503, {'error': 'Could not save to the OS credential store. Install local dependencies and unlock the store.'}); return
                self._json(200, {'saved': True, 'name': name}); return
            if self.path == '/api/local/artifacts':
                self._json(200, self.runner.artifacts(item.get('id'), item.get('key'))); return
            if self.path == '/api/local/artifact':
                self._json(200, self.runner.artifact(item.get('id'), item.get('name'), item.get('key'))); return
            if self.path == '/api/local/evaluations':
                self._json(200, {'evaluations': self.runner.history()}); return
            if self.path == '/api/local/stop':
                job=self.runner.snapshot()
                if item.get('id') and (not job or item['id']!=job['id']):raise ValueError('This is not the active run.')
                if job:self.runner.platform_reviews.stop(job['id'])
                self._json(200, {'job': self.runner.stop()}); return
            if self.path == '/api/local/review':
                self._json(200, {'job': self.runner.review(item.get('id'), item.get('key'), item.get('review'))}); return
            if self.path == '/api/local/prepare-swebench':
                owner=item.get('workspaceId')
                if owner and self.runner.workspaces.get(owner)['status']!='draft':raise ValueError('Clone this run before changing benchmarks.')
                self._json(202, {'benchmark': self.runner.lite.start(item.get('count', 5),workspace_id=owner)}); return
            if self.path == '/api/local/swebench-status':
                self._json(200, {'benchmark': self.runner.lite.snapshot()}); return
            if self.path == '/api/local/cancel-swebench':
                with self.runner.lite.lock:
                    if self.runner.lite.snapshot().get('workspaceId')!=item.get('workspaceId'):raise ValueError('Benchmark preparation belongs to another run.')
                    self._json(200, {'benchmark': self.runner.lite.stop()}); return
            if self.path == '/api/local/prepare-humaneval':
                path = prepare_humaneval(self.runner.folder, item.get('count', 5))
                self._json(200, {'path': path, 'benchmark': benchmark_pack(path)}); return
            if self.path == '/api/local/benchmark':
                self._json(200, {'benchmark': benchmark_pack(item.get('path', ''))}); return
            if self.path == '/api/local/run':
                self._json(202, {'job': self.runner.start(item.get('plan'), item.get('consent'))}); return
            self._json(404, {'error': 'Unknown route'})
        except ValueError as error:
            self._json(400, {'error': str(error)})
        except (TypeError, KeyError, OSError):
            self._json(400, {'error': 'Invalid request or inaccessible local file. Check paths and permissions.'})
        except RuntimeError as error:
            self._json(503, {'error': str(error)})

    def log_message(self, *args):
        pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    runner = Runner()
    server = http.server.ThreadingHTTPServer(('127.0.0.1', args.port), functools.partial(Handler, token=secrets.token_urlsafe(32), runner=runner))
    print(f'Open http://127.0.0.1:{server.server_port}/ ; localhost only. Press Ctrl+C to stop.', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        if runner.platform_reviews.active_run:
            runner.platform_reviews.stop(runner.platform_reviews.active_run)
        runner.lite.stop()
        runner.stop()
        server.server_close()

if __name__ == '__main__':
    main()
