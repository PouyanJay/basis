import test from 'node:test';import assert from 'node:assert/strict';
import {catalog,dimensions,evidenceFor,documentSummary} from '../technology.js';
test('technology claims each have primary HTTPS source and a recognized dimension',()=>{for(const c of catalog){for(const v of c.claims){assert.ok(dimensions.some(d=>d.id===v.dimension));assert.match(v.source,/^https:\/\//);assert.equal(v.status,'documented');assert.ok(v.claim.length>12)}}});
test('unknown features do not imply missing product capability',()=>{assert.deepEqual(evidenceFor('grok','automation'),[]);assert.equal(documentSummary().independentlyVerifiedClaims,0)});
