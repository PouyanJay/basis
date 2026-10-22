# Execution status

- Set up → Run evaluation → Evaluation results is implemented. Setup tasks execute automatically in isolated local folders, with optional HumanEval or local benchmark packs.
- Plans and source/check snapshots are frozen at run start. Run history, completed evidence, and human reviews persist locally. Cancellation preserves partial evidence; restarting marks unfinished runs interrupted.
- Settings and Set up share OS credential presence checks. Saved does not imply provider validity.
- Agents cannot access the held-out checks. The separate verifier has no provider keys or network. Original source folders and the Docker socket are never mounted.
- HumanEval uses pinned original tasks and checks through a Basis adapter, not the official completion sampling harness or leaderboard protocol. SWE-bench and Terminal-Bench official harness runs remain external imports.
- Test commands, source and check digests, model selection, task identity, and limits are saved. Unpinned CLI defaults are explicitly labeled. Actual provider costs remain unknown unless entered by a reviewer; no monetary cap is claimed.
- A passing test never auto-verifies governance controls or human acceptance. Reviews remain self-reported evidence.
- Automated browser and backend tests use temporary stores and simulated agents. Container integration checks use a test-only agent and canonical benchmark solutions, not paid provider calls or production performance evidence.
- Credentialed vendor API calls remain unverified end to end. The UI surfaces agent errors/timeouts instead of fabricating successful outcomes.
- Legacy standalone fixture scripts remain for development, but the sample-task workflow is removed from the application.
