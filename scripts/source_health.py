#!/usr/bin/env python3
"""Check the curated vendor reference URLs; never promote claims automatically."""
import json, re, urllib.request, pathlib, datetime
root=pathlib.Path(__file__).resolve().parents[1]
text=(root/'technology.js').read_text()
urls=sorted(set(re.findall(r"source:'(https://[^']+)'",text)))
results=[]
for url in urls:
 try:
  req=urllib.request.Request(url,headers={'User-Agent':'BasisSourceHealth/0.2'})
  with urllib.request.urlopen(req,timeout=15) as resp:
   code=resp.status; final=resp.url
  status='reachable' if code==200 else 'review'
 except Exception as e:
  status='manual-review';code=None;final=url
 results.append({'url':url,'httpStatus':code,'status':status,'finalURL':final})
report={'checkedAt':datetime.datetime.now(datetime.timezone.utc).isoformat(),'total':len(results),'results':results,'note':'Availability only; does not certify vendor claims or content correctness.'}
(root/'source-health.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({'checked':len(results),'reachable':sum(x['status']=='reachable' for x in results),'manualReview':sum(x['status']!='reachable' for x in results)}))
