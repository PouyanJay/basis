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


class Runner:
    def __init__(self, folder=None):
        self.folder = pathlib.Path(folder or pathlib.Path.home() / '.local/share/basis')
        self.folder.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.lock = threading.RLock()
        self.job = None
        self.file = self.folder / 'latest-run.json'
        if self.file.exists():
            try:
                self.job = json.loads(self.file.read_text())
                if self.job['status'] in ('preparing', 'running'):
                    container = self.job.get('container', '')
                    if re.fullmatch(r'basis-[a-f0-9]{32}', container):
                        self.remove_container(container)
                    self.job.update(status='interrupted', message='The local companion stopped. Start a new run when ready.', container=None)
            except (ValueError, KeyError):
                self.job = None

    @staticmethod
    def remove_container(name):
        try:
            subprocess.run(['docker', 'rm', '-f', name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
        except (OSError, subprocess.TimeoutExpired):
            pass

    def stop(self):
        job = self.snapshot()
        if job and job['status'] in ('preparing', 'running'):
            if job.get('container'):
                self.remove_container(job['container'])
            self.update(status='interrupted', message='The local companion stopped.', container=None)

    def snapshot(self):
        with self.lock:
            return json.loads(json.dumps(self.job))

    def update(self, **values):
        with self.lock:
            self.job.update(values)
            temp = self.file.with_suffix('.tmp')
            fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, 'w') as f:
                json.dump(self.job, f)
            temp.replace(self.file)

    def start(self, entries, consent):
        if consent is not True:
            raise ValueError('Confirm provider API usage before starting.')
        if not isinstance(entries, list) or not 1 <= len(entries) <= 4:
            raise ValueError('Select one to four supported services.')
        seen, prepared = set(), []
        store = vault()
        for entry in entries:
            if not isinstance(entry, dict):
                raise ValueError('Invalid service configuration.')
            agent, model = entry.get('agent'), entry.get('model', '')
            if not isinstance(agent, str):
                raise ValueError('Invalid service.')
            if not isinstance(model, str) or len(model) > 100 or (model and not re.fullmatch(r'[\w./:-]+', model, re.ASCII)):
                raise ValueError('Invalid model identifier.')
            key = required_key(agent, model)
            if agent in seen:
                raise ValueError('Select each service only once.')
            seen.add(agent)
            value = store.get_password('basis-local', key)
            if not value:
                raise ValueError(f'Configure {key} in Settings first.')
            prepared.append((agent, model, key, value))
        if not docker_ready():
            raise ValueError('Start Docker, then check connection again.')
        with self.lock:
            if self.job and self.job['status'] in ('preparing', 'running'):
                raise ValueError('A test is already running. Wait for it to finish.')
            self.job = {'id': uuid.uuid4().hex, 'status': 'preparing', 'message': 'Preparing the local runner. First use downloads the agent tools and may take several minutes.', 'results': [], 'agents': [x[0] for x in prepared]}
            self.update()
            threading.Thread(target=self.execute, args=(prepared,), daemon=True).start()
            return self.snapshot()

    def execute(self, prepared):
        container = None
        try:
            # Always build to honor runner changes; Docker caches unchanged layers. No credentials in build.
            build = subprocess.run(['docker', 'build', '-t', IMAGE, '-f', 'scripts/local-runner.Dockerfile', '.'], cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=900)
            if build.returncode:
                raise RuntimeError('Could not prepare the runner image. Check Docker and network access, then retry.')
            results = []
            for agent, model, key, value in prepared:
                self.update(status='running', message=f'Running {agent} on the included sample task…')
                container = 'basis-' + uuid.uuid4().hex
                self.update(container=container)
                env = {k: v for k, v in os.environ.items() if k not in ALLOWED}
                env[key] = value
                command = ['docker', 'run', '--rm', '--name', container, '--read-only', '--cap-drop=ALL', '--security-opt=no-new-privileges', '--pids-limit=256', '--memory=2g', '--cpus=2', '--tmpfs', '/work:rw,nosuid,size=64m,uid=1000,gid=1000', '--tmpfs', '/tmp:rw,nosuid,size=128m', '--tmpfs', '/home/node:rw,nosuid,size=256m,uid=1000,gid=1000', '-e', key, IMAGE, agent, model]
                run = subprocess.run(command, env=env, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, timeout=750)
                if run.returncode:
                    raise RuntimeError(f'The {agent} container could not complete. Check Docker resources and retry.')
                report = json.loads(run.stdout)
                # Persist only the trusted runner's summary, never agent output or credentials.
                if report.get('type') != 'basis-agent-evaluation' or report.get('candidate') != agent:
                    raise RuntimeError('The runner returned an invalid summary.')
                results.append(report)
                self.update(results=results, container=None)
                container = None
            self.update(status='completed', message='Tests finished. Review the automated checks below; human review is still required.')
        except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as error:
            message = str(error) if isinstance(error, RuntimeError) else 'The local runner stopped or timed out. Check Docker and retry.'
            self.update(status='failed', message=message)
        finally:
            if container:
                self.remove_container(container)
            prepared.clear()


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
            if self.headers.get('Content-Type', '').split(';')[0] != 'application/json' or not 1 <= length <= 16000:
                raise ValueError('Expected a small JSON request.')
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
                self._json(200, {'configured': configured, 'credentialError': issue, 'dockerReady': docker_ready(), 'job': self.runner.snapshot()}); return
            if self.path == '/api/local/job':
                self._json(200, {'job': self.runner.snapshot()}); return
            if self.path == '/api/local/credentials':
                name, value = item.get('secret'), item.get('value')
                if name not in ALLOWED or not isinstance(value, str) or not 8 <= len(value) <= 8000 or any(c in value for c in '\r\n\x00'):
                    raise ValueError('Choose a supported provider and enter a single-line key.')
                try:
                    vault().set_password('basis-local', name, value)
                except Exception:
                    self._json(503, {'error': 'Could not save to the OS credential store. Install local dependencies and unlock the store.'}); return
                self._json(200, {'saved': True, 'name': name}); return
            if self.path == '/api/local/run':
                self._json(202, {'job': self.runner.start(item.get('agents'), item.get('consent'))}); return
            self._json(404, {'error': 'Unknown route'})
        except (ValueError, TypeError, KeyError):
            self._json(400, {'error': 'Invalid request or run prerequisites. Check selected services, model identifiers, saved credentials, and Docker.'})
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
        runner.stop()
        server.server_close()

if __name__ == '__main__':
    main()
