"""Read authenticated provider catalogs; never supply a fallback model list."""
import datetime
import json
import os
import re
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import uuid

PROVIDERS = {'openai': 'OPENAI_API_KEY', 'anthropic': 'ANTHROPIC_API_KEY', 'cursor': 'CURSOR_API_KEY'}
ID = re.compile(r'[\w./:-]{1,100}', re.ASCII)

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def request_json(url, headers):
    try:
        with urllib.request.build_opener(NoRedirect).open(urllib.request.Request(url, headers=headers), timeout=20) as response:
            raw = response.read(2_000_001)
            if len(raw) > 2_000_000:
                raise RuntimeError('Provider returned an oversized model list.')
            return json.loads(raw)
    except urllib.error.HTTPError as error:
        if error.code in (401, 403):
            raise RuntimeError('The provider rejected this key or its model-list permission. Replace the key and retry.') from None
        if error.code == 429:
            raise RuntimeError('Provider rate limit reached. Try refreshing shortly.') from None
        raise RuntimeError('Provider model discovery is unavailable. Try refreshing shortly.') from None
    except (OSError, ValueError):
        raise RuntimeError('Could not read the provider model list. Check your connection and retry.') from None


def cursor_models(key):
    # Use the same CLI as execution, without passing a secret in command arguments.
    executable = shutil.which('cursor-agent')
    env = {'PATH': os.environ.get('PATH', ''), 'CURSOR_API_KEY': key, 'NO_COLOR': '1', 'TERM': 'dumb'}
    container = 'basis-models-' + uuid.uuid4().hex
    with tempfile.TemporaryDirectory(prefix='basis-models-') as folder:
        env['HOME'] = folder
        if executable:
            command = [executable, '--list-models']
        else:
            env = {**os.environ, 'CURSOR_API_KEY': key}
            command = ['docker', 'run', '--rm', '--pull=never', '--name', container, '--read-only', '--cap-drop=ALL', '--security-opt=no-new-privileges', '--memory=512m', '--cpus=1', '--tmpfs', '/home/node:uid=1000,gid=1000', '--tmpfs', '/tmp', '-e', 'HOME=/home/node', '-e', 'CURSOR_API_KEY', '-e', 'NO_COLOR=1', '--entrypoint', 'cursor-agent', 'basis-local-runner:v2', '--list-models']
        try:
            result = subprocess.run(command, cwd=folder, env=env, capture_output=True, text=True, timeout=40)
        except subprocess.TimeoutExpired:
            if not executable:
                subprocess.run(['docker', 'rm', '-f', container], capture_output=True, timeout=10)
            raise RuntimeError('Cursor model discovery timed out. Retry after checking your connection.') from None
        except OSError:
            raise RuntimeError('Install Cursor CLI or start Docker with the Basis runner image to discover Cursor models.') from None
    if result.returncode:
        raise RuntimeError('Cursor could not list models. Check your key, Cursor CLI installation, or local Docker runner.')
    return parse_cursor_models(result.stdout)


def parse_cursor_models(output):
    output = re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]', '', output)
    rows, listing = [], False
    for line in output.splitlines():
        line = line.strip()
        if line == 'Available models':
            listing = True
            continue
        if not listing or not line:
            continue
        if line.startswith('Tip:'):
            break
        line = re.sub(r' \((?:current|default|current, default)\)$', '', line)
        identifier, _, label = line.partition(' - ')
        if ID.fullmatch(identifier):
            rows.append({'id': identifier, 'name': label or identifier})
    return rows


def discover(service, provider, store):
    if service == 'opencode':
        if provider not in ('openai', 'anthropic'):
            raise ValueError('Select an OpenCode provider first.')
    else:
        provider = {'codex': 'openai', 'claude': 'anthropic', 'cursor': 'cursor'}.get(service)
    if provider not in PROVIDERS:
        raise ValueError('Model discovery is not supported for this service.')
    try:
        key = store.get_password('basis-local', PROVIDERS[provider])
    except Exception:
        raise RuntimeError('Unlock your OS credential store and retry.') from None
    if not key:
        raise ValueError('Save the provider API key before fetching models.')
    if provider == 'cursor':
        models, source = cursor_models(key), 'Cursor CLI'
    else:
        source = 'https://api.openai.com/v1/models' if provider == 'openai' else 'https://api.anthropic.com/v1/models'
        headers = {'Authorization': 'Bearer ' + key} if provider == 'openai' else {'x-api-key': key, 'anthropic-version': '2023-06-01'}
        models, after, seen = [], '', set()
        for _ in range(100):
            url = source + ('?' + urllib.parse.urlencode({'limit': 1000, **({'after_id': after} if after else {})}) if provider == 'anthropic' else '')
            data = request_json(url, headers)
            if not isinstance(data, dict) or not isinstance(data.get('data'), list):
                raise RuntimeError('Provider returned an unreadable model list.')
            for row in data['data']:
                if isinstance(row, dict) and isinstance(row.get('id'), str) and ID.fullmatch(row['id']):
                    models.append({'id': row['id'], 'name': row.get('display_name') or row['id']})
            if not data.get('has_more'):
                break
            after = data.get('last_id')
            if provider != 'anthropic' or not isinstance(after, str) or not after or after in seen:
                raise RuntimeError('Provider returned incomplete model pagination. Retry discovery.')
            seen.add(after)
        else:
            raise RuntimeError('Provider model pagination limit exceeded.')
    unique = {}
    for row in models:
        identifier = (provider + '/' if service == 'opencode' else '') + row['id']
        if ID.fullmatch(identifier):
            unique[identifier] = {'id': identifier, 'name': str(row['name'])[:160]}
    return {'models': list(unique.values()), 'source': source, 'fetchedAt': datetime.datetime.now(datetime.timezone.utc).isoformat()}
