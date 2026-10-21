#!/usr/bin/env python3
"""SWE-bench Lite public issue runner; never run this against privileged/private repos.

The official swebench harness (separate job) is solely responsible for grading.
"""
import argparse, datetime, hashlib, json, os, pathlib, re, shutil, subprocess, sys, time

ROOT=pathlib.Path(__file__).resolve().parents[1]
VENDORS={'codex':'OPENAI_API_KEY','claude':'ANTHROPIC_API_KEY','cursor':'CURSOR_API_KEY','opencode':'OPENAI_API_KEY'}

def validate_model(s):
    if len(s)>110 or not re.fullmatch(r'[a-zA-Z0-9_./:-]*',s):raise ValueError('Invalid model identifier')

def cli(vendor, model, prompt):
    validate_model(model)
    commands={
      'codex':['codex','exec','--sandbox','workspace-write','--skip-git-repo-check',prompt],
      'claude':['claude','-p',prompt,'--permission-mode','bypassPermissions'],
      'cursor':['cursor-agent','-p','--force','--output-format','text',prompt],
      'opencode':['opencode','run','--agent','build',prompt]
    }
    cmd=commands[vendor]
    if model:
        if vendor=='opencode':cmd[2:2]=['--model',model]
        elif vendor=='claude':cmd[2:2]=['--model',model]
        elif vendor=='cursor':cmd[2:2]=['--model',model]
        else:cmd[2:2]=['--model',model]
    return cmd

def run_process(args, cwd, timeout, env=None):
    return subprocess.run(args,cwd=cwd,timeout=timeout,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False)

def load_tasks(limit, instance_ids, revision):
    from datasets import load_dataset
    from huggingface_hub import HfApi
    repo='SWE-bench/SWE-bench_Lite'
    resolved=HfApi().dataset_info(repo,revision=revision).sha
    data=load_dataset(repo,split='test',revision=resolved)
    rows={r['instance_id']:r for r in data}
    if instance_ids:
        unknown=set(instance_ids)-set(rows)
        if unknown:raise ValueError('Unknown Lite IDs: '+', '.join(sorted(unknown)))
        chosen=[rows[x] for x in instance_ids]
    else:chosen=list(rows.values())[:limit]
    return chosen,resolved

