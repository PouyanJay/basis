#!/usr/bin/env python3
"""Run one allowlisted coding CLI against an approved disposable public fixture.

Do not run on production repositories or privileged runners. No shell=True.
"""
import argparse, datetime, hashlib, json, os, pathlib, shutil, subprocess, sys, time

P=argparse.ArgumentParser()
P.add_argument('--vendor',choices=['claude','cursor','codex','opencode'],required=True)
P.add_argument('--workspace',default='fixtures/agent_task')
P.add_argument('--out',default='evaluation-output/agent-result.json')
P.add_argument('--timeout',type=int,default=600)
P.add_argument('--model',default='')
args=P.parse_args()
workspace=pathlib.Path(args.workspace).resolve()
if not workspace.is_dir() or not (workspace/'TASK.md').is_file(): P.error('Approved task workspace with TASK.md required')
if args.timeout < 1 or args.timeout > 1200: P.error('Timeout must be 1..1200')
if args.model and (len(args.model)>100 or not all(c.isalnum() or c in '_./:-' for c in args.model)): P.error('Invalid model')
if True:
  expected={'claude':'ANTHROPIC_API_KEY','cursor':'CURSOR_API_KEY','codex':'OPENAI_API_KEY','opencode':'OPENCODE_MODEL_KEY'}[args.vendor]
  # OpenCode supports different providers; map selected provider key before invoking.
  if args.vendor=='opencode': expected='ANTHROPIC_API_KEY' if args.model.startswith('anthropic/') else 'OPENAI_API_KEY'
  if not os.environ.get(expected): P.error('Missing provider secret; configure it in Basis Settings')
prompt=(workspace/'TASK.md').read_text(encoding='utf8') + '\nImplement the task in this working directory. Do not alter TASK.md. Do not use external repositories.'
commands={
 'claude':['claude','-p',prompt,'--permission-mode','bypassPermissions'],
 'cursor':['cursor-agent','-p','--force','--output-format','text',prompt],
 'codex':['codex','exec','--dangerously-bypass-approvals-and-sandbox' if os.environ.get('BASIS_ISOLATED_RUNNER')=='1' else '--full-auto',prompt],
 'opencode':['opencode','run','--pure','--agent','build',prompt]
}
cmd=commands[args.vendor][:]
if os.environ.get('BASIS_ISOLATED_RUNNER')=='1':
  if args.vendor=='opencode': cmd.insert(2,'--auto')
  if args.vendor=='cursor': cmd.insert(2,'--trust')
if args.model and args.vendor=='cursor': cmd[2:2]=['--model',args.model]
if args.model and args.vendor=='opencode': cmd[2:2]=['--model',args.model]
if args.model and args.vendor=='claude': cmd[2:2]=['--model',args.model]
if args.model and args.vendor=='codex': cmd[2:2]=['-m',args.model]
start=time.monotonic(); error=''; code=None; timedout=False
try:
  r=subprocess.run(cmd,cwd=workspace,timeout=args.timeout,capture_output=True,text=True,check=False)
  code=r.returncode
  if code: error='Agent exited with nonzero status; check the configured key and model, then retry.'
except subprocess.TimeoutExpired:
  timedout=True;error='Agent exceeded time limit.'
except FileNotFoundError:
  error='CLI executable not installed.'
# The agent job contains provider secrets: never publish its output or diff as public artifacts.
# Independent grading below runs only a fixed, reviewed verifier.
passed=False;verify_code=None
if not timedout and code==0:
  try:
    v=subprocess.run([sys.executable,'-m','unittest','discover','-s',str(pathlib.Path(__file__).resolve().parents[1]/'benchmark-tests'/'agent_task'),'-v'],cwd=workspace,timeout=90,capture_output=True,text=True,env={**{k:v for k,v in os.environ.items() if k not in ('ANTHROPIC_API_KEY','OPENAI_API_KEY','CURSOR_API_KEY')},'PYTHONPATH':str(workspace)})
    verify_code=v.returncode;passed=v.returncode==0
  except subprocess.TimeoutExpired: error='Verifier timed out.'
result={'schemaVersion':2,'type':'basis-agent-evaluation','recordKind':'automated-test','candidate':args.vendor,'model':args.model or 'provider-default','task':'agent_task','taskDigest':hashlib.sha256((workspace/'TASK.md').read_bytes()).hexdigest(),'agentExitCode':code,'agentTimedOut':timedout,'verifierExitCode':verify_code,'automatedTestsPass':passed,'accepted':False,'humanReview':'required','elapsedSeconds':round(time.monotonic()-start,2),'timeRecordedUtc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'provenance':'CI runner execution; no independent human code review','error':error}
out=pathlib.Path(args.out);out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(result,indent=2)+'\n')
print('RESULT',json.dumps({k:result[k] for k in ['candidate','agentExitCode','automatedTestsPass','elapsedSeconds']}))
# Fail the job if the tests failed, preserving result as an artifact.
sys.exit(0 if passed else 1)
