# CURRENT_STATE

Product authority snapshot: 2026-10-28 15:22:10 UTC; product facts retained.
Local Harness state reviewed at 2026-10-30 12:22:49 UTC.
Run `uv run --frozen python -m scripts.current_state --json` for live local Git facts.

- Product: M2 / Phase5 accepted and [#49 closed](https://github.com/aning0922/commerceops-agent/issues/49); M3 is unapproved.
- Accepted main: `6d3a8f7bf3d36c6c1dcfd5072a3297be4cc88265` / tree `ac92562c26d24eb183143e52de64e5a51282948c`.
- Last accepted Full CI: [40432280677](https://github.com/aning0922/commerceops-agent/actions/runs/40432280677), per
  [authority receipt](https://github.com/aning0922/commerceops-agent/issues/49#issuecomment-6430237354). This is historical product evidence.
- Active engineering task: [#51 open](https://github.com/aning0922/commerceops-agent/issues/51); its title still says V2, while the
  authorized implementation material is Harness V3.
- Harness: H0 local candidate B Gate accepted; H1 LOCAL_GATE_ACCEPTED at 17e2e1af5e77b1c09b1de45d51c357a8e4da1dd4; integrated Hosted evidence belongs to H2 published head a5c80203;
  Published226917d4dba57bdb2eef54180df97e57510e4169 Full/Shadow attempt2 evidence retained, both PASS; warm hits confirmed, material cache net saving not established, Full44m03s. Local Full candidate now reuses existing six-shard plan/native/aggregate with unchanged required contexts and Web/N01/final gate; legacy path remains in exact Git history. New topology Hosted and performance NOT_RUN; no prior result transferred. H3IN_PROGRESS_NOT_ACCEPTED; H4-H5NOT_STARTED.
- H0 handoff: `c3dd84e2ce36e03a7658bcd266cf6f442da877b5`; code freeze `b0d61e73f924f84d4afaf319131597b78aedda40` in
  `/Users/aipuli/Documents/Projects/commerceops-harness-v3-h0-20261028`.
- Model policy: gpt-6.1-sol / medium by default; Astra requires scoped approval. Model
  availability was catalog-only in H0; inference NOT_RUN. Quota/token usage UNKNOWN, no
  reservation claimed, no paid API fallback.
- Authorized scope: User approved local Full topology candidate reusing existing six shards, all business/security/recovery/evidence gates and exact old-path rollback retained. No push/Hosted/protection/main/H4/M3/paidAPI/business resources.
- [Old ARM64 CI stopped](https://github.com/aning0922/commerceops-agent/issues/46#issuecomment-6138014477); preserve its Worktree and WIP.
- Next Gate: see [handoff](docs/harness/HANDOFF.md). Fast/Impacted give local feedback;
  existing Full required gates remain authoritative. Published a5c80203 passed its exact
  Hosted Full/Shadow pair; this local Harness candidate has no new Hosted run.

Navigation: [H1 usage](docs/harness/README.md), [TaskSpec
example](docs/harness/task.example.json), [handoff](docs/harness/HANDOFF.md),
[decisions](docs/DECISIONS.md), [historical status](docs/STATUS.md), [original
AGENTS](AGENTS.history-20261028.md).

`CURRENT_STATE.md` is the only current summary. Older AGENTS/STATUS/ROADMAP entries retain
their original dates; they do not reopen accepted product work. Refresh requires reading
Git/Issue/PR authorities, reviewing the compact snapshot and changing its hash pin; Issue prose
is never executable policy.
