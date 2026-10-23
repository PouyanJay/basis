"""Pinned SWE-bench dependencies run in a dedicated, credential-free venv."""
import json
from pathlib import Path
import sys


def main():
    mode, filename = sys.argv[1:3]
    if mode == 'dataset':
        import pyarrow.parquet as pq
        rows = pq.read_table(filename).to_pylist()
        Path(sys.argv[3]).write_text(json.dumps(rows))
        return
    import docker
    from swebench.harness.test_spec.test_spec import make_test_spec
    from swebench.harness.run_evaluation import run_instance
    config = json.loads(Path(filename).read_text())
    spec = make_test_spec(config['instance'], namespace='swebench', instance_image_tag=config['imageTag'])
    spec.arch = 'x86_64'
    pred = {'instance_id': spec.instance_id, 'model_name_or_path': 'basis',
            'model_patch': Path(config['patch']).read_text()}
    client = docker.from_env()
    if config.get('imageDigest') and client.images.get(spec.instance_image_key).id != client.images.get(config['imageDigest']).id:
        raise RuntimeError('Prepared benchmark image changed. Re-add the benchmark.')
    create = client.containers.create
    def isolated_create(*args, **kwargs):
        kwargs.update(mem_limit='4g', nano_cpus=2_000_000_000, pids_limit=512,
                      network_disabled=True, cap_drop=['ALL'], security_opt=['no-new-privileges'])
        return create(*args, **kwargs)
    client.containers.create = isolated_create
    print('Starting isolated official checks', flush=True)
    result = run_instance(spec, pred, False, False, client, config['runId'], timeout=config['timeout'])
    if result is None:
        log = Path('logs/run_evaluation') / config['runId'] / 'basis' / spec.instance_id / 'test_output.txt'
        if log.exists() and f'Timeout error: {config["timeout"]} seconds exceeded.' in log.read_text(errors='replace')[-500:]:
            sys.exit(124)
        raise RuntimeError('Official grader produced no report; see grading logs.')
    _, report = result
    Path(config['report']).write_text(json.dumps(report, indent=2))
    print('Official grading report saved', flush=True)


if __name__ == '__main__':
    main()
