# H3 — Web, caching and final Full gate

Status: **IN_PROGRESS / H3-A LOCAL_CANDIDATE**. H2 acceptance remains scoped to published
`a5c80203df9de89e0d22a87d565533b38b23899a` and its exact Full/Shadow pair. The user instruction
“开始下一步” authorizes the next local H3 work; it does not grant push, Hosted runs, Required
Check/protection mutation, main merge, H4, paid API, M3 or real business resources.

## Active package: H3-A additive final gate

Base `6b4ab4a19bc47ca200f2821edc1d9e455194f2f5`; Root is sole writer in the existing
`codex/harness-v3` Worktree. Default Sol/medium; quota UNKNOWN, no paid fallback. A single
existing independent Sol Reviewer reviews the frozen package. Product UI NOT_APPLICABLE.

Outcome: the candidate Full workflow always attempts a final `merge-gate`, requiring actual
success of all five original jobs, the exact current GitHub checkout SHA and a successful
N01/foundation source SHA/tree output. Missing, unexpected, skipped, cancelled, failed,
unknown or stale inputs reject. It consumes only the current run's `needs` context; it does
not query a latest-success run, reusable author sample or arbitrary artifact. Existing PG,
Web and N01 validators still check their real artifacts before job success. This is a small
stdlib command in the existing workflow, not an approval platform or scheduling framework.

The original five job names, permissions, triggers, deadlines and complete execution contents
are retained. N01 adds only a final successful-source output; PG, frontend, full offline,
security and cleanup checks are unchanged. All paths conservatively require Full: no change
classifier or workflow path filters are introduced. The new gate is additive and is not yet
a branch-protection Required Check. There is no performance improvement claim for this package.

Important sequencing constraint: the existing complete `scripts.check` runs once, inside
N01 preparation. It includes npm installation/typecheck, which N01 repeats during its own
build preparation. Moving the complete check to a new optional job before a protected final
gate exists would weaken today's authoritative N01 gate. A trial local extraction was
therefore removed before freeze; this package does not introduce that new job. Keep the
complete check where it is until an approved, evidenced transition preserves enforcement.

GitHub documents that workflow path filtering can leave required checks Pending and that a
job skipped after dependency failure may not block merging; `always()` with `needs` is the
appropriate final-job pattern. Full cancellation can still prevent execution: no success is
inferred from absence. See [required-check behavior](https://docs.github.com/en/pull-requests/how-tos/merge-and-close-pull-requests/troubleshooting-required-status-checks)
and [job outputs](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/pass-job-outputs).

## Actual local verification

- Final H3-A focused suite: **233 passed / 12.01s**, covering merge-gate native CLI and
  workflow wiring plus existing PG/shard/N01/failure-sidecar contracts.
- New gate cases: each original job must actually succeed; missing/unexpected dependencies,
  absent/stale source outputs, mismatched checkout and malformed JSON reject. CLI success
  uses the actual local Git SHA/tree. Error messages do not echo untrusted context.
- Original consumer equivalence: all five original jobs match the accepted product workflow
  after removing only N01's new outputs and terminal source-binding step. No business test
  is retired; two workflow assertions are updated for the additive job/source output.
- Ruff, mypy for the new command/tests, and diff whitespace checks pass.
- First development command:199pass/39fail, consisting of one new test incorrectly forbidding
  the original pg-pair `always()` and38 existing sidecar cases missing project-local Node.
  The assertion was corrected; the existing Node24.21.0 installation was linked read-only
  into ignored `.tools/node`. A second run before that link had200pass/38environment failures.
  An intermediate extraction candidate passed238/12.11s but is not the frozen implementation
  or H3-A acceptance evidence. Final233/12.01s belongs to the retained-five-job implementation.
- No PG/Docker/browser service was started. Existing H2 Hosted evidence is retained, not
  recast as a new H3 run. H3 Hosted/cold-cache/warm-cache/performance acceptance: **NOT_RUN**.
- Independent review and final default dir/index/history scanner are recorded at freeze;
  do not infer their result from this candidate text.

## Next bounded work and acceptance boundary

Review Web preparation/build duplication and safe shared-build/cache candidates using the
same source and pinned tool/lock identity. Reuse existing runners and validators; do not cache
credentials, `.env`, PG state or sensitive logs. Preserve all original Required Checks until
an explicitly approved transition. Cache/build implementation is not included in H3-A.

Full H3 acceptance still requires the original contract's three comparable Hosted Full runs,
including clean and warm cache observations, complete PG/Web/N01/offline/security/resource
proof and an executable rollback. No such remote run is authorized by this local instruction.
H4-H5 remain NOT_STARTED. H3-A rollback is a normal revert of its additive gate and N01
output changes; original job bodies and branch protection need no restoration.
