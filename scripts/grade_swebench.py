#!/usr/bin/env python3
"""Grade genuine patches with upstream SWE-bench Docker harness; fail closed."""
import argparse, glob, json, pathlib, subprocess, sys

def locate_report(run_id):
    paths=glob.glob(f'logs/run_evaluation/{run_id}/**/*report*.json',recursive=True)
    return [p for p in paths if pathlib.Path(p).is_file()]

def main():
    p=argparse.ArgumentParser();p.add_argument('--directory',required=True);p.add_argument('--run-id',required=True);p.add_argument('--workers',type=int,default=1);p.add_argument('--timeout',type=int,default=1800);a=p.parse_args()
    path=pathlib.Path(a.directory);meta=json.loads((path/'agent-run.json').read_text());manifest=meta.get('sampleManifest')
    if not manifest or not manifest.get('instanceIds'):raise SystemExit('Missing official-task manifest')
    ids=manifest['instanceIds'];preds=[json.loads(x) for x in (path/'predictions.jsonl').read_text().splitlines() if x.strip()]
    if [r['instance_id'] for r in preds]!=ids:raise SystemExit('Prediction IDs differ from frozen manifest')
    cmd=[sys.executable,'-m','swebench.harness.run_evaluation','--dataset_name','SWE-bench/SWE-bench_Lite','--split','test','--predictions_path',str(path/'predictions.jsonl'),'--max_workers',str(a.workers),'--timeout',str(a.timeout),'--run_id',a.run_id,'--instance_ids',*ids]
    print('Running OFFICIAL SWE-bench harness for',len(ids),'tasks',flush=True)
    proc=subprocess.run(cmd,check=False)
    if proc.returncode:raise SystemExit(f'Official harness failed: {proc.returncode}')
    reports=locate_report(a.run_id)
    if not reports:raise SystemExit('Official harness completed but no report was found: grading UNVERIFIED')
    # Only accept report files with actual per-task status keys.
    reports=[p for p in reports if any(k in json.loads(pathlib.Path(p).read_text()) for k in ('resolved_ids','unresolved_ids','error_ids'))]
    if len(reports)!=1:raise SystemExit('Cannot uniquely identify official harness report')
    (path/'official-report.json').write_text(pathlib.Path(reports[0]).read_text())
    print('Official report:',reports[0])
if __name__=='__main__':main()
