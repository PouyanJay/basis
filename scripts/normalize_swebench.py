#!/usr/bin/env python3
"""Normalize an OFFICIAL SWE-bench report, never guess outcome from patches."""
import argparse,json,pathlib,sys

def normalize(agent_run,official, harness_rev):
    if agent_run.get('type')!='basis-swebench-lite-agent-run' or agent_run.get('recordKind')!='ungraded-predictions':raise ValueError('Unknown generation evidence')
    if not isinstance(official,dict):raise ValueError('Missing official harness report')
    # SWE-bench report keys include resolved, unresolved, error, empty_patch, completed_ids.
    resolved=set(official.get('resolved_ids',[]));unresolved=set(official.get('unresolved_ids',[]));errors=set(official.get('error_ids',[]))
    if not (resolved or unresolved or errors):raise ValueError('Official report has no task outcomes')
    if len({r['instance_id'] for r in agent_run['records']}) != len(agent_run['records']): raise ValueError('Duplicate agent task IDs')
    if any(x in resolved and x in unresolved|errors for x in resolved):raise ValueError('Contradictory official results')
    records=agent_run['records'];expected={r['instance_id'] for r in records}
    if (resolved|unresolved|errors)-expected:raise ValueError('Official report includes unrequested tasks')
    if resolved & unresolved or resolved & errors or unresolved & errors:raise ValueError('Overlapping status sets')
    tasks=[]
    for r in records:
        iid=r['instance_id'];status='resolved' if iid in resolved else 'unresolved' if iid in unresolved else 'error' if iid in errors else 'not_graded'
        tasks.append({'id':iid,'status':status,'durationSeconds':r['duration_seconds']})
    return {'schemaVersion':1,'type':'basis-community-benchmark-report','benchmarkId':'swebench-lite','datasetRevision':agent_run['datasetRevision'],'harnessRevision':harness_rev,'agent':agent_run['vendor'],'model':agent_run['model'],'executionMode':'headless-cli','runId':agent_run['runId'],'provenance':'official-swebench-harness','verified':False,'humanAccepted':False,'tasks':tasks,'verificationNote':'Derived from official harness report and local generation bundle. Independently verify workflow artifact provenance before trusting.'}

def main():
    p=argparse.ArgumentParser();p.add_argument('--agent-run',required=True);p.add_argument('--official-report',required=True);p.add_argument('--harness-revision',required=True);p.add_argument('--out',required=True);a=p.parse_args()
    agent=json.loads(pathlib.Path(a.agent_run).read_text());official=json.loads(pathlib.Path(a.official_report).read_text())
    result=normalize(agent,official,a.harness_revision);dest=pathlib.Path(a.out);dest.parent.mkdir(parents=True,exist_ok=True);dest.write_text(json.dumps(result,indent=2)+'\n')
if __name__=='__main__':main()
