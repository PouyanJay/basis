<div align="center">

<img src="brand.svg" width="72" height="72" alt="Basis precision star logo" />

# Basis

**Choose AI coding tools with evidence that fits your team.**

A workspace for comparing coding agents through your engineering needs, governance requirements, pilot results, and reproducible benchmark runs. Define what matters, collect evidence, and understand what is still missing before making a decision.

[![Live app](https://img.shields.io/badge/demo-open_Basis-b99af0?style=flat-square&logo=github&logoColor=white)](https://pouyanjay.github.io/basis/)
[![Checks and deployment](https://img.shields.io/github/actions/workflow/status/PouyanJay/basis/pages.yml?branch=main&style=flat-square&label=checks)](https://github.com/PouyanJay/basis/actions/workflows/pages.yml)
[![License: Apache 2.0](https://img.shields.io/badge/license-Apache_2.0-8b94a6?style=flat-square)](LICENSE)
[![JavaScript](https://img.shields.io/badge/JavaScript-ES_modules-f7df1e?style=flat-square&logo=javascript&logoColor=black)](package.json)
[![GitHub Pages](https://img.shields.io/badge/hosting-GitHub_Pages-222222?style=flat-square&logo=github&logoColor=white)](.github/workflows/pages.yml)

[Capabilities](#what-you-can-do) · [Quick start](#quick-start) · [Evidence model](#evidence-model) · [Agent execution](#agent-execution) · [Development](#development) · [Documentation](#documentation)

[**Open the live app →**](https://pouyanjay.github.io/basis/) · No account or API key required to explore the workspace.

<img src="docs/assets/basis-overview.png" width="1200" alt="Basis home screen with a guided first test, three evaluation stages, and simplified navigation" />

<sub>A new study starts with no pilot results or preloaded vendor scores.</sub>

</div>

## Why Basis exists

Choosing a coding agent involves more than a benchmark score. A tool needs to fit your codebase, satisfy your organization's controls, and deliver useful work after review, rework, and operating costs are included.

Basis brings those questions into one study. It connects an engineering profile, governance gates, task-level observations, and documented vendor capabilities, while keeping the provenance and limits of each result visible.

**Current status:** the static application is deployed and browser-tested. Local sample-task execution is implemented with OS credential storage and isolated Docker containers. Credentialed vendor runs and official SWE-bench grading have not yet been validated end to end. Imported results remain unverified evidence.

## What you can do

| Area | Purpose |
|---|---|
| **Home** | A suggested first test and a plain-language explanation of what runs where. |
| **Set up** | Team context, service selection, requirements, and task definitions with acceptance criteria. |
| **Run tests** | Run the included sample locally, record attempts from your own tasks, or import external benchmark evidence. |
| **Results** | Browse recorded pilot results, compare services, and review imported agent checks and external reports. |
| **Tool catalog** | Documented vendor capabilities and their primary sources. |
| **Settings** | Shared OS credential status and local evaluation data. |

The interface pairs neutral charcoal surfaces and compact Inter typography with restrained violet accents. The precision star mark anchors the sidebar and browser icon; the home screen introduces the evaluation workflow before showing detailed analysis. Layouts adapt to desktop and mobile screens. Study state is stored in your browser's local storage; it is specific to that browser and origin, with no shared database or account synchronization. A hard refresh preserves this data. Use **Settings → Reset evaluation** to clear the local study, imported results, and run settings; export the study and keep original report files first if you need them. Reset does not delete OS credentials or the companion’s latest run.

## Quick start

Use the [hosted app](https://pouyanjay.github.io/basis/) to explore the workspace. To save credentials and execute the included sample task, run Basis locally with Python 3.9+ and Docker:

```sh
git clone https://github.com/PouyanJay/basis.git
cd basis
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-local.txt
.venv/bin/python scripts/credential_companion.py
```

Open **http://127.0.0.1:8765/**. On Windows, use `.venv\Scripts\python.exe` instead. Start Docker before running a test. The frontend uses native JavaScript modules and has no build step.

### Your first test

1. **Set up → Requirements:** select your services.
2. **Set up → Credentials:** save the required keys once. Keys already saved through Settings show **Configured**; there is no need to enter them again.
3. **Run tests → Small test run:** choose optional models, confirm provider API usage, and click **Run selected services**.
4. Watch progress and results automatically. The first run builds the container image and may take several minutes.
5. Review checks under **Results**. Passing automated checks does not establish independent human acceptance.

No fork, GitHub login, repository secrets, workflow dispatch, or artifact download is required. GitHub secrets previously saved by the old helper cannot be retrieved; enter those keys locally once. The same keys are then available in Settings and Set up.

**What runs where:** the browser stores your study, the OS credential store holds API keys, and the local companion executes the included public fixture in disposable Docker containers. External benchmark suites and user-defined tasks are not automatically executed by the sample-task runner.

For a broader team evaluation, use **Set up → Tasks** to define tasks and acceptance criteria. Perform the tasks with your selected services outside Basis, then use **Run tests → Record a result** to log each attempt, including failures, human effort, usage cost, and evidence. Saved attempts appear under **Results → Pilot results**. The **Fair testing guide** is available from Help, Tasks, and Record a result. **Run tests → External benchmarks** contains upstream suite instructions and external report import. **Results** keeps these evidence sources separate and offers deeper pilot comparison, review quality, and decision summary tabs.

## Evidence model

Basis keeps documented capabilities, automated checks, and independent acceptance distinct.

| Evidence | What it establishes |
|---|---|
| **Documented vendor capability** | A sourced claim about a tool; it is not an experimentally verified result. |
| **Manual observation or imported report** | User-provided evidence, treated as self-reported and unverified. |
| **Automated test result** | Technical evidence from a specific task and run; it does not establish human acceptance. |
| **Independently reviewed, digest-linked record** | Required for verified eligibility. The prototype does not yet provide a reviewer sign-off UI. |

New studies contain no synthetic vendor scores or pilot results, and mock records are rejected on import. Unverified evidence cannot produce a procurement winner. Benchmark comparisons require matching dataset and harness versions, task sets, and evaluation conditions; a sampled run is not an official leaderboard score.

The help menu is rules-based. Devin and xAI appear in the candidate catalog but do not have working execution adapters.

## Agent execution

The local runner supports these adapters:

| Agent | Identifier | OS credential entry |
|---|---|---|
| Claude Code | `claude` | `ANTHROPIC_API_KEY` |
| Cursor | `cursor` | `CURSOR_API_KEY` |
| Codex | `codex` | `OPENAI_API_KEY` |
| OpenCode | `opencode` | `OPENAI_API_KEY` for `openai/model`, or `ANTHROPIC_API_KEY` for `anthropic/model` |

Each selected supported service receives the same public Python addition task in a fresh container. Devin, xAI, and custom services remain manual evaluations and are clearly excluded from automatic execution.

### Credentials and execution boundaries

Credentials are stored using the OS credential store (macOS Keychain, Windows Credential Locker, Linux Secret Service or KWallet). Basis returns presence flags only, never stored values. **Configured** confirms storage, not provider validity or remaining credit. Keys can be replaced from either Settings or Set up. They are not written to browser storage, exports, build layers, or source files.

Containers run as an unprivileged user with a read-only root, temporary writable directories, dropped capabilities, and CPU, memory, process and time limits. They receive only the selected provider key and have no host-directory or Docker-socket mounts. Network access remains enabled for provider calls. The local Docker administrator can inspect container environments. This is a public-fixture runner, not a general-purpose sandbox for arbitrary repositories.

The companion binds to loopback, validates Host and Origin, requires a session token for API requests, and serves only allowlisted frontend assets. It saves the latest run summary under `~/.local/share/basis/latest-run.json` with restricted file permissions. The browser automatically polls progress and reads results; no agent logs or code diffs are published. Restarting the companion preserves completed results; an interrupted run is reported as interrupted.

### External benchmarks

External suites are run separately with their official harnesses and imported through **Run tests → External benchmarks**. The old GitHub launch workflows have been removed. See [SWEBENCH_SETUP.md](SWEBENCH_SETUP.md) for the scope of the retained command-line tools. Official grading and live provider compatibility still need independent validation.

## How it works

```mermaid
flowchart LR
    Setup[Set up services and tasks] --> App[Local browser workspace]
    App <-->|Credential status| Companion[Local companion]
    Companion <-->|Keys| Vault[OS credential store]
    Companion --> Containers[Isolated sample-task containers]
    Containers --> Reports[Automated check summaries]
    Reports --> Companion
    Companion -->|Automatic progress and results| App
    App <-->|Study state| Storage[Browser local storage]
```

## Development

Use Node.js 22, matching CI, and Python 3. Browser checks additionally require Playwright and Chromium.

```sh
# Core logic, benchmark report validation, and deterministic sampling
npm test
python3 -m unittest discover -s tests -p test_sampling.py -v

# JavaScript syntax checks
node --check app.js
node --check technology.js

# Browser checks
python3 -m venv .venv
source .venv/bin/activate
python -m pip install playwright
python -m playwright install chromium
python tests/ui_test.py
python tests/local_ui_test.py
python -m unittest discover -s tests -p test_credential_companion.py -v
```

On Linux runners, install browser system dependencies with `python -m playwright install --with-deps chromium`.

The main browser check covers grouped navigation, shared credential detection, local run prerequisites, automatic results, scenario cost editing, task creation, governance persistence, mobile overflow, responsive navigation, and page errors. Screenshots are saved to the ignored `test-results/ui/` directory.

### Project layout

```text
index.html                 Static application entry point
app.js                     Interface, browser state, and interactions
core.js                    Study model, evaluation logic, and validation
technology.js              Vendor capability catalog and source links
benchmarks.js              Benchmark catalog and report validation
styles.css                 Neutral workspace theme and responsive layouts
brand.svg                  Precision star mark and browser icon
scripts/                   Agent execution, grading, sampling, and helpers
fixtures/agent_task/       Public coding task for integration runs
benchmark-tests/           Checks used by the agent evaluation pipeline
tests/                     JavaScript, Python, and browser checks
.github/workflows/         Deployment, tests, and source health checks
docs/assets/               README screenshots
```

## Deployment

In your repository, enable **Settings → Pages → Source → GitHub Actions**. Pages must be enabled before the deployment action can create a site.

Every push to `main` runs the [Pages workflow](.github/workflows/pages.yml): JavaScript tests, Python sampling tests, syntax checks, and browser QA. After verification, it stages only `index.html`, `app.js`, `core.js`, `technology.js`, `benchmarks.js`, `styles.css`, and `brand.svg`, then deploys that artifact to GitHub Pages. The staging script gives assets content-versioned filenames and rewrites module imports so each deployment loads matching JavaScript and styles instead of cached files from a previous release.

## Documentation

| Guide | Contents |
|---|---|
| [SWE-bench Lite setup](SWEBENCH_SETUP.md) | Provider keys, runner requirements, sampling, grading, and run limitations. |
| [Benchmark library](BENCHMARKS.md) | Report schema and upstream suite references. |
| [Execution status](EXECUTION_STATUS.md) | Execution boundaries and outstanding provider validation. |
| [Implementation plan](IMPLEMENTATION_PLAN.md) | Project implementation notes and planned work. |

## Contributing

Issues and pull requests are welcome. Include reproduction steps for bugs, source links for capability changes, and the relevant checks for code changes. Keep benchmark provenance explicit and preserve the distinction between automated results and independently accepted evidence.

## License

[Apache License 2.0](LICENSE). External benchmark datasets, harnesses, and provider tools retain their own licenses and terms.
