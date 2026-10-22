# SWE-bench Lite external evaluation

The built-in local Run button executes the small public integration task, not SWE-bench Lite. The old GitHub execution workflow has been removed.

For SWE-bench Lite, use the official suite instructions linked in **Run tests → External benchmarks**. Run the harness in an appropriately isolated environment with Docker and sufficient disk/RAM, then import authentic outcomes using the Basis report schema. API calls and grading can consume substantial resources.

The repository retains these command-line utilities for advanced external evaluations:

- `scripts/sample_swebench.py`: creates a deterministic, repository-balanced nested sample from the official 300-task Lite test split. Use `--percent`, `--seed`, `--revision`, and `--out`.
- `scripts/swebench_lite.py`: produces predictions with a selected CLI against the shared manifest.
- `scripts/grade_swebench.py`: invokes official Docker grading.
- `scripts/normalize_swebench.py`: translates authentic grading outcomes to the Basis report schema.
- `scripts/compare_swebench.py`: compares compatible reports.

These utilities are not connected to the local companion's credential store or run button. They require separate environment and dependency preparation. Consult each script's `--help` and the upstream suite documentation before execution. No provider-key live run or official grading has been validated here.

Import reports under **Run tests → External benchmarks**. Compare only matching dataset/harness revisions, task IDs, and evaluation conditions. Imported reports remain self-reported, unverified evidence; a sample is not an official leaderboard score.
