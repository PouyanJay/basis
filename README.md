# Basis — Iris production-safe starter

Static frontend for GitHub Pages, GitHub Actions agent execution and a local credential companion. **No synthetic vendor scores are preloaded.** The initial organizational profile and pilot results are empty, with all mandatory controls unverified. The candidate catalog contains real vendor names but no claims about their measured performance.

## Deploy
1. Upload repository files to GitHub, set GitHub Pages source to GitHub Actions.
2. Push to `main`; `.github/workflows/pages.yml` runs tests and stages only the public static assets.
3. For API keys, use the local credential companion (`python3 scripts/credential_companion.py`) and an authenticated `gh` CLI, or configure repository Actions Secrets yourself. **Never enter secrets into a public Pages form.**
4. Open the Actions workflow **Run coding-agent benchmark (public fixtures only)**, choose `claude`, `cursor`, `codex`, or `opencode`, and confirm public fixture. A provider key and current CLI compatibility are required. No mock vendor option exists.
5. Retrieve the `agent-result.json` artifact and import it from Agent Execution. A successful test is **automated technical evidence only**, not independent acceptance or a procurement decision.

## Evidence policy
- Every new study starts empty. Previous browser state under earlier app versions is not automatically migrated.
- Demo/mock result files are not included and mock records are rejected on import.
- Manually supplied records are **user-provided, unverified**. Verified eligibility requires independently reviewed, digest-linked records; the prototype does not yet have a UI workflow for reviewer sign-off. No procurement winner can be produced from unverified evidence.
- Technology Intelligence contains documented vendor facts with source URLs. 'Documented' does not mean experimentally verified.
- A rules-based help menu is **not a live AI advisor**. Devin and xAI are catalog entries, not working execution adapters.
- Run proprietary or hostile code only after hardening runner isolation and secret scoping.

## Tests
`npm test` and `python3 tests/ui_test.py` (Chromium + Playwright required).


## Community benchmark library

The **Benchmark library** tab lists official suites and supports strict imports of normalized, self-reported evidence. **It does not yet execute those external benchmarks.** Details and honest limitations: [BENCHMARKS.md](BENCHMARKS.md).
