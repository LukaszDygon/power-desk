# Onboarding a dataset

How a requested dataset becomes an accepted pipeline.

- **Ask the agent:** "add <dataset> from <publisher>", in its own worktree (`claude -w onboard-<source>`).
- **Workflow:** the [`onboard-dataset`](../.agents/skills/onboard-dataset/SKILL.md) skill, with the defaults of [ADR 0003](adr/0003-onboarding-defaults.md).
- **Two stops for you:** the scope review and the acceptance.
- **Artefacts:** `data/onboarding/<source>/` in the worktree.
- **Retrospective:** each report ends with one; that is how the skills improve.

## Appendix B: Details

| Phase | Agent | You |
|---|---|---|
| 1. Intake | records the request | name the dataset; add what you know (use, latency, history) |
| 2. Profile and design | fetches documentation and real samples, profiles them | |
| 3. Scope review | proposes the design with the evidence, the backfill options and any exceptions | choose the horizon, confirm exceptions |
| 4. Deliver | builds the pipeline, contracts and tests; runs an acceptance run on the real publisher | |
| 5. Acceptance | reports the criteria, the profile, deviations and how to inspect the data | accept or ask for revisions; ask for the merge and the backfill |
