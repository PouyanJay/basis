import assert from 'node:assert/strict';
import {BENCHMARKS,validateBenchmarkReport,summarizeReport} from '../benchmarks.js';
assert.equal(BENCHMARKS.length,4);
let r={type:'basis-community-benchmark-report',schemaVersion:1,benchmarkId:'swebench-lite',datasetRevision:'a'.repeat(40),harnessRevision:'b'.repeat(40),agent:'Codex',model:'gpt-model',executionMode:'CLI',runId:'test-run',provenance:'external-official-harness',verified:false,humanAccepted:false,tasks:[{id:'repo__issue1',status:'resolved',durationSeconds:25},{id:'repo__issue2',status:'timeout',durationSeconds:120}]};
assert.equal(summarizeReport(validateBenchmarkReport(r)).rate,.5);
for(const edit of [{benchmarkId:'made-up'},{verified:true},{tasks:[...r.tasks,r.tasks[0]]},{tasks:[{id:'a',status:'passed',durationSeconds:1}]},{datasetRevision:'latest'}])assert.throws(()=>validateBenchmarkReport({...r,...edit}));
console.log('Benchmark catalog and report validation tests passed');
