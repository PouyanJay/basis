# Basis Community Benchmark Library

## What is implemented

- Research-backed catalog of established suites with links to the upstream maintained harnesses.
- Iris dark-mode navigation and friction-reduced discovery screen.
- Strict, consistent Basis benchmark result schema; duplicate run/task protection; no seeded scores.
- Browser-only import of reports, explicitly labeled self-reported/unverified.
- Desktop/mobile Playwright checks and Node validation tests.

## What is not implemented

- This release **does not automatically run SWE-bench, Terminal-Bench, or SWE-bench Pro**. Their runner implementations, specialized resources, agent-specific adapters, and native report converters are not bundled.
- Imports are self-reported. Hashes/metadata supplied by user are not cryptographic attestation. An external user could falsify input; Basis does not certify imported results.
- Do not compare runs from different benchmark versions, task subsets, judge settings, timeouts, models or agent modes.
- Commercial/held-out datasets and their answer keys are NOT included.

## Recommended execution order

1. Use official SWE-bench Lite harness with a small pinned subset on adequately sized isolated runner. Capture patch predictions, task results and exact harness/dataset SHA.
2. Write and test a native SWE-bench result converter; capture failures/timeouts and match exact task sets across platforms.
3. Integrate agents under the same time budget, allowed tools and starting Git snapshot.
4. Add Terminal-Bench 2.1 with Harbor in dedicated containers, including version-pinned adapter for each vendor.
5. Add SWE-bench Pro open-source subset; use its official verifier and resource recommendations.
6. Implement signed artifact ingestion and direct GitHub Actions artifact retrieval (without browser-exposed secrets).
7. Run golden-result validation and metamorphic tests to ensure the evaluator is correct before publishing leaderboards.

## Basis report format

Import a JSON object such as:

```json
{
  "type": "basis-community-benchmark-report",
  "schemaVersion": 1,
  "benchmarkId": "swebench-lite",
  "datasetRevision": "<real 40-to-64 character commit or content hash>",
  "harnessRevision": "<real 40-to-64 character commit or content hash>",
  "agent": "Codex CLI",
  "model": "<actual model ID>",
  "executionMode": "CLI",
  "runId": "<unique actual run ID>",
  "provenance": "external-official-harness",
  "verified": false,
  "humanAccepted": false,
  "tasks": [
    {"id":"<real upstream task id>","status":"resolved","durationSeconds":42.5}
  ]
}
```

The above is a **schema illustration only**, not a benchmark result. For real output, values must be extracted from the actual official harness. In particular, do not invent duration data when the official tool does not record it. The current schema requires duration; the future native converters should add explicit missing-value support.

## Official sources

- SWE-bench: https://github.com/SWE-bench/SWE-bench
- SWE-bench CLI: https://github.com/SWE-bench/SWE-bench/blob/main/docs/reference/cli.md
- Terminal-Bench 2.1: https://www.tbench.ai/news/terminal-bench-2-1
- Harbor: https://www.tbench.ai/news/announcement-2-0
- SWE-bench Pro open harness: https://github.com/scaleapi/SWE-bench_Pro-os
