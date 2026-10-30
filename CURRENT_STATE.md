# CURRENT_STATE

Product authority snapshot: 2026-10-28 15:22:10 UTC; product facts retained.
Local Harness state reviewed at 2026-10-30 01:54:27 UTC.
Run `uv run --frozen python -m scripts.current_state --json` for live local Git facts.

- Product: M2 / Phase5 accepted and [#49 closed](https://github.com/aning0922/commerceops-agent/issues/49); M3 is unapproved.
- Accepted main: `6d3a8f7bf3d36c6c1dcfd5072a3297be4cc88265` / tree `ac92562c26d24eb183143e52de64e5a51282948c`.
- Last accepted Full CI: [40432280677](https://github.com/aning0922/commerceops-agent/actions/runs/40432280677), per
  [authority receipt](https://github.com/aning0922/commerceops-agent/issues/49#issuecomment-6430237354). This is historical product evidence.
- Active engineering task: [#51 open](https://github.com/aning0922/commerceops-agent/issues/51); its title still says V2, while the
  authorized implementation material is Harness V3.
- Harness: H0 local candidate B Gate accepted; H1 LOCAL_GATE_ACCEPTED at 17e2e1af5e77b1c09b1de45d51c357a8e4da1dd4 under PF-1; candidate Full NOT_RUN;
  H2 fifth head1be2c0f/merge4f82de96: Shadow40984497438 SUCCESS590actual passes/18m54s; original Full40984497286 FAIL phase3native139 (578/590passed), root causeUNKNOWN, cleanup0/pairreject; H2 NOT_ACCEPTED; no retry, H3-H5 NOT_STARTED; local A/B accepted, remote grantSPENT.
- H0 handoff: `c3dd84e2ce36e03a7658bcd266cf6f442da877b5`; code freeze `b0d61e73f924f84d4afaf319131597b78aedda40` in
  `/Users/aipuli/Documents/Projects/commerceops-harness-v3-h0-20261028`.
- Model policy: gpt-6.1-sol / medium by default; Astra requires scoped approval. Model
  availability was catalog-only in H0; inference NOT_RUN. Quota/token usage UNKNOWN, no
  reservation claimed, no paid API fallback.
- Authorized scope: Local Harness H0-H5 only; remote publication/CI, global services, business secrets/resources and M3 require separate authorization.
- [Old ARM64 CI stopped](https://github.com/aning0922/commerceops-agent/issues/46#issuecomment-6138014477); preserve its Worktree and WIP.
- Next Gate: see [handoff](docs/harness/HANDOFF.md). Fast/Impacted give local feedback;
  existing Full required gates remain authoritative and are NOT_RUN for this candidate.

Navigation: [H1 usage](docs/harness/README.md), [TaskSpec
example](docs/harness/task.example.json), [handoff](docs/harness/HANDOFF.md),
[decisions](docs/DECISIONS.md), [historical status](docs/STATUS.md), [original
AGENTS](AGENTS.history-20261028.md).

`CURRENT_STATE.md` is the only current summary. Older AGENTS/STATUS/ROADMAP entries retain
their original dates; they do not reopen accepted product work. Refresh requires reading
Git/Issue/PR authorities, reviewing the compact snapshot and changing its hash pin; Issue prose
is never executable policy.
