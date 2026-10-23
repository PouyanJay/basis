"""Durable local evaluation plans and isolated per-task execution."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import threading
import time
import uuid
from integrated_swebench import LiteBenchmark, clean_env

ACTIVE = ('preparing', 'running')
EXCLUDED = {'.git', '.env', '.ssh', '.aws', 'node_modules', '__pycache__', '.venv', '.DS_Store'}


def write_json(path, value):
    temp = path.with_suffix('.tmp')
    with open(os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), 'w') as stream:
        json.dump(value, stream, indent=2)
    temp.replace(path)


def copy_source(source, destination):
    """Copy regular source files only. Never expose the original to an agent."""
    destination.mkdir(parents=True, exist_ok=True)
    if not source:
        return hashlib.sha256(b'').hexdigest()
    root = Path(source).expanduser()
    if not root.is_absolute() or not root.is_dir() or root.is_symlink():
        raise ValueError('Source and check folders must be existing absolute directories.')
    total, count, digest = 0, 0, hashlib.sha256()
    for base, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d not in EXCLUDED and not Path(base, d).is_symlink())
        for name in sorted(files):
            p = Path(base, name)
            if name in EXCLUDED or name.startswith('.env.') or p.suffix in {'.pem', '.key', '.p12'}:
                continue
            if p.is_symlink() or not p.is_file():
                raise ValueError('Source folders must not contain symlinks or special files.')
            total += p.stat().st_size
            count += 1
            if total > 100 * 1024 * 1024 or count > 10000:
                raise ValueError('Source snapshot exceeds 100 MB or 10,000 files. Use a smaller source folder.')
            relative = p.relative_to(root)
            out = destination / relative
            out.parent.mkdir(parents=True, exist_ok=True)
            data = p.read_bytes()
            out.write_bytes(data)
            out.chmod(0o755 if p.stat().st_mode & 0o111 else 0o644)
            digest.update(str(relative).encode() + b'\0' + data)
    return digest.hexdigest()


def benchmark_pack(filename):
    if not isinstance(filename, str) or not filename:
        raise ValueError('Enter the absolute path to a benchmark pack.')
    path = Path(filename).expanduser()
    if not path.is_absolute() or not path.is_file() or path.stat().st_size > 200000:
        raise ValueError('Choose an absolute path to a benchmark pack JSON file (under 200 KB).')
    pack = json.loads(path.read_text())
    if not isinstance(pack, dict):
        raise ValueError('Benchmark pack must be a JSON object.')
    if pack.get('schemaVersion') != 1 or not isinstance(pack.get('name'), str) or not pack.get('revision'):
        raise ValueError('Benchmark pack needs schemaVersion 1, name, revision, and tasks.')
    tasks = pack.get('tasks')
    if not isinstance(tasks, list) or not 1 <= len(tasks) <= 50:
        raise ValueError('A benchmark pack must contain 1–50 tasks.')
    for task in tasks:
        if not isinstance(task, dict) or not task.get('checkCommand') or not task.get('checksPath'):
            raise ValueError('Every benchmark task needs checkCommand and checksPath for independent checks.')
        for field in ('sourcePath', 'checksPath'):
            if task.get(field) and not isinstance(task[field], str):
                raise ValueError('Benchmark source and checks paths must be text.')
            if task.get(field):
                task[field] = str((path.parent / task[field]).resolve())
    return {'name': pack['name'], 'revision': str(pack['revision']), 'source': pack.get('source', ''), 'tasks': tasks,
            'manifestDigest': hashlib.sha256(path.read_bytes()).hexdigest()}


class EvaluationRunner:
    def __init__(self, folder, root, vault, docker_ready, required_key, allowed):
        self.folder = Path(folder or Path.home() / '.local/share/basis')
        self.folder.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.root, self.vault, self.docker_ready, self.required_key, self.allowed = root, vault, docker_ready, required_key, allowed
        self.lite = LiteBenchmark(self.folder, root)
        self.lock = threading.RLock()
        self.cancel = threading.Event()
        self.image = 'basis-local-runner:v2'
        self.process = None
        self.job = None
        self.file = self.folder / 'latest-run.json'
        if self.file.exists():
            try:
                self.job = json.loads(self.file.read_text())
                if self.job['status'] in ACTIVE:
                    if re.fullmatch(r'(?:basis-[a-f0-9]{32}|sweb\.eval\.[a-z0-9_.-]+\.basis-[a-f0-9]{32}-[a-z0-9-]+)', self.job.get('container') or ''):
                        self.remove_container(self.job['container'])
                    self.update(status='interrupted', finishedAt=time.time(), message='The local companion stopped. Completed evidence is preserved.', container=None)
            except (ValueError, KeyError):
                self.job = None

    @staticmethod
    def remove_container(name):
        try:
            subprocess.run(['docker', 'rm', '-f', name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
        except (OSError, subprocess.TimeoutExpired):
            pass

    def snapshot(self):
        with self.lock:
            return json.loads(json.dumps(self.job))

    def update(self, **values):
        with self.lock:
            self.job.update(values)
            write_json(self.file, self.job)
            directory = self.folder / 'evaluations' / self.job['id']
            if directory.is_dir():
                write_json(directory / 'result.json', self.job)

    def history(self):
        rows = []
        for path in sorted((self.folder / 'evaluations').glob('*/result.json'), reverse=True):
            try:
                rows.append(json.loads(path.read_text()))
            except (OSError, ValueError):
                continue
        return sorted(rows, key=lambda row: row.get('startedAt', 0), reverse=True)

    def stop(self):
        with self.lock:
            if not self.job or self.job['status'] not in ACTIVE:
                return self.snapshot()
            self.cancel.set()
            if self.process:
                self.process.terminate()
            container = self.job.get('container')
            self.update(status='stopped', finishedAt=time.time(), message='Stopped. Completed attempts are preserved; remaining attempts were not run.')
        if container:
            self.remove_container(container)
        return self.snapshot()

    def review(self, run_id, key, review):
        if not isinstance(run_id, str) or not re.fullmatch(r'[a-f0-9]{32}', run_id):
            raise ValueError('Invalid evaluation ID.')
        if not isinstance(review, dict) or type(review.get('accepted')) is not bool or not isinstance(review.get('notes'), str) or not review['notes'].strip():
            raise ValueError('Acceptance and review evidence are required.')
        for field in ('humanMinutes', 'usageCost'):
            value = review.get(field)
            if value is not None and (type(value) not in (int, float) or not 0 <= value < 1e9):
                raise ValueError('Cost and human effort must be nonnegative numbers or left blank.')
        with self.lock:
            path = self.folder / 'evaluations' / run_id / 'result.json'
            job = json.loads(path.read_text())
            if not any(f"{r['taskIndex']}:{r.get('candidateId', r['agent'])}" == key for r in job['results']):
                raise ValueError('The attempt does not exist.')
            job.setdefault('reviews', {})[key] = {k: review.get(k) for k in ('accepted', 'notes', 'humanMinutes', 'usageCost')}
            job['reviews'][key]['reviewedAt'] = time.time()
            write_json(path, job)
            if self.job and self.job['id'] == run_id:
                self.job['reviews'] = job['reviews']
                self.update()
        return job

    def start(self, plan, consent):
        if consent is not True:
            raise ValueError('Confirm provider usage and permission to send the selected source and task context.')
        with self.lock:
            if (self.job and self.job['status'] in ACTIVE) or self.process or (getattr(self, 'worker', None) and self.worker.is_alive()):
                raise ValueError('An evaluation is already running or stopping.')
            if not isinstance(plan, dict) or not isinstance(plan.get('setup'), dict):
                raise ValueError('Save your setup before running an evaluation.')
            plan = json.loads(json.dumps(plan))
            setup = plan['setup']
            if not isinstance(setup.get('platforms'), list) or not all(isinstance(p, dict) and isinstance(p.get('id'), str) for p in setup['platforms']):
                raise ValueError('Select valid services in Set up.')
            if not isinstance(setup.get('tasks', []), list) or not all(isinstance(t, dict) for t in setup.get('tasks', [])):
                raise ValueError('Tasks must be a list of task definitions.')
            services = [p for p in setup['platforms'] if p.get('enabled')]
            if not 1 <= len(services) <= 4 or len({p.get('id') for p in services}) != len(services):
                raise ValueError('Choose one to four distinct supported services in Set up.')
            prepared = []
            candidates = []
            for service in services:
                agent = service['id']
                models = service.get('models', [service.get('model', '')])
                if not isinstance(models, list) or not 1 <= len(models) <= 10 or not all(isinstance(m, str) for m in models) or len(set(models)) != len(models):
                    raise ValueError('Choose one to ten distinct models per service.')
                if 'models' in service and any(not m or m.startswith('Specify ') for m in models):
                    raise ValueError('Choose an available model for each selected service.')
                for model in models:
                    if model == 'Specify deployed model':
                        model = ''
                    if len(model) > 100 or model and not re.fullmatch(r'[\w./:-]+', model, re.ASCII):
                        raise ValueError('Set a valid model identifier in Set up.')
                    key = self.required_key(agent, model)
                    value = self.vault().get_password('basis-local', key)
                    if not value:
                        raise ValueError(f'Configure {key} in Settings or Set up → Services & criteria.')
                    candidate_id = agent if len(models) == 1 else agent + '-' + hashlib.sha256(model.encode()).hexdigest()[:16]
                    candidates.append({**service, 'model': model or 'CLI default (not pinned)', 'candidateId': candidate_id})
                    prepared.append((agent, model, key, value))
            services = candidates
            timeout = plan.get('timeoutSeconds', 600)
            if type(timeout) is not int or not 30 <= timeout <= 1800:
                raise ValueError('Time limit must be 30–1800 seconds per attempt.')
            tasks = [{**{k: v for k, v in t.items() if k not in ('grader', 'instancePath', 'imageTag', 'imageDigest')}, 'sourceKind': 'team', 'suite': 'Team tasks'} for t in setup.get('tasks', [])]
            packs = plan.get('benchmarkPaths', [])
            if not isinstance(packs, list) or len(packs) > 5:
                raise ValueError('Choose at most five benchmark packs.')
            plan['benchmarks'] = []
            for index, path in enumerate(packs):
                pack = benchmark_pack(path)
                if any(p['name'] == pack['name'] for p in plan['benchmarks']):
                    raise ValueError('Use a unique name for each benchmark pack in this run.')
                plan['benchmarks'].append({k: v for k, v in pack.items() if k != 'tasks'})
                tasks.extend({**{k: v for k, v in t.items() if k not in ('grader', 'instancePath', 'imageTag', 'imageDigest')}, 'instanceId': t.get('id', str(n)), 'id': f'benchmark-{index}-{n}', 'sourceKind': 'benchmark', 'suite': pack['name'], 'revision': pack['revision']} for n, t in enumerate(pack['tasks']))
            suites = plan.get('integratedBenchmarks', [])
            if not isinstance(suites, list) or len(suites) > 1 or any(not isinstance(b, dict) or b.get('id') != 'swebench-lite' for b in suites):
                raise ValueError('Only SWE-bench Lite is currently available for integrated execution.')
            for suite in suites:
                pack = self.lite.selection(suite.get('count'))
                plan['benchmarks'].append({k: v for k, v in pack.items() if k != 'tasks'})
                tasks.extend({**t, 'instanceId': t['id'], 'sourceKind': 'benchmark', 'suite': pack['name'], 'revision': pack['revision'], 'harness': pack['harness']} for t in pack['tasks'])
            if not 1 <= len(tasks) <= 400:
                raise ValueError('Define a task in Set up or add a benchmark pack (maximum 400 tasks).')
            if not self.docker_ready():
                raise ValueError('Start Docker before running the evaluation.')
            run_id = uuid.uuid4().hex
            directory = self.folder / 'evaluations' / run_id
            directory.mkdir(parents=True, mode=0o700)
            try:
                for index, task in enumerate(tasks):
                    for field in ('name', 'acceptance'):
                        if not isinstance(task.get(field), str) or not task[field].strip():
                            raise ValueError('Every task needs a name and acceptance criteria.')
                    for field in ('sourcePath', 'checksPath', 'checkCommand'):
                        if not isinstance(task.get(field, ''), str):
                            raise ValueError('Task source, checks, and command must be text.')
                    if task.get('checkCommand') and not task.get('checksPath'):
                        raise ValueError('A check command needs an independent checks folder, mounted read-only at /checks.')
                    task['index'] = index
                    for field in ('sourcePath', 'checksPath'):
                        if task.get(field):
                            source = Path(task[field]).expanduser().resolve()
                            if ',' in str(source) or source == self.folder.resolve() or source in self.folder.resolve().parents:
                                raise ValueError('Use a project folder outside the Basis run storage, without commas in its path.')
                    base = directory / 'inputs' / str(index)
                    task['sourceDigest'] = copy_source(task.get('sourcePath'), base / 'source')
                    task['checksDigest'] = copy_source(task.get('checksPath'), base / 'checks')
                    if task.get('grader') == 'swebench-lite':
                        shutil.copyfile(task['instancePath'], base / 'instance.json')
                        task['checksDigest'] = hashlib.sha256((base / 'instance.json').read_bytes()).hexdigest()
                        task.pop('instancePath')
                plan.update(tasks=tasks, services=services, timeoutSeconds=timeout, schemaVersion=1)
                write_json(directory / 'plan.json', plan)
            except Exception:
                shutil.rmtree(directory)
                raise
            self.cancel.clear()
            self.job = {'id': run_id, 'status': 'preparing', 'startedAt': time.time(), 'plan': plan,
                        'folder': str(directory), 'results': [], 'total': len(tasks) * len(services),
                        'phase': 'prepare', 'activity': [],
                        'message': 'Preparing isolated runner tools. First use can take several minutes.'}
            self.update()
            self.worker = threading.Thread(target=self.execute, args=(prepared,), daemon=True)
            self.worker.start()
            return self.snapshot()

    def output(self, line):
        # Render only public Claude messages and tool names, never thinking blocks
        # or the raw initialization payload (which can include environment data).
        if getattr(self, '_stream', '').split('-')[0] == 'claude' and self.job.get('phase') == 'agent' and line.lstrip().startswith('{'):
            try:
                event = json.loads(line)
                if event.get('type') == 'assistant':
                    parts = event.get('message', {}).get('content', [])
                    line = ' | '.join(str(p.get('text', '')) if p.get('type') == 'text' else 'Tool: ' + str(p.get('name', '')) for p in parts if p.get('type') in ('text', 'tool_use'))
                elif event.get('type') == 'result':
                    line = str(event.get('result') or event.get('subtype') or 'Agent finished')
                elif event.get('type') == 'system' and event.get('subtype') == 'init':
                    line = 'Claude Code connected'
                else:
                    return
            except (ValueError, AttributeError, TypeError):
                return
        # Redact before truncation, storage, or exposure to the browser.
        line = re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]', '', line)
        for secret in getattr(self, '_secrets', []):
            if secret:
                line = line.replace(secret, '[REDACTED]')
        line = re.sub(r'(?i)(bearer\s+|(?:api[_-]?key|authorization)\s*[:=]\s*)\S+', r'\1[REDACTED]', line)
        line = re.sub(r'sk-[A-Za-z0-9_-]+', '[REDACTED]', line)
        line = ''.join(c for c in line if c >= ' ' or c == '\t')
        if not line.strip():
            return
        with self.lock:
            entry = {'time': time.time(), 'stream': getattr(self, '_stream', 'setup'), 'text': line[:2000]}
            activity = self.job.setdefault('activity', [])
            activity.append(entry)
            if len(activity) > 300:
                del activity[:-300]
                self.job['activityTruncated'] = True
            self.job['lastOutputAt'] = entry['time']
            if entry['time'] - getattr(self, '_last_activity_save', 0) >= 1:
                self._last_activity_save = entry['time']
                self.update()

    def read_output(self, pipe):
        # A bounded line buffer also handles secrets split across read chunks.
        buffer = bytearray()
        dropping = False
        while True:
            chunk = os.read(pipe.fileno(), 4096)
            if not chunk:
                break
            for byte in chunk:
                if byte in (10, 13):
                    if buffer and not dropping:
                        self.output(buffer.decode('utf-8', errors='replace'))
                    buffer.clear()
                    dropping = False
                elif not dropping:
                    buffer.append(byte)
                    if len(buffer) > 32768:
                        buffer.clear()
                        dropping = True
                        self.output('[Oversized output line omitted]')
        if buffer and not dropping:
            self.output(buffer.decode('utf-8', errors='replace'))

    def command(self, args, timeout, env=None, cwd=None):
        if self.cancel.is_set():
            raise InterruptedError()
        with self.lock:
            if self.cancel.is_set():
                raise InterruptedError()
            self.process = subprocess.Popen(args, cwd=cwd or self.root, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            reader = threading.Thread(target=self.read_output, args=(self.process.stdout,), daemon=True)
            reader.start()
        try:
            code = self.process.wait(timeout=timeout)
            if self.cancel.is_set():
                raise InterruptedError()
            return code
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait()
            raise
        finally:
            reader.join(timeout=2)
            if not reader.is_alive():
                self.process.stdout.close()
            with self.lock:
                self.process = None
                self.update()

    def container(self, work, checks, args, timeout, key=None, value=None):
        name = 'basis-' + uuid.uuid4().hex
        self.update(container=name)
        uid, gid = (os.getuid(), os.getgid()) if hasattr(os, 'getuid') else (1000, 1000)
        env = {k: v for k, v in os.environ.items() if k not in self.allowed}
        command = ['docker', 'run', '--rm', '--name', name, '--read-only', '--cap-drop=ALL', '--security-opt=no-new-privileges',
                   '--pids-limit=256', '--memory=2g', '--cpus=2', '--user', f'{uid}:{gid}',
                   '--tmpfs', '/tmp:rw,nosuid,size=256m', '--tmpfs', f'/home/node:rw,nosuid,size=256m,uid={uid},gid={gid}',
                   '--mount', f'type=bind,source={work},target=/work']
        if key:
            env[key] = value
            command += ['-e', key]
        else:
            command += ['--network=none', '--mount', f'type=bind,source={checks},target=/checks,readonly']
        command += [self.image, *args]
        try:
            return self.command(command, timeout, env)
        finally:
            self.remove_container(name)
            self.update(container=None)

    def git(self, work, *args):
        # The agent never receives the trusted git directory or user git config.
        gitdir = work.parent / (work.name + '-patch-index')
        env = {**{k:v for k,v in clean_env().items() if not k.startswith('GIT_')}, 'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': os.devnull,
               'GIT_CONFIG_SYSTEM': os.devnull, 'GIT_ATTR_NOSYSTEM': '1'}
        return subprocess.run(['git', '--no-pager', '--git-dir=' + str(gitdir), '--work-tree=' + str(work),
                               '-c', 'core.hooksPath=' + os.devnull, '-c', 'core.attributesFile=' + os.devnull,
                               '-c', 'core.autocrlf=false', *args], env=env, cwd=work,
                              capture_output=True, check=True, timeout=60)

    def prepare_patch(self, work):
        self.git(work, 'init', '--template=')
        self.git(work, 'add', '-A', '--', '.')
        tree = self.git(work, 'write-tree').stdout.decode().strip()
        (work.parent / (work.name + '-base-tree')).write_text(tree)

    def grade_lite(self, task, work, timeout):
        self.output('Grading with the pinned SWE-bench harness')
        self.git(work, 'add', '-A', '--', '.')
        tree = (work.parent / (work.name + '-base-tree')).read_text()
        patch = self.git(work, 'diff', '--cached', '--binary', '--no-ext-diff', '--no-textconv', tree, '--', '.').stdout
        evidence = work.parent / (work.name + '-grading')
        evidence.mkdir()
        (evidence / 'prediction.patch').write_bytes(patch)
        if not patch.strip():
            report = evidence / 'report.json'
            write_json(report, {task['instanceId']: {'resolved': False, 'reason': 'No changes produced', 'graded': False}})
            return {'checkPassed': False, 'checkExitCode': None, 'gradingReport': str(report), 'gradingReason': 'No changes produced', 'gradingSkipped': True}
        instance = json.loads((Path(self.job['folder']) / 'inputs' / str(task['index']) / 'instance.json').read_text())
        run_id = 'basis-' + self.job['id'] + '-' + str(task['index']) + '-' + work.name
        name = 'sweb.eval.' + task['instanceId'].lower() + '.' + run_id
        report = evidence / 'report.json'
        config = {'instance': instance, 'imageTag': task['imageTag'], 'imageDigest': task['imageDigest'], 'patch': str(evidence / 'prediction.patch'),
                  'runId': run_id, 'timeout': timeout, 'report': str(report)}
        write_json(evidence / 'config.json', config)
        self.update(container=name)
        try:
            code = self.command([str(self.lite.python), str(self.root / 'scripts/swebench_helper.py'), 'grade', str(evidence / 'config.json')],
                                timeout + 120, clean_env(), cwd=evidence)
            if code == 124:
                raise subprocess.TimeoutExpired('Official SWE-bench checks', timeout)
            if code or not report.exists():
                raise RuntimeError('Official grading failed')
            grade = json.loads(report.read_text()).get(task['instanceId'], {})
            if type(grade.get('resolved')) is not bool:
                raise RuntimeError('Official report is missing a resolved outcome')
            return {'checkPassed': grade['resolved'], 'checkExitCode': code, 'gradingReport': str(report),
                    'harness': 'swebench==' + task['harness'], 'datasetRevision': task['revision'], 'imageDigest': task['imageDigest']}
        finally:
            self.remove_container(name)
            self.update(container=None)

    def execute(self, prepared):
        self._secrets = [row[3] for row in prepared]
        self._stream = 'setup'
        try:
            for digest in {t['imageDigest'] for t in self.job['plan']['tasks'] if t.get('grader') == 'swebench-lite'}:
                if self.command(['docker', 'image', 'inspect', '--format', '{{.Id}}', digest], 30, clean_env()):
                    self.output('Benchmark image is missing. Remove and add SWE-bench Lite again before running.')
                    raise RuntimeError('Prepared benchmark image is missing')
            if self.command(['docker', 'build', '--progress=plain', '-t', 'basis-local-runner:v2', '-f', 'scripts/local-runner.Dockerfile', '.'], 900):
                raise RuntimeError('Could not build the runner. Check Docker and network connectivity.')
            plan = self.job['plan']
            directory = Path(self.job['folder'])
            for task in plan['tasks']:
                for agent, model, key, value in prepared:
                    if self.cancel.is_set():
                        raise InterruptedError()
                    candidate = next((p for p in plan['services'] if p['id'] == agent and p['model'] == (model or 'CLI default (not pinned)')), {})
                    candidate_id = candidate.get('candidateId', agent)
                    work = directory / 'attempts' / str(task['index']) / candidate_id
                    shutil.copytree(directory / 'inputs' / str(task['index']) / 'source', work)
                    checks = directory / 'inputs' / str(task['index']) / 'checks'
                    prompt = {'task': task['name'], 'acceptance': task['acceptance'], 'teamContext': plan['setup'].get('org', {}),
                              'requirements': plan['setup'].get('gates', []), 'instructions': 'Work in /work. Implement the task. Do not alter /checks. Policy requirements need human evidence and cannot be certified by this run.'}
                    if task.get('grader') == 'swebench-lite':
                        prompt['instructions'] += ' Fix the repository issue without changing tests to manufacture success. Do not retrieve reference solutions or hidden evaluation tests.'
                    # Pass the prompt as an argument, never a file that an agent can replace before launch.
                    self._stream = candidate_id
                    self.output(f"Starting task: {task['name']}")
                    self.update(status='running', phase='agent', currentAgent=agent, currentCandidate=candidate_id, currentTask=task['index'], message=f"Running {agent} · {model or 'default'}: {task['name']}")
                    started = time.time()
                    result = {'agent': agent, 'candidateId': candidate_id, 'model': model or 'CLI default (not pinned)', 'taskIndex': task['index'], 'task': task['name'],
                              'sourceKind': task['sourceKind'], 'suite': task['suite'], 'folder': str(work), 'accepted': None,
                              'checkPassed': None, 'usageCost': None, 'humanMinutes': None}
                    try:
                        if task.get('grader') == 'swebench-lite':
                            self.prepare_patch(work)
                        code = self.container(work, checks, ['agent', agent, model, json.dumps(prompt)], plan['timeoutSeconds'], key, value)
                        result.update(status='completed' if code == 0 else 'error', agentExitCode=code)
                        if code == 0 and task.get('grader') == 'swebench-lite':
                            self.update(phase='check', message=f"Grading {agent} · {model}: {task['name']}")
                            result.update(self.grade_lite(task, work, plan['timeoutSeconds']))
                        elif code == 0 and task.get('checkCommand'):
                            self.output('Running independent checks')
                            self.update(phase='check', message=f"Checking {agent} · {model or 'default'}: {task['name']}")
                            check = self.container(work, checks, ['check', task['checkCommand']], plan['timeoutSeconds'])
                            result.update(checkPassed=check == 0, checkExitCode=check)
                    except subprocess.TimeoutExpired:
                        result['status'] = 'timeout'
                    except InterruptedError:
                        result['status'] = 'stopped'
                    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError):
                        result.update(status='error', error='Benchmark grading failed. See this attempt’s activity and grading logs.')
                    self.output(f"Attempt {result['status']}; checks: {result.get('checkPassed')}")
                    result['durationSeconds'] = round(time.time() - started, 2)
                    self.update(results=[*self.job['results'], result])
                    if self.cancel.is_set():
                        raise InterruptedError()
            failed = any(r['status'] != 'completed' for r in self.job['results'])
            self.update(status='partial' if failed else 'completed', finishedAt=time.time(), message='Evaluation finished. Review checks and acceptance criteria; policy requirements still need documentary evidence.')
        except InterruptedError:
            self.update(status='stopped', finishedAt=time.time(), message='Stopped. Completed attempts are preserved.')
        except Exception:
            self.update(status='failed', finishedAt=time.time(), message='Runner failed. Check Docker resources, source permissions, and network availability. Completed attempts are preserved.')
        finally:
            prepared.clear()
            self._secrets = []
