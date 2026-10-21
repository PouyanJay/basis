#!/usr/bin/env python3
"""Combine graded agent reports for a shared manifest; no fictional scores."""
import argparse,json,pathlib

def compare(reports):
    if not reports:raise ValueError('No reports')
    first=reports[0];base=(first['datasetRevision'],first['harnessRevision'],tuple(x['id'] for x in first['tasks']))
    seen=set();items=[]
    for r in reports:
        if (r['datasetRevision'],r['harnessRevision'],tuple(x['id'] for x in r['tasks']))!=base:raise ValueError('Incomparable task sets or revisions')
        if r['agent'] in seen:raise ValueError('Duplicate agent')
        seen.add(r['agent']);counts={x:sum(t['status']==x for t in r['tasks']) for x in ('resolved','unresolved','error','not_graded')}
        items.append({'agent':r['agent'],'model':r['model'],'selected':len(r['tasks']),'counts':counts,'resolvedRate':counts['resolved']/len(r['tasks'])})
    return {'type':'basis-swebench-lite-comparison','datasetRevision':base[0],'harnessRevision':base[1],'taskIds':list(base[2]),'candidates':items,'verified':False,'note':'Official harness outputs imported; verify provenance and CI configuration before relying on scores.'}
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('files',nargs='+');p.add_argument('--output',required=True);a=p.parse_args()
    data=compare([json.loads(pathlib.Path(f).read_text()) for f in a.files]);pathlib.Path(a.output).write_text(json.dumps(data,indent=2)+'\n')
