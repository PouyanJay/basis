# Basis engineering plan and delivery ledger

## Product boundary
A static GitHub Pages Iris interface can compare evidence and source claims. It cannot directly run coding agents or protect API keys. GitHub Actions performs asynchronous execution. Real-time conversations require a secure local companion or backend; embedding provider secrets in Pages is disallowed.

## Implemented and tested in this version
- Multi-candidate study, editable Engineering DNA and workload mix.
- Governance gates, task catalog, pilot evidence entry, exploratory metrics and eligibility states.
- Iris technology matrix with narrowly scoped primary-source claims, unknown states, review date and source links.
- Source-health workflow checks URL accessibility; does not prove the truth of a claim.
- GH Pages deployment workflow with Node and browser checks before publish.
- Safe-by-default fixed-command verifier for an explicitly supplied fixture directory, JSON output, bounded timeout, no vendor API keys.
- Demo result relabeling blocked; synthetic runs must be cleared first.

## Not implemented; required before real evaluation product claims
### P0 Provenance and correctness
1. Migrate browser data to versioned signed result bundles with JSON Schema validation, immutable task/agent/runner metadata, hash of repository snapshot and artifact digests.
2. Replace exploratory weighted-score formula (which is relative to included candidates) with preregistered acceptance, inference, baseline, per-task strata, uncertainty intervals, sensitivity thresholds and missing-data rules.
3. Implement reviewer attestation, dual approval for acceptance, blind judges with swap tests, reference-set calibration and exclusion of conflicted models.
4. Quantify actual human time and total cost, include retries/failures, amortization horizon and latency.
### P1 Real execution
5. Build vendor adapters for Claude Code, Cursor CLI, Codex exec, OpenCode and Devin API; xAI by specified integration. Pin concrete models, CLI versions, credentials and policy configuration. Never infer interchangeability of IDE and CLI workflows.
6. Create a trusted orchestration workflow separate from untrusted agent runs; isolate networks, remove repository write tokens, restrict filesystem, enforce time, token, dollar and concurrency limits. Avoid exposing hidden tests.
7. Add post-run verifier workflows with hidden tests, security scans, independent code review, diff and PR artifacts; support explicit manual-mode runs for tools without API integration.
8. Add a managed benchmark catalog, representative task sampling and fixed seed/assignment methodology.
### P2 Organization intelligence and advisor
9. Read-only GitHub/GitLab adapters that collect approved repository/PR metadata; never send code to a model by default. Workload classifications require user review.
10. Verified technology source registry with extraction snapshots, provenance, plan/version restrictions, change detection, archived copies and reviewer sign-off. UI reflects changes with evidence chips rather than auto-updating definitive claims.
11. Secure optional local companion for streaming advisor and judge API calls, with explicit user-supplied credentials, grounding and human review. Keep assistant and judging decisions separate.
### P3 Productization and QA
12. Cross-browser and keyboard accessibility audits, contrast checks, full journey Playwright tests, UI screenshot baselines and mobile layouts.
13. Reliability tests for outages, malicious outputs, stale/contradictory source claims, timeout/cancellation, prompt injection, unknown controls, poisoned benchmarks and insufficient samples.
14. Export reproducible decision packages and an independently auditable scoring report. Then run pilot with real paid tool accounts and organizational review.

## Acceptance criteria
- No demo or unattributed evidence can result in a procurement winner.
- Required failed/unverified governance control prevents eligible decision.
- A claim's date, original link, conditions and review status are available without occupying the main interface.
- Same task/repository snapshot and acceptance checks for comparable candidates.
- Every non-deterministic judgment includes judge configuration, blinded source, disagreement and reviewer reference.
- Browser tests pass before pages deployment; fixture run verified; secrets never stored in static code.
- Before a real organizational decision: manual review of all source claims, statistical analysis and independent security review.
