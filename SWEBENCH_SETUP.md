# SWE-bench Lite · production run setup

**Status:** Workflow and UI implemented; no provider-key live SWE-bench Lite run or official Docker grading has been performed here. Successful deployment and grading is therefore NOT yet demonstrated.

## Start a run

1. Push this project to the default branch of a repository containing the Actions workflow, preferably a **private evaluation repository** (GitHub Pages can be public separately). Set Pages → Source to GitHub Actions.
2. Set the relevant provider API key in repository **Actions Secrets** (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, or `CURSOR_API_KEY`). Never enter keys in Pages. For OpenCode choose provider/model explicitly.
3. Configure an appropriately isolated runner with **>40 GB free disk**, Docker available, and ample RAM; set repository Actions variable `SWE_BENCH_RUNNER` to that runner's exact label. Default `ubuntu-latest` may fail preflight for insufficient resources. GitHub-hosted standard runners should not be assumed sufficient for grading.
4. In Basis → Benchmark library choose percentage (1–100), seed, agents and repository. Open the workflow through the UI and input the displayed values in GitHub Actions; confirm costs. Task selection is **repo-balanced and deterministic** using the official Lite test dataset at its resolved immutable commit. The selection is a nested progressive design but is **not an official statistically certified stratification**.
5. The workflow creates one shared `selected.json`, launches a separate evaluation job for every agent, creates patches, then grades against the official SWE-bench Docker harness. If a job fails before grading, no verified outcome is produced. The job may time out for larger samples; this release does not yet implement checkpointed multi-job shards.
6. Download `basis-report.json` from each successful job's artifact, import under Benchmark Library. The app treats imported results as self-reported and unverified; compare only identical dataset, harness and task IDs. Do not publish agent traces containing confidential material.

## Meaning of a score

- 10% = 30 unique official tasks; 25% = 75; 100% = all 300. Same seed means 25% includes the 10% sequence.
- Tasks that fail generation or produce empty patches must be counted in the chosen denominator; the scorer must show `not_graded` where no official outcome exists.
- Incomplete/error runs and missing test evidence are **not** verified successes.
- A sampled result is **not** an official leaderboard score and is not adequate on its own for organization procurement.

## Security and limits

- GitHub-hosted runners execute third-party agent-written code and may be exposed to prompt injection. Use restricted keys, preferably task-scoped/ephemeral identities, least privilege and a private isolated runner. The current Actions workflow injects provider keys into the run that executes an agent. **Do not use it with untrusted or proprietary task repositories without additional isolation.**
- GitHub Pages cannot safely directly dispatch workflows without user authorization; the app opens the GitHub Actions workflow with clear inputs. This is an intentional human authorization step, not true one-click execution.
- Official SWE-bench grader can download large Docker layers, consume many hours, and incur paid compute. A single long run might exceed Actions timeouts. Chunking/resume and secure artifact auto-sync are future requirements.
- Version pinning of the pip harness and CLIs should be hardened and integration-tested in your specific runner before relying on output. This release records the installed harness version, not an exact upstream git commit.

Primary references: [SWE-bench evaluation guide](https://github.com/SWE-bench/SWE-bench/blob/main/docs/guides/evaluation.md); [SWE-bench code](https://github.com/SWE-bench/SWE-bench).
