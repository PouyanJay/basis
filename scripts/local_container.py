"""Trusted container entrypoint. Emit only the structured result, never agent output."""
import os
import json
import pathlib
import shutil
import subprocess
import sys

os.environ['BASIS_ISOLATED_RUNNER'] = '1'
ROOT = pathlib.Path('/opt/basis')
shutil.copytree(ROOT / 'fixtures/agent_task', '/work', dirs_exist_ok=True)
subprocess.run(['git', 'init', '-q', '/work'], check=True)
subprocess.run([sys.executable, str(ROOT / 'scripts/run_agent.py'), '--vendor', sys.argv[1], '--model', sys.argv[2], '--workspace', '/work', '--out', '/tmp/result.json'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=710)
report = json.loads(pathlib.Path('/tmp/result.json').read_text())
report['provenance'] = 'Local isolated container; no independent human code review'
print(json.dumps(report))
