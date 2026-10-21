#!/usr/bin/env python3
"""Deterministic nested repository-balanced ordering of the OFFICIAL Lite test split.

No generated questions or synthetic scores. Manifest is shared by every vendor.
"""
import argparse, collections, hashlib, json, math, pathlib, random

def order_tasks(rows, seed):
    groups=collections.defaultdict(list)
    for row in rows:
        groups[row['repo']].append(row['instance_id'])
    rng=random.Random(str(seed))
    for group in groups.values(): rng.shuffle(group)
    # Greedy proportional deficit: approximate representation at every prefix.
    total=len(rows); selected=[]; used=collections.Counter()
    while len(selected)<total:
        n=len(selected)+1
        eligible=[g for g in groups if groups[g]]
        score=lambda g: (n* (len(groups[g])+used[g])/total - used[g], -used[g], g)
        best=max(eligible,key=score)
        selected.append(groups[best].pop());used[best]+=1
    return selected

def make_manifest(rows, seed, percentage, dataset_revision):
    if len(rows)!=300: raise ValueError(f'Expected 300 official SWE-bench Lite tasks; found {len(rows)}')
    if not isinstance(percentage,int) or not 1<=percentage<=100: raise ValueError('Percentage must be an integer 1..100')
    ids=order_tasks(rows,seed)
    k=math.ceil(len(ids)*percentage/100)
    return {'type':'basis-swebench-lite-sample','schemaVersion':1,'benchmarkId':'swebench-lite','dataset':'SWE-bench/SWE-bench_Lite','datasetRevision':dataset_revision,'seed':str(seed),'percentage':percentage,'totalPopulation':len(ids),'selectedCount':k,'instanceIds':ids[:k],'selectionAlgorithm':'repo-balanced-nested-v1','fullOrderSha256':hashlib.sha256(('\n'.join(ids)).encode()).hexdigest()}

def main():
    p=argparse.ArgumentParser();p.add_argument('--percent',type=int,default=10);p.add_argument('--seed',default='42');p.add_argument('--revision',default='main');p.add_argument('--out',required=True);a=p.parse_args()
    from datasets import load_dataset
    from huggingface_hub import HfApi
    name='SWE-bench/SWE-bench_Lite';sha=HfApi().dataset_info(name,revision=a.revision).sha
    rows=list(load_dataset(name,revision=sha,split='test'))
    manifest=make_manifest(rows,a.seed,a.percent,sha)
    out=pathlib.Path(a.out);out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(manifest,indent=2)+'\n')
    print(f"Selected {manifest['selectedCount']}/300 official tasks, revision {sha}, seed {a.seed}")
if __name__=='__main__': main()
