#!/usr/bin/env python3
"""Offline verifier for externally-produced candidate patches.

The evaluator does not run vendor CLIs or expose credentials. It can verify a
candidate's code in an explicitly supplied sandbox, with a fixed, approved
verification command and timeout. Only run TRUSTED fixtures on local runners.
"""
import argparse, datetime, hashlib, json, pathlib, subprocess, time
p=argparse.ArgumentParser()
p.add_argument('--workspace',required=True,help='Existing isolated working directory')
p.add_argument('--candidate',required=True)
p.add_argument('--task',required=True)
p.add_argument('--command',required=True,help='Pre-approved test command; no shell expansion')
p.add_argument('--out',required=True)
p.add_argument('--timeout',type=int,default=120)
a=p.parse_args(); root=pathlib.Path(a.workspace).resolve()
if not root.is_dir():p.error('Workspace missing')
if a.timeout<1 or a.timeout>3600:p.error('Timeout outside allowed range')
import shlex
args=shlex.split(a.command)
if not args:p.error('Empty command')
start=time.monotonic()
try:
 r=subprocess.run(args,cwd=root,capture_output=True,text=True,timeout=a.timeout,check=False)
 code=r.returncode; timedout=False;stdout=r.stdout[-15000:];stderr=r.stderr[-15000:]
except subprocess.TimeoutExpired as e:
 code=None;timedout=True;stdout=str(e.stdout or '')[-15000:];stderr=str(e.stderr or '')[-15000:]
report={'schemaVersion':1,'candidate':a.candidate,'task':a.task,'verifiedAt':datetime.datetime.now(datetime.timezone.utc).isoformat(),'verifier':'approved-command','command':args,'exitCode':code,'timedOut':timedout,'acceptedByAutomatedTest':code==0 and not timedout,'elapsedSeconds':round(time.monotonic()-start,3),'stdoutTail':stdout,'stderrTail':stderr,'workspace':'isolated workspace supplied by operator','manualReview':'required before task is accepted','provenance':'Local test output, not a vendor model performance claim'}
path=pathlib.Path(a.out);path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(report,indent=2)+'\n');print(f"Saved {path}; automated test {'PASS' if report['acceptedByAutomatedTest'] else 'FAIL'}")
