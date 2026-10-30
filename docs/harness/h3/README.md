# H3 — Web, caching and final Full gate

Status: **IN_PROGRESS / H3-A LOCALLY_ACCEPTED / H3-B LOCALLY_REVIEWED**. H2 acceptance remains scoped to published
`a5c80203df9de89e0d22a87d565533b38b23899a` and its exact Full/Shadow pair. The user instruction
“开始下一步” authorizes the next local H3 work; it does not grant push, Hosted runs, Required
Check/protection mutation, main merge, H4, paid API, M3 or real business resources.

## Accepted package: H3-A additive final gate

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
- Actual current collection:2960offline/590integration, no deleted business tests; collection
  command exit0/wall4.599212s. Collection is not execution of the whole suite.
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
an explicitly approved transition. Cache/build implementation is not included in H3-A; H3-B below is its bounded continuation.

Full H3 acceptance still requires the original contract's three comparable Hosted Full runs,
including clean and warm cache observations, complete PG/Web/N01/offline/security/resource
proof and an executable rollback. No such remote run is authorized by this local instruction.
H4-H5 remain NOT_STARTED. H3-A rollback is a normal revert of its additive gate and N01
output changes; original job bodies and branch protection need no restoration.

## Active package: H3-B local Web preparation and public npm cache

Base `6602e7615014a86ac445d79527a3576631b86a15`. The existing Sol Reviewer has now ACCEPTED
H3-A's five-file metadata delta without rerunning checks; earlier capacity failures remain
recorded. Same Root writer/Worktree/branch, local-only grant, no model escalation/API fallback.

N01 removes only its second `npm ci --ignore-scripts`, `check:toolchain` and `typecheck`.
The unchanged complete `scripts.check` still performs all three on this same checkout,
inside the same immutable deadline before production build. No new optional job substitutes
for a protected check. Frontend's own checks and all PG/Web/N01/security/audit/cleanup gates
remain. The same exact reconstruction test compares all original consumer bodies after
accounting only for these explicit duplicates, H3-A source output and public-cache steps.

Both Web jobs use pinned official actions/cache v4.3.0
`0057852bfaa89a56745cba8c7296529d2fc39830` (read-only official tag API verified). The sole cache
path is `${runner.temp}/commerceops-npm/_cacache`, with no restore-prefix fallback. No
node_modules, .next, Playwright binaries, uv environment, .env, auth configuration, logs,
evidence or PG state is saved. The key includes OS/arch/ubuntu24/actual ImageVersion,
Python/Node/npm/uv/Playwright/action versions and package/package-lock/.npmrc/uv.lock/tool pin
hashes. Native ImageVersion is read explicitly rather than assuming a runner variable is
available in the GitHub expression env context. Missing/malformed image identity or a lock
entry lacking integrity/public HTTPS npm registry origin disables caching; installation and
all checks still run. Current lock has92 public integrity-pinned package entries.

A cache hit never skips installation or any check. npm ci still uses the lock and integrity
verification. PR caches remain subject to GitHub merge-ref isolation; no cache-mode override,
privileged event, additional token or write permission is introduced. References:
[npm cache integrity](https://docs.npmjs.com/cli/cache/),
[GitHub cache scope](https://docs.github.com/en/actions/reference/workflows-and-actions/dependency-caching).

Actual native macOS/ARM experiment, fixed Node24.21.0/npm11.19.0, unchanged frontend source
and lock, task-owned fresh cache/HOME and empty npm user/global config, no provider credentials:

| Command scope | Native exit | Wall seconds |
|---|---:|---:|
| Empty public cache npm ci |0|3.235278|
| Same warm public cache npm ci |0|2.996168|
| Warm cache offline npm ci |0|2.960152|
| Intentionally corrupted required React cache, offline npm ci |1, ENOTCACHED|3.461889|
| Restored required content, offline npm ci |0|2.734002|
| Fixed toolchain check |0|0.177986|
| Typecheck |0|0.913447|
| Production build |0|4.726062|

[Actual receipt](npm-local-experiment.json). Install experiments use --ignore-scripts and
--no-audit to measure package rehydration; this flag is not added to CI and does not substitute
for an audit. Corruption caused npm to reject/refetch the content and fail without a network
fallback in offline mode; do not call it an EINTEGRITY exit (native error was ENOTCACHED).
The original content was restored and the next offline installation and build passed. Cache
and evidence belong only to this experiment, not existing/shared server data. No service ran.

The observed local cold/warm difference is only0.239110s. Do not extrapolate it to Hosted or
claim a net cache benefit: cache compression/transport and Hosted runner/network costs are
NOT_RUN. The three duplicate preparation commands avoid work locally, but the original Full
critical path remains governed by required PG jobs. No new build-sharing job or Next/uv/
Playwright cache is justified by this small local build sample alone; remaining H3 work stays
bounded by actual Hosted evidence and separately authorized runs.

Validation: focused239pass/12.47s; after a type-annotation-only test correction, affected cache
and original-consumer-equivalence7pass/0.29s, Ruff/mypy2files/diff pass. First Ruff failed two
long test literals, and mypy rejected direct access to the check module's imported subprocess;
both were fixed without runtime workflow changes. Six necessary new offline cases cover
cache identity/origin/integrity and mandatory surviving preparation. No business test deleted.
Existing independent Sol Reviewer ACCEPTS codeed17399 and metadatad735fc3, no BLOCKER or
necessary source correction. The approximately107MB task-owned cache and local0.239s delta
remain a nonblocking FOLLOW_UP: use actual authorized Hosted transport/post-save measurements
to decide retention; do not assume a net benefit. Final full scanner binds the later metadata
SHA externally; H3 overall/Hosted acceptance is not implied.

## Complete local preparation verification — 2026-10-30

Exact source `8645634d4aca734344be68640d186692bbef1207`, which already has independent code/
metadata ACCEPT. No implementation change was needed. One actual complete `uv run --frozen
python -m scripts.check` exits0 in318.437312s:2966offline pass/590integration deselected/
4warnings/271.92s, full secret scan, lock/docs/lint/format/full typecheck, npm installation/
fixed toolchain/typecheck/audit and95locked Python runtime/dev/build packages audited with
known vulnerabilities0. Immediately afterward, `npm run build` exits0 in3.238832s. Both
complete inside one23minute local window with85sreserve, no timeout, using the previously
owned public npm cache and empty isolated npm user/global configuration. Tracked tree remains
unchanged. [Native receipt](full-local-preparation.json).

This is complete local engineering preparation, not Hosted Full or PG/Web/N01 acceptance.
There is no cold/warm comparison for this complete check, and build-cache/network effects
are uncontrolled; do not call318seconds a Full CI speedup. No Docker/PG/browser service,
provider call, remote push/CI/protection mutation, H4 or M3 was requested. Existing independent
implementation review applies to unchanged code; this later documentation only records the
new actual results. The exact8645634 secret scan remains valid for that unchanged source;
any later metadata SHA receives its own final full scan without repeating2966tests.

Retained historical Full41010032206/a5c80203 frontend preparation232s, actual PG/Web829s;
N01 preparation489s and six actual cases109s. Preparation bundles tools/checks/build/browser
installation, not build alone. This old sample is not a new candidate benchmark or evidence
that artifact sharing would improve the current critical path. The remaining H3 acceptance
requires separately authorized real Hosted measurements; no new local framework is needed.
