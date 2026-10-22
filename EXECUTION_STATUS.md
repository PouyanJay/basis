# Execution status

- The local companion supports the included public sample task with Claude Code, Cursor, Codex and OpenCode in disposable Docker containers.
- Settings and Set up share OS credential storage. Presence is checked without returning key values. Presence does not verify provider validity.
- GitHub execution workflows and setup steps have been removed. GitHub Actions remains for repository checks, source health, and publishing the static website.
- The container image and installed CLIs are tested locally. Browser/backend tests use isolated test credentials and simulated runs; they are not vendor performance evidence.
- No paid, credentialed vendor run has been performed as part of this change. Provider API compatibility and official SWE-bench grading remain unverified end to end.
- The local Run button executes only the included sample task. Custom tasks require manual execution and result recording. External suites require their own harness and report import.
- Automated checks never become independently accepted pilot observations automatically.
