"""Local run workspaces. Drafts and executions share an immutable identity/folder."""
import copy
import json
import re
import shutil
import time
import uuid
from local_evaluation import write_json, copy_source, normalize_completion

SECRET_FIELDS = {'apikey','api_key','token','password','secret','credentials','pendingkeys','authorization','openai_api_key','anthropic_api_key'}

def clean_setup(value):
    if not isinstance(value,dict) or not isinstance(value.get('platforms'),list) or not isinstance(value.get('tasks'),list):
        raise ValueError('Provide a valid run setup.')
    if not isinstance(value.get('meta',{}),dict) or any(not isinstance(p,dict) or not isinstance(p.get('id'),str) for p in value['platforms']) or any(not isinstance(t,dict) for t in value['tasks']):raise ValueError('Invalid run setup fields.')
    def clean(v):
        if isinstance(v,dict):return {k:clean(x) for k,x in v.items() if k.lower() not in SECRET_FIELDS}
        if isinstance(v,list):return [clean(x) for x in v]
        return v
    result=clean(value)
    if len(json.dumps(result))>400000:raise ValueError('Run setup exceeds 400 KB.')
    name=result.setdefault('meta',{}).get('name','New run')
    if not isinstance(name,str) or not 1<=len(name.strip())<=150:raise ValueError('Use a run name between 1 and 150 characters.')
    result['meta']['name']=name.strip()
    return result

