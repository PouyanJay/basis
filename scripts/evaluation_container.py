"""Only invoked inside the isolated local runner container."""
import os
import subprocess
import sys


def main():
    mode = sys.argv[1]
    if mode == 'check':
        return subprocess.call(['/bin/sh', '-c', sys.argv[2]], cwd='/work')
    agent, model, prompt = sys.argv[2:5]
    commands = {
        'claude': ['claude', '-p', prompt, '--permission-mode', 'bypassPermissions', '--output-format', 'stream-json', '--verbose'],
        'codex': ['codex', 'exec', '--skip-git-repo-check', '--dangerously-bypass-approvals-and-sandbox', prompt],
        'cursor': ['cursor-agent', '-p', '--force', '--trust', '--output-format', 'text', prompt],
        'opencode': ['opencode', 'run', '--pure', '--auto', '--agent', 'build', prompt],
    }
    command = commands[agent]
    if model:
        command += ['--model', model]
    return subprocess.call(command, cwd='/work', env={**os.environ, 'HOME': '/home/node'})

if __name__ == '__main__':
    sys.exit(main())
