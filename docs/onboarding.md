# Onboarding a dataset

Ask the agent for a dataset ("add <dataset> from <publisher>"), in its own worktree:
`claude -w onboard-<source>`. The [`onboard-dataset`](../.agents/skills/onboard-dataset/SKILL.md) skill
runs the workflow with the defaults of [ADR 0003](adr/0003-onboarding-defaults.md); its artefacts stay in
`data/onboarding/<source>/` in the worktree.

| Phase | Agent | You |
|---|---|---|
| 1. Intake | records the request | name the dataset; add what you know (use, latency, history) |
| 2. Profile and design | fetches documentation and real samples, profiles them | |
| 3. Scope review | proposes the design with the evidence, the backfill options and any exceptions | choose the horizon, confirm exceptions |
| 4. Deliver | builds the pipeline, contracts and tests; runs an acceptance run on the real publisher | |
| 5. Acceptance | reports the criteria, the profile, deviations and how to inspect the data | accept or ask for revisions; ask for the merge and the backfill |

Each report ends with a retrospective on the workflow, which is how the skills improve between sessions.