class RunWorkspaces:
    def __init__(self,runner):
        self.runner=runner;self.root=runner.folder/'evaluations';self.root.mkdir(exist_ok=True)
        self.lock=runner.lock
    def directory(self,run_id):
        if not isinstance(run_id,str) or not re.fullmatch('[a-f0-9]{32}',run_id):raise ValueError('Invalid run ID.')
        p=self.root/run_id
        if p.is_symlink() or not p.is_dir():raise ValueError('Run not found.')
        return p
    def read(self,p):
        if p.is_symlink():raise ValueError('Invalid workspace file.')
        return json.loads(p.read_text())
    def get(self,run_id):
        with self.lock:
            p=self.directory(run_id);job=self.read(p/'result.json') if (p/'result.json').exists() else None
            if (p/'workspace.json').exists():w=self.read(p/'workspace.json')
            elif job:
                setup=copy.deepcopy(job['plan']['setup']);setup['execution']={**setup.get('execution',{}),**{k:job['plan'][k] for k in ('timeoutSeconds','benchmarkPaths','integratedBenchmarks','platformReview') if k in job['plan']}}
                w={'id':run_id,'revision':0,'createdAt':job.get('startedAt',0),'updatedAt':job.get('finishedAt') or job.get('startedAt',0),'parentId':None,'parentName':None,'setup':setup}
            else:raise ValueError('Run is missing its setup.')
            w=copy.deepcopy(w);w['status']=normalize_completion(job)['status'] if job else 'draft'
            # Executed setup is authoritative and cannot be changed by a draft file.
            if job:w['setup']=copy.deepcopy(job['plan']['setup']);w['setup']['execution']={**w['setup'].get('execution',{}),**{k:job['plan'][k] for k in ('timeoutSeconds','benchmarkPaths','integratedBenchmarks','platformReview') if k in job['plan']}}
            w['name']=w['setup'].get('meta',{}).get('name') or 'Untitled run'
            w['updatedAt']=job.get('finishedAt') or job.get('startedAt') or w['updatedAt'] if job else w['updatedAt']
            w['changes']=[]
            if (p/'origin-setup.json').exists() and not job:
                origin=self.read(p/'origin-setup.json')
                for label,key in [('Services and models','platforms'),('Team context','org'),('Requirements','orgRequirements'),('Tasks','tasks'),('Benchmarks and limits','execution')]:
                    if w['setup'].get(key)!=origin.get(key):w['changes'].append(label)
            w['models']=sum(len(s.get('models',[s.get('model')])) for s in w['setup'].get('platforms',[]) if s.get('enabled'))
            w['services']=[s.get('name',s['id']) for s in w['setup'].get('platforms',[]) if s.get('enabled')]
            return w
    def listing(self):
        with self.lock:
            rows=[]
            for p in self.root.iterdir():
                if not p.is_dir() or p.is_symlink():continue
                try:rows.append({k:v for k,v in self.get(p.name).items() if k!='setup'})
                except (OSError,ValueError,KeyError):continue
            return sorted(rows,key=lambda w:w['updatedAt'],reverse=True)
    def create(self,setup):
        with self.lock:
            setup=clean_setup(setup);run_id=uuid.uuid4().hex;p=self.root/run_id;p.mkdir(mode=0o700)
            w={'id':run_id,'revision':1,'createdAt':time.time(),'updatedAt':time.time(),'parentId':None,'parentName':None,'setup':setup}
            try:write_json(p/'workspace.json',w)
            except Exception:shutil.rmtree(p);raise
            return self.get(run_id)
    def save(self,run_id,setup,revision):
        with self.lock:
            w=self.get(run_id)
            if w['status']!='draft':raise ValueError('This run has started. Clone it to change its setup.')
            if type(revision) is not int or revision!=w['revision']:raise ValueError('This draft changed in another tab. Reopen it before editing.')
            w.update(setup=clean_setup(setup),revision=revision+1,updatedAt=time.time())
            write_json(self.directory(run_id)/'workspace.json',{k:w[k] for k in ('id','revision','createdAt','updatedAt','parentId','parentName','setup')})
            return self.get(run_id)
    def clone(self,run_id):
        with self.lock:
            original=self.get(run_id);setup=copy.deepcopy(original['setup']);setup['meta']['name']=(original['name'][:140]+' (copy)')
            setup.get('execution',{}).pop('pendingLiteCount',None)
            # Reviews/results belong to the old run, not its new draft.
            setup['runs']=[];setup['gateResults']={};setup['gateEvidence']={};setup.pop('importedEvidence',None)
            child=self.create(setup);source=self.directory(run_id);target=self.directory(child['id'])
            try:
                write_json(target/'origin-setup.json',original['setup'])
                if (source/'plan.json').exists():
                    plan=self.read(source/'plan.json')
                    for i,task in enumerate(plan['tasks']):
                        base=source/'inputs'/str(i)
                        for kind in ('source','checks'):
                            if not (base/kind).is_dir():raise ValueError('Saved input snapshots are missing. Restore them before cloning this run.')
                            copy_source(str(base/kind),target/'clone-inputs'/str(i)/kind)
                        if task.get('grader')=='swebench-lite':
                            instance=base/'instance.json'
                            if instance.is_symlink():raise ValueError('Invalid saved benchmark instance.')
                            shutil.copyfile(instance,target/'clone-inputs'/str(i)/'instance.json')
                    write_json(target/'clone-plan.json',plan)
                elif (source/'clone-plan.json').exists():
                    plan=self.read(source/'clone-plan.json')
                    for i,task in enumerate(plan['tasks']):
                        for kind in ('source','checks'):copy_source(str(source/'clone-inputs'/str(i)/kind),target/'clone-inputs'/str(i)/kind)
                        if task.get('grader')=='swebench-lite':
                            instance=source/'clone-inputs'/str(i)/'instance.json'
                            if instance.is_symlink():raise ValueError('Invalid saved benchmark instance.')
                            shutil.copyfile(instance,target/'clone-inputs'/str(i)/'instance.json')
                    write_json(target/'clone-plan.json',plan)
                w=self.read(target/'workspace.json');w.update(parentId=run_id,parentName=original['name']);write_json(target/'workspace.json',w)
                return self.get(child['id'])
            except Exception:shutil.rmtree(target);raise
    def start(self,run_id,revision,consent):
        with self.lock:
            w=self.get(run_id)
            if w['status']!='draft':raise ValueError('This run already has an execution. Clone it to run again.')
            if revision!=w['revision']:raise ValueError('Save the latest setup before running.')
            setup=w['setup'];options=setup.get('execution',{})
            plan={'setup':setup,**{k:options[k] for k in ('timeoutSeconds','benchmarkPaths','integratedBenchmarks','platformReview') if k in options}}
            p=self.directory(run_id);frozen=self.read(p/'clone-plan.json') if (p/'clone-plan.json').exists() else None
            return self.runner.start(plan,consent,workspace_id=run_id,frozen_plan=frozen)
