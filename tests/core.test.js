import test from 'node:test';
import assert from 'node:assert/strict';
import {demo,clone,platformMetrics,gateStatus,scorePlatforms,decision,normalizedMix,validateState} from '../core.js';
function study(){let s=clone(demo);s.org.rate=100;s.mix={Features:0,Debugging:100,Refactoring:0,Tests:0,Migration:0};s.tasks=[{id:'task1',name:'Repair error',type:'Debugging',acceptance:'Independent tests'}];s.runs=[{id:'1',platform:'codex',task:'task1',accepted:true,humanMinutes:20,usageCost:4,evidence:'https://example.org/a',quality:4,review:4}];return s}
test('default production state contains no demo pilot observations',()=>{assert.equal(validateState(demo),true);assert.equal(demo.meta.demo,false);assert.equal(demo.runs.length,0);assert.equal(demo.tasks.length,0);assert.ok(demo.platforms.length>0)});
test('empty workload yields no made-up distribution',()=>assert.equal(Object.values(normalizedMix(demo)).reduce((a,b)=>a+b,0),0));
test('missing evidence never produces a winner',()=>{let s=clone(demo);for(const p of s.platforms){s.gateResults[p.id]={};for(const g of s.gates)s.gateResults[p.id][g.id]='pass'}assert.equal(decision(s).type,'insufficient')});
test('failed governance gate blocks',()=>{let s=study();s.gateEvidence={codex:{retention:{status:'fail',url:'https://example.org/evidence',notes:'Control fails our requirement',reviewer:'Alex',reviewedAt:'2026-10-22T20:00:00Z'}}};assert.equal(gateStatus(s,'codex'),'fail')});
test('failed attempts count in success, human effort and cost',()=>{let s=study();const before=platformMetrics(s,'codex');s.runs.push({platform:'codex',task:'task1',accepted:false,humanMinutes:400,usageCost:100,quality:1,review:1});const after=platformMetrics(s,'codex');assert.ok(after.success<before.success);assert.ok(after.effort>before.effort);assert.ok(after.fullCost>before.fullCost)});
test('hourly labor rate affects full cost',()=>{let s=study(),m=platformMetrics(s,'codex').fullCost;s.org.rate=200;assert.ok(platformMetrics(s,'codex').fullCost>m)});
test('missing task types reduce coverage',()=>{let s=study();s.mix={Features:50,Debugging:50,Refactoring:0,Tests:0,Migration:0};assert.ok(platformMetrics(s,'codex').coverage<1)});
test('equal scores have stable order',()=>{let s=clone(demo);const ids=scorePlatforms(s).map(x=>x.id);s.platforms.reverse();assert.deepEqual(scorePlatforms(s).map(x=>x.id),ids)});

test('legacy pass cannot satisfy a mandatory requirement without evidence',()=>{const s=study();s.gateResults.codex=Object.fromEntries(s.gates.map(g=>[g.id,'pass']));assert.equal(gateStatus(s,'codex'),'unverified')});
