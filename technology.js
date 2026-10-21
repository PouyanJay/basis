// Curated, narrowly scoped claims backed by primary vendor documentation.
// A documentation claim does NOT count as independent verification.
export const reviewedOn='2026-10-20';
export const dimensions=[
 {id:'automation',label:'Automated coding',icon:'flask'},
 {id:'model',label:'Model configuration',icon:'brain'},
 {id:'integration',label:'Workflow integration',icon:'link'},
 {id:'governance',label:'Governance evidence',icon:'shield'}
];
export const catalog=[
 {id:'claude',name:'Claude Code',website:'https://code.claude.com/docs/en/overview',claims:[{dimension:'automation',claim:'CLI and automated workflows are documented',source:'https://code.claude.com/docs/en/headless',status:'documented'}]},
 {id:'cursor',name:'Cursor',website:'https://cursor.com',claims:[{dimension:'automation',claim:'CLI non-interactive print mode is documented',source:'https://docs.cursor.com/en/cli/headless',status:'documented'},{dimension:'integration',claim:'CLI reads repository rules and configured MCP servers',source:'https://docs.cursor.com/en/cli/using',status:'documented'}]},
 {id:'devin',name:'Devin',website:'https://devin.ai',claims:[{dimension:'automation',claim:'API documentation for Devin sessions is available',source:'https://docs.devin.ai/api-reference/overview',status:'documented'}]},
 {id:'codex',name:'Codex',website:'https://developers.openai.com/codex/',claims:[{dimension:'automation',claim:'Codex CLI supports non-interactive exec',source:'https://developers.openai.com/codex/non-interactive/',status:'documented'}]},
 {id:'opencode',name:'OpenCode',website:'https://opencode.ai',claims:[{dimension:'automation',claim:'The run command supports non-interactive execution',source:'https://opencode.ai/docs/cli/',status:'documented'},{dimension:'model',claim:'CLI supports an explicit provider/model selection',source:'https://opencode.ai/v2/docs/cli/commands/',status:'documented'}]},
 {id:'grok',name:'xAI coding configuration',website:'https://docs.x.ai',claims:[]}
];
export function evidenceFor(id,dimension){return catalog.find(c=>c.id===id)?.claims.filter(c=>c.dimension===dimension)||[];}
export function coverageFor(id){const c=catalog.find(c=>c.id===id);return c?new Set(c.claims.map(x=>x.dimension)).size:0;}
export function documentSummary(){return {reviewedOn,documentedClaims:catalog.reduce((n,c)=>n+c.claims.length,0),platforms:catalog.length,independentlyVerifiedClaims:0};}
