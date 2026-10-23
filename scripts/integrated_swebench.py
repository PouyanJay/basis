"""Managed, cached SWE-bench Lite preparation. No provider calls during setup."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import random
import shutil
import subprocess
import sys
import tarfile
import threading
import time
import urllib.request
import uuid
import re

REVISION = '6ec7bb89b9342f664a54a6e0a6ea6501d3437cc2'
HARNESS = '3.0.15'
DATASET_SHA256 = '7a21f37b8bc179c7db5beeb14e88ac538ba283455c776e6b2535bbfb6e3551b4'
DATASET = 'princeton-nlp/SWE-bench_Lite'
ACTIVE = {'checking', 'downloading', 'preparing'}


def clean_env():
    return {k: v for k, v in os.environ.items() if not any(word in k.upper() for word in ('KEY', 'TOKEN', 'SECRET', 'PASSWORD'))}


def save(path, data):
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(data, indent=2))
    tmp.replace(path)


class LiteBenchmark:
    def __init__(self, folder, root):
        self.folder = Path(folder) / 'benchmarks' / ('swebench-lite-' + REVISION)
        self.folder.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.root = Path(root)
        self.lock = threading.RLock()
        self.cancel = threading.Event()
        self.process = None
        self.state = {'status': 'idle'}
        self.statefile = self.folder / 'preparation.json'
        if self.statefile.exists():
            try:
                self.state = json.loads(self.statefile.read_text())
                if self.state['status'] in ACTIVE:
                    self.remove_container(self.state.get('container'))
                    self.update(status='error', message='Preparation interrupted. Retry to continue.', container=None)
            except (ValueError, KeyError):
                self.state = {'status': 'idle'}

    @staticmethod
    def remove_container(name):
        if not isinstance(name, str) or not re.fullmatch(r'basis-prepare-[a-f0-9]{32}', name):
            return
        try:
            subprocess.run(['docker', 'rm', '-f', name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
        except (OSError, subprocess.TimeoutExpired):
            pass

    @property
    def python(self):
        return self.folder / 'venv' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')

    def snapshot(self):
        with self.lock:
            return json.loads(json.dumps(self.state))

    def update(self, **values):
        with self.lock:
            self.state.update(values, updatedAt=time.time())
            save(self.statefile, self.state)

    def start(self, count):
        if type(count) is not int or not 1 <= count <= 300:
            raise ValueError('Choose 1–300 SWE-bench Lite tasks.')
        with self.lock:
            if self.state['status'] in ACTIVE or getattr(self, 'worker', None) and self.worker.is_alive():
                return self.snapshot()
            self.cancel.clear()
            self.state = {'status': 'checking', 'count': count, 'completed': 0, 'message': 'Checking this computer', 'startedAt': time.time()}
            self.update()
            self.worker = threading.Thread(target=self.prepare, args=(count,), daemon=True)
            self.worker.start()
            return self.snapshot()

    def stop(self):
        with self.lock:
            if self.state['status'] not in ACTIVE:
                return self.snapshot()
            self.cancel.set()
            if self.process:
                self.process.terminate()
            container = self.state.get('container')
            self.update(status='cancelled', message='Preparation cancelled')
        self.remove_container(container)
        return self.snapshot()

    def command(self, args, timeout=1800, output=None):
        if self.cancel.is_set():
            raise InterruptedError()
        with open(self.folder / 'preparation.log', 'ab') as log:
            with self.lock:
                if self.cancel.is_set():
                    raise InterruptedError()
                self.process = subprocess.Popen([str(x) for x in args], stdout=output or log, stderr=log, env=clean_env())
            try:
                code = self.process.wait(timeout=timeout)
                if self.cancel.is_set():
                    raise InterruptedError()
                if code:
                    raise RuntimeError('Setup failed. Check Docker and network access, then retry.')
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
                raise RuntimeError('Setup timed out. Check Docker and network access, then retry.') from None
            finally:
                with self.lock:
                    self.process = None

    def prepare(self, count):
        try:
            try:
                info = subprocess.run(['docker', 'info', '--format', '{{json .}}'], capture_output=True, timeout=15, check=True)
                info = json.loads(info.stdout)
            except (OSError, ValueError, subprocess.SubprocessError):
                raise RuntimeError('Start Docker, then retry.') from None
            if info.get('MemTotal', 0) < 8 * 1024**3:
                raise RuntimeError('Give Docker at least 8 GB of memory, then retry.')
            if shutil.disk_usage(self.folder).free < 20 * 1024**3:
                raise RuntimeError('Free at least 20 GB of disk space, then retry.')
            self.update(status='downloading', message='Installing benchmark tools')
            marker = self.folder / 'tools-version'
            if not self.python.exists() or not marker.exists() or marker.read_text() != HARNESS:
                self.command([sys.executable, '-m', 'venv', self.folder / 'venv'], 120)
                self.command([self.python, '-m', 'pip', 'install', '--disable-pip-version-check', 'swebench==' + HARNESS, 'pyarrow==19.0.1'])
                marker.write_text(HARNESS)
            dataset = self.folder / 'dataset.json'
            parquet = self.folder / 'dataset.parquet'
            if not parquet.exists() or hashlib.sha256(parquet.read_bytes()).hexdigest() != DATASET_SHA256:
                self.update(message='Downloading pinned tasks')
                url = f'https://huggingface.co/datasets/{DATASET}/resolve/{REVISION}/data/test-00000-of-00001.parquet'
                with urllib.request.urlopen(url, timeout=60) as response:
                    data = response.read(30 * 1024**2 + 1)
                if len(data) > 30 * 1024**2:
                    raise RuntimeError('Dataset exceeds the expected download size.')
                if hashlib.sha256(data).hexdigest() != DATASET_SHA256:
                    raise RuntimeError('Dataset verification failed. Retry the download.')
                parquet.write_bytes(data)
            # Rebuild the parsed cache from verified bytes, never trust a stale JSON cache.
            self.command([self.python, self.root / 'scripts/swebench_helper.py', 'dataset', parquet, dataset], 120)
            rows = sorted(json.loads(dataset.read_text()), key=lambda row: row['instance_id'])
            random.Random(0).shuffle(rows)
            selected = rows[:count]
            tasks = []
            for index, row in enumerate(selected):
                if self.cancel.is_set():
                    raise InterruptedError()
                instance = row['instance_id']
                self.update(status='preparing', message=f'Preparing task {index + 1} of {count}', completed=index)
                if shutil.disk_usage(self.folder).free < 10 * 1024**3:
                    raise RuntimeError('Free more disk space, then retry. Prepared tasks are cached.')
                image = 'swebench/sweb.eval.x86_64.' + instance.lower().replace('__', '_1776_') + ':latest'
                cache = self.folder / instance
                cache.mkdir(exist_ok=True)
                metadata = cache / 'image.json'
                if metadata.exists():
                    pin = json.loads(metadata.read_text())
                    image = pin['digest']
                self.command(['docker', 'pull', '--platform', 'linux/amd64', image])
                inspected = subprocess.run(['docker', 'image', 'inspect', image], check=True, capture_output=True, timeout=30)
                detail = json.loads(inspected.stdout)[0]
                digest = detail['RepoDigests'][0]
                tag = 'basis-' + detail['Id'].split(':')[1][:20]
                pinned_tag = 'swebench/sweb.eval.x86_64.' + instance.lower().replace('__', '_1776_') + ':' + tag
                self.command(['docker', 'tag', image, pinned_tag], 30)
                save(metadata, {'digest': digest, 'tag': tag})
                source = cache / 'source'
                if not source.exists():
                    archive = cache / 'source.tar'
                    name = 'basis-prepare-' + uuid.uuid4().hex
                    self.update(container=name)
                    with archive.open('wb') as stream:
                        self.command(['docker', 'run', '--rm', '--name', name, '--platform', 'linux/amd64', '--network=none', '--read-only', '--cap-drop=ALL', '--security-opt=no-new-privileges', '--memory=2g', '--cpus=2', '--entrypoint', 'tar', digest, '-C', '/testbed', '--exclude=.git', '-cf', '-', '.'], output=stream)
                    self.update(container=None)
                    staging = cache / 'extracting'
                    shutil.rmtree(staging, ignore_errors=True)
                    staging.mkdir()
                    total = 0
                    with tarfile.open(archive) as tar:
                        for member in tar:
                            path = PurePosixPath(member.name)
                            if path.is_absolute() or '..' in path.parts or '.git' in path.parts:
                                raise RuntimeError('Unsafe benchmark source archive.')
                            if not member.isfile():
                                continue
                            total += member.size
                            if total > 100 * 1024**2:
                                raise RuntimeError('Benchmark source exceeds 100 MB.')
                            target = staging / str(path)
                            target.parent.mkdir(parents=True, exist_ok=True)
                            with tar.extractfile(member) as src, target.open('wb') as dst:
                                shutil.copyfileobj(src, dst)
                            target.chmod(0o755 if member.mode & 0o111 else 0o644)
                    staging.rename(source)
                    archive.unlink()
                # Private reference data never enters the agent's source or prompt.
                save(cache / 'instance.json', row)
                tasks.append({'id': instance, 'name': instance, 'acceptance': row['problem_statement'],
                              'sourcePath': str(source), 'checksPath': '', 'checkCommand': '',
                              'grader': 'swebench-lite', 'imageDigest': digest, 'imageTag': tag,
                              'instancePath': str(cache / 'instance.json')})
            manifest = {'id': 'swebench-lite', 'name': 'SWE-bench Lite', 'revision': REVISION,
                        'harness': HARNESS, 'seed': 0, 'tasks': tasks}
            save(self.folder / f'selection-{count}.json', manifest)
            if self.cancel.is_set():
                raise InterruptedError()
            self.update(status='ready', completed=count, message='Ready', revision=REVISION, harness=HARNESS)
        except InterruptedError:
            self.remove_container(self.state.get('container'))
            self.update(status='cancelled', message='Preparation cancelled')
        except Exception as error:
            self.remove_container(self.state.get('container'))
            self.update(status='error', message=str(error) if isinstance(error, RuntimeError) else 'Preparation failed. Check Docker, disk space, and network access; then retry.')

    def selection(self, count):
        if type(count) is not int or not 1 <= count <= 300:
            raise ValueError('Invalid SWE-bench Lite task count.')
        path = self.folder / f'selection-{count}.json'
        if not path.exists() or not self.python.exists():
            raise ValueError('Prepare SWE-bench Lite in Benchmarks before running.')
        selection = json.loads(path.read_text())
        if selection.get('revision') != REVISION or selection.get('harness') != HARNESS or len(selection.get('tasks', [])) != count:
            raise ValueError('SWE-bench Lite cache changed. Remove and add the benchmark again.')
        if any(not Path(task['sourcePath']).is_dir() or not Path(task['instancePath']).is_file() for task in selection['tasks']):
            raise ValueError('SWE-bench Lite files are missing. Remove and add the benchmark again.')
        return selection
