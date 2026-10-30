# CURRENT_STATE

Product authority snapshot: 2026-10-28 15:22:10 UTC; product facts retained.
Local Harness state reviewed at 2026-10-30 07:35:07 UTC.
Run `uv run --frozen python -m scripts.current_state --json` for live local Git facts.

- Product: M2 / Phase5 accepted and [#49 closed](https://github.com/aning0922/commerceops-agent/issues/49); M3 is unapproved.
- Accepted main: `6d3a8f7bf3d36c6c1dcfd5072a3297be4cc88265` / tree `ac92562c26d24eb183143e52de64e5a51282948c`.
- Last accepted Full CI: [40432280677](https://github.com/aning0922/commerceops-agent/actions/runs/40432280677), per
  [authority receipt](https://github.com/aning0922/commerceops-agent/issues/49#issuecomment-6430237354). This is historical product evidence.
- Active engineering task: [#51 open](https://github.com/aning0922/commerceops-agent/issues/51); its title still says V2, while the
  authorized implementation material is Harness V3.
- Harness: H0 local candidate B Gate accepted; H1 LOCAL_GATE_ACCEPTED at 17e2e1af5e77b1c09b1de45d51c357a8e4da1dd4; integrated Hosted evidence belongs to H2 published head a5c80203;
  H2 ACCEPTED for published a5c80203df9de89e0d22a87d565533b38b23899a / merge d6d88c2468d4b1e66823153dface05a6cbba8294 / tree 8910865f0bfc577236bdbbe57a7adedd7f55ca36; Full41010032206 and Shadow41010032199 SUCCESS attempt1/both590PG/G1three/G2six/native0/cleanup0, independently ACCEPTED. H3 IN_PROGRESS: local H3-A code992f6f77823e1b4e83d6fb580627ae3a219d9249 adds fail-closed final gate/current source binding, preserves all original five consumer bodies and checks; focused233pass/12.01s. New candidate Hosted/performance/cold-warm acceptance NOT_RUN; no H2 evidence transplanted to H3 SHA. H4-H5 NOT_STARTED.
- H0 handoff: `c3dd84e2ce36e03a7658bcd266cf6f442da877b5`; code freeze `b0d61e73f924f84d4afaf319131597b78aedda40` in
  `/Users/aipuli/Documents/Projects/commerceops-harness-v3-h0-20261028`.
- Model policy: gpt-6.1-sol / medium by default; Astra requires scoped approval. Model
  availability was catalog-only in H0; inference NOT_RUN. Quota/token usage UNKNOWN, no
  reservation claimed, no paid API fallback.
- Authorized scope: User next-step instruction authorizes local H3 engineering/checks/independent review/freeze in existing owned Worktree. No push/new Hosted CI/Required Check or protection mutation/main merge/H4/M3/paid API/business resources. Prior one-pair grant SPENT; no retry.
- [Old ARM64 CI stopped](https://github.com/aning0922/commerceops-agent/issues/46#issuecomment-6138014477); preserve its Worktree and WIP.
- Next Gate: see [handoff](docs/harness/HANDOFF.md). Fast/Impacted give local feedback;
  existing Full required gates remain authoritative. Published a5c80203 passed its exact
  Hosted Full/Shadow pair; this later metadata-only handoff has no new Hosted run.

Navigation: [H1 usage](docs/harness/README.md), [TaskSpec
example](docs/harness/task.example.json), [handoff](docs/harness/HANDOFF.md),
[decisions](docs/DECISIONS.md), [historical status](docs/STATUS.md), [original
AGENTS](AGENTS.history-20261028.md).

`CURRENT_STATE.md` is the only current summary. Older AGENTS/STATUS/ROADMAP entries retain
their original dates; they do not reopen accepted product work. Refresh requires reading
Git/Issue/PR authorities, reviewing the compact snapshot and changing its hash pin; Issue prose
is never executable policy.
