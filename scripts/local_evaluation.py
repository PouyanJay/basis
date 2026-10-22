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
                    if re.fullmatch(r'basis-[a-f0-9]{32}', self.job.get('container') or ''):
                        self.remove_container(self.job['container'])
                    self.update(status='interrupted', message='The local companion stopped. Completed evidence is preserved.', container=None)
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
            self.update(status='stopped', message='Stopped. Completed attempts are preserved; remaining attempts were not run.')
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
            if not any(f"{r['taskIndex']}:{r['agent']}" == key for r in job['results']):
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
            for service in services:
                agent, model = service.get('id'), service.get('model', '')
                if model == 'Specify deployed model':
                    model = ''
                if not isinstance(model, str) or len(model) > 100 or model and not re.fullmatch(r'[\w./:-]+', model, re.ASCII):
                    raise ValueError('Set a valid model identifier in Set up.')
                key = self.required_key(agent, model)
                value = self.vault().get_password('basis-local', key)
                if not value:
                    raise ValueError(f'Configure {key} in Settings or Set up → Requirements.')
                service['model'] = model or 'CLI default (not pinned)'
                prepared.append((agent, model, key, value))
            timeout = plan.get('timeoutSeconds', 600)
            if type(timeout) is not int or not 30 <= timeout <= 1800:
                raise ValueError('Time limit must be 30–1800 seconds per attempt.')
            tasks = [{**t, 'sourceKind': 'team', 'suite': 'Team tasks'} for t in setup.get('tasks', [])]
            packs = plan.get('benchmarkPaths', [])
            if not isinstance(packs, list) or len(packs) > 5:
                raise ValueError('Choose at most five benchmark packs.')
            plan['benchmarks'] = []
            for index, path in enumerate(packs):
                pack = benchmark_pack(path)
                if any(p['name'] == pack['name'] for p in plan['benchmarks']):
                    raise ValueError('Use a unique name for each benchmark pack in this run.')
                plan['benchmarks'].append({k: v for k, v in pack.items() if k != 'tasks'})
                tasks.extend({**t, 'instanceId': t.get('id', str(n)), 'id': f'benchmark-{index}-{n}', 'sourceKind': 'benchmark', 'suite': pack['name'], 'revision': pack['revision']} for n, t in enumerate(pack['tasks']))
            if not 1 <= len(tasks) <= 100:
                raise ValueError('Define a task in Set up or add a benchmark pack (maximum 100 tasks).')
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
                plan.update(tasks=tasks, services=services, timeoutSeconds=timeout, schemaVersion=1)
                write_json(directory / 'plan.json', plan)
            except Exception:
                shutil.rmtree(directory)
                raise
            self.cancel.clear()
            self.job = {'id': run_id, 'status': 'preparing', 'startedAt': time.time(), 'plan': plan,
                        'folder': str(directory), 'results': [], 'total': len(tasks) * len(services),
                        'message': 'Preparing isolated runner tools. First use can take several minutes.'}
            self.update()
            self.worker = threading.Thread(target=self.execute, args=(prepared,), daemon=True)
            self.worker.start()
            return self.snapshot()

    def command(self, args, timeout, env=None):
        if self.cancel.is_set():
            raise InterruptedError()
        # Do not persist untrusted process output, which may contain provider credentials.
        with self.lock:
            if self.cancel.is_set():
                raise InterruptedError()
            self.process = subprocess.Popen(args, cwd=self.root, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
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
            with self.lock:
                self.process = None

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

    def execute(self, prepared):
        try:
            if self.command(['docker', 'build', '-t', 'basis-local-runner:v2', '-f', 'scripts/local-runner.Dockerfile', '.'], 900):
                raise RuntimeError('Could not build the runner. Check Docker and network connectivity.')
            plan = self.job['plan']
            directory = Path(self.job['folder'])
            for task in plan['tasks']:
                for agent, model, key, value in prepared:
                    if self.cancel.is_set():
                        raise InterruptedError()
                    work = directory / 'attempts' / str(task['index']) / agent
                    shutil.copytree(directory / 'inputs' / str(task['index']) / 'source', work)
                    checks = directory / 'inputs' / str(task['index']) / 'checks'
                    prompt = {'task': task['name'], 'acceptance': task['acceptance'], 'teamContext': plan['setup'].get('org', {}),
                              'requirements': plan['setup'].get('gates', []), 'instructions': 'Work in /work. Implement the task. Do not alter /checks. Policy requirements need human evidence and cannot be certified by this run.'}
                    # Pass the prompt as an argument, never a file that an agent can replace before launch.
                    self.update(status='running', message=f"Running {agent}: {task['name']}")
                    started = time.time()
                    result = {'agent': agent, 'model': model or 'CLI default (not pinned)', 'taskIndex': task['index'], 'task': task['name'],
                              'sourceKind': task['sourceKind'], 'suite': task['suite'], 'folder': str(work), 'accepted': None,
                              'checkPassed': None, 'usageCost': None, 'humanMinutes': None}
                    try:
                        code = self.container(work, checks, ['agent', agent, model, json.dumps(prompt)], plan['timeoutSeconds'], key, value)
                        result.update(status='completed' if code == 0 else 'error', agentExitCode=code)
                        if code == 0 and task.get('checkCommand'):
                            self.update(message=f"Checking {agent}: {task['name']}")
                            check = self.container(work, checks, ['check', task['checkCommand']], plan['timeoutSeconds'])
                            result.update(checkPassed=check == 0, checkExitCode=check)
                    except subprocess.TimeoutExpired:
                        result['status'] = 'timeout'
                    except InterruptedError:
                        result['status'] = 'stopped'
                    result['durationSeconds'] = round(time.time() - started, 2)
                    self.update(results=[*self.job['results'], result])
                    if self.cancel.is_set():
                        raise InterruptedError()
            failed = any(r['status'] != 'completed' for r in self.job['results'])
            self.update(status='partial' if failed else 'completed', finishedAt=time.time(), message='Evaluation finished. Review checks and acceptance criteria; policy requirements still need documentary evidence.')
        except InterruptedError:
            self.update(status='stopped', message='Stopped. Completed attempts are preserved.')
        except Exception:
            self.update(status='failed', message='Runner failed. Check Docker resources, source permissions, and network availability. Completed attempts are preserved.')
        finally:
            prepared.clear()