def run(args):
    if args.vendor not in VENDORS:raise ValueError('Unsupported vendor')
    validate_model(args.model)
    if args.vendor=='opencode' and not args.model:raise ValueError('OpenCode requires provider/model')
    provider=VENDORS[args.vendor]
    if args.vendor=='opencode' and args.model.startswith('anthropic/'):
        provider='ANTHROPIC_API_KEY'
    if not os.getenv(provider):raise ValueError('Missing credential: '+provider)
    if args.limit<1 or args.limit>300:raise ValueError('Choose 1–300 official tasks')
    if args.timeout<30 or args.timeout>1800:raise ValueError('Timeout must be 30–1800 seconds')
    
    if args.manifest:
        manifest=json.loads(pathlib.Path(args.manifest).read_text())
        if manifest.get('type')!='basis-swebench-lite-sample' or len(manifest.get('instanceIds',[]))!=manifest.get('selectedCount') or len(set(manifest['instanceIds']))!=manifest['selectedCount']:
            raise ValueError('Invalid or duplicate sample manifest')
        args.ids=manifest['instanceIds']
        args.dataset_revision=manifest['datasetRevision']
    rows,ds_rev=load_tasks(args.limit,args.ids,args.dataset_revision)
    out=pathlib.Path(args.output).resolve();out.mkdir(parents=True,exist_ok=True)
    predictions=[];records=[]
    for row in rows:
        iid=row['instance_id']; repo=row['repo']; commit=row['base_commit']
        if not re.fullmatch(r'[\w.-]+/[\w.-]+',repo) or not re.fullmatch('[a-fA-F0-9]{40}',commit):raise ValueError('Invalid public repo/commit in dataset')
        work=out/'work'/iid;work.parent.mkdir(exist_ok=True)
        # Github Actions public tasks only. Distinct checkout for every instance.
        fetched=run_process(['git','clone','--no-checkout','--filter=blob:none','https://github.com/'+repo+'.git',str(work)],ROOT,300)
        if fetched.returncode:raise RuntimeError('Could not clone source repository: '+repo)
        checked=run_process(['git','-c','advice.detachedHead=false','checkout',commit],work,240)
        if checked.returncode:raise RuntimeError('Could not checkout base commit for '+iid)
        # Prevent baseline untracked artifacts from entering the patch.
        prompt=(f'You are solving a public SWE-bench Lite GitHub issue.\nIssue:\n{row["problem_statement"]}\n'
                'Edit the repository files to resolve the issue. Do not modify tests to manufacture success. '
                'Do not search for official solutions or hidden evaluation tests. You are working in the checkout root.')
        initial=time.monotonic();status='agent_error';err='';exitcode=None
        try:
            env=os.environ.copy();env['CI']='true';env['GIT_TERMINAL_PROMPT']='0'
            result=run_process(cli(args.vendor,args.model,prompt),work,args.timeout,env)
            exitcode=result.returncode
            status='patch_created' if exitcode==0 else 'agent_error'
            if exitcode:err='Agent nonzero exit (see protected workflow logs)'
        except subprocess.TimeoutExpired:status='timeout';err='Agent time limit exceeded'
        except FileNotFoundError:status='adapter_error';err='Vendor executable missing'
        # Only modifications tracked in original repo; no injected tests.
        patch=run_process(['git','diff','--binary','HEAD','--'],work,30)
        diff=patch.stdout if patch.returncode==0 else ''
        if not diff and status=='patch_created':status='empty_patch'
        predictions.append({'instance_id':iid,'model_name_or_path':args.vendor+':'+(args.model or 'default'),'model_patch':diff})
        records.append({'instance_id':iid,'agent':args.vendor,'model':args.model or 'provider-default','status':status,'agent_exit_code':exitcode,'duration_seconds':round(time.monotonic()-initial,2),'patch_sha256':hashlib.sha256(diff.encode()).hexdigest(),'error':err})
        print(f'{iid}: {status} (duration {records[-1]["duration_seconds"]}s)',flush=True)
    with (out/'predictions.jsonl').open('w') as f:
        for r in predictions:f.write(json.dumps(r)+'\n')
    meta={'type':'basis-swebench-lite-agent-run','schemaVersion':1,'benchmarkId':'swebench-lite','dataset':'SWE-bench/SWE-bench_Lite','datasetRevision':ds_rev,'harnessRevision':None,'vendor':args.vendor,'model':args.model or 'provider-default','runId':os.getenv('GITHUB_RUN_ID','local')+'-'+args.vendor,'executionMode':'headless-cli','recordKind':'ungraded-predictions','createdUtc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'records':records,'sampleManifest':json.loads(pathlib.Path(args.manifest).read_text()) if args.manifest else None}
    (out/'agent-run.json').write_text(json.dumps(meta,indent=2)+'\n')
    print('Wrote ungraded prediction bundle. Do not interpret as resolved tasks.')

def main():
    p=argparse.ArgumentParser();p.add_argument('--vendor',choices=VENDORS,required=True);p.add_argument('--manifest');p.add_argument('--model',default='');p.add_argument('--limit',type=int,default=1);p.add_argument('--ids',nargs='*');p.add_argument('--dataset-revision',default='main');p.add_argument('--timeout',type=int,default=900);p.add_argument('--output',default='evaluation-output/swebench-lite');a=p.parse_args()
    try:run(a)
    except (ValueError,RuntimeError) as e:print('RUN ERROR:',str(e),file=sys.stderr);sys.exit(2)
if __name__=='__main__':main()
