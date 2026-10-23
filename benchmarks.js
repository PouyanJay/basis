// Primary-source catalog; availability is separate from measured results.
export const BENCHMARKS = Object.freeze([
 {id:'swebench-lite',name:'SWE-bench Lite',version:'6ec7bb89b9342f664a54a6e0a6ea6501d3437cc2',category:'Repository issues',difficulty:'Accessible start',runtime:'Docker; high disk/memory demand',runner:'Pinned official SWE-bench harness',status:'integrated',source:'https://github.com/SWE-bench/SWE-bench',setup:'https://github.com/SWE-bench/SWE-bench/blob/main/docs/reference/cli.md',note:'Smaller established subset; scores depend on dataset revision and evaluation harness.'},
 {id:'swebench-verified',name:'SWE-bench Verified',version:'dataset revision must be pinned',category:'Repository issues',difficulty:'Intermediate',runtime:'Docker; high disk/memory demand',runner:'External official SWE-bench harness',status:'inactive',source:'https://github.com/SWE-bench/SWE-bench',setup:'https://github.com/SWE-bench/SWE-bench/blob/main/README.md',note:'Use with known grading and contamination limitations; do not infer production performance.'},
 {id:'terminalbench-2.1',name:'Terminal-Bench 2.1',version:'2.1',category:'Autonomous terminal work',difficulty:'Advanced',runtime:'Container runtime / Harbor',runner:'External Harbor harness',status:'inactive',source:'https://www.tbench.ai/news/terminal-bench-2-1',setup:'https://www.tbench.ai/news/announcement-2-0',note:'Check whether a compatible Harbor adapter exists for each candidate before running.'},
 {id:'swebench-pro',name:'SWE-bench Pro (open subset)',version:'dataset revision must be pinned',category:'Long-horizon software engineering',difficulty:'Advanced',runtime:'Docker; Modal recommended in official docs',runner:'External official Pro harness',status:'inactive',source:'https://github.com/scaleapi/SWE-bench_Pro-os',setup:'https://github.com/scaleapi/SWE-bench_Pro-os',note:'Only publicly accessible tasks; held-out and commercial subsets are not included.'}
]);
const allowed = new Set(BENCHMARKS.map(x=>x.id));
const hex = /^[0-9a-f]{40,64}$/i;
export function validateBenchmarkReport(input){
 if(!input || typeof input !== 'object' || input.schemaVersion!==1 || input.type!=='basis-community-benchmark-report')throw new Error('Not a Basis benchmark report v1');
 if(!allowed.has(input.benchmarkId))throw new Error('Unknown benchmark ID');
 if(typeof input.datasetRevision!=='string' || !hex.test(input.datasetRevision))throw new Error('Dataset revision must be a 40–64 character commit or content hash');
 if(typeof input.harnessRevision!=='string' || !hex.test(input.harnessRevision))throw new Error('Harness revision must be a 40–64 character commit or content hash');
 if(typeof input.agent!=='string'||!input.agent.trim()||input.agent.length>100)throw new Error('Agent required');
 if(typeof input.model!=='string'||!input.model.trim()||input.model.length>100)throw new Error('Model required');
 if(typeof input.executionMode!=='string'||!input.executionMode.trim())throw new Error('Execution mode required');
 if(typeof input.runId!=='string'||!input.runId.trim()||input.runId.length>128)throw new Error('Run ID required');
 if(!['external-official-harness','basis-official-harness'].includes(input.provenance))throw new Error('Unrecognized provenance');
 if(input.verified!==false || input.humanAccepted!==false)throw new Error('Imported report must remain unverified and not human-accepted');
 if(!Array.isArray(input.tasks)||!input.tasks.length||input.tasks.length>10000)throw new Error('At least one task, max 10,000');
 let ids=new Set();
 for(const t of input.tasks){
  if(typeof t.id!=='string'||!t.id||t.id.length>180||ids.has(t.id))throw new Error('Task IDs must be unique');ids.add(t.id);
  if(!['resolved','unresolved','error','timeout'].includes(t.status))throw new Error('Invalid task outcome');
  if(typeof t.durationSeconds!=='number'||!Number.isFinite(t.durationSeconds)||t.durationSeconds<0||t.durationSeconds>100000)throw new Error('Invalid duration');
 }
 // Never trust self-asserted verification fields, provenance, or URL as cryptographic proof.
 return {type:input.type,schemaVersion:1,benchmarkId:input.benchmarkId,datasetRevision:input.datasetRevision,harnessRevision:input.harnessRevision,agent:input.agent.trim(),model:input.model.trim(),executionMode:input.executionMode.trim(),runId:input.runId,provenance:input.provenance,verified:false,humanAccepted:false,tasks:input.tasks.map(t=>({id:t.id,status:t.status,durationSeconds:t.durationSeconds}))};
}
export function summarizeReport(report){let total=report.tasks.length,resolved=report.tasks.filter(t=>t.status==='resolved').length,failures=report.tasks.filter(t=>t.status==='error'||t.status==='timeout').length;return {total,resolved,failures,rate:resolved/total};}
