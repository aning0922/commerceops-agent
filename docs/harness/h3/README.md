# H3 — Web, caching and final Full gate

Status: **H3_NOT_ACCEPTED / LOCAL_CONTEXT_REPAIR_REVIEWED**. H2 acceptance remains scoped to published
`a5c80203df9de89e0d22a87d565533b38b23899a` and its exact Full/Shadow pair. The user instruction
“开始下一步” authorizes the next local H3 work; it does not grant push, Hosted runs, Required
Check/protection mutation, main merge, H4, paid API, M3 or real business resources.

## First Hosted terminal result — 2026-10-30

Published `e33cc4b04bac1d806aa390cfb7c515c126067be3`, one push, authorization SPENT.
[Full41028393476](https://github.com/aning0922/commerceops-agent/actions/runs/41028393476)
FAILS workflow validation before any job exists. Its native event is push and job count0;
no Full PR merge checkout, offline/PG/Web/N01/cache/build/merge-gate ran. GitHub reports
job-level env references to runner.temp at lines69and531 are invalid. This is a configuration
error, not a PG test failure or an H2 performance result. Artifacts/cache timing are NOT_RUN.

[Shadow41028403294](https://github.com/aning0922/commerceops-agent/actions/runs/41028403294)
SUCCESS/all8jobs/attempt1, actual merge63f06f10d8f82f431b419f051beee255524df6de,
treedf7778bf6ec56eca7536c60548390af911d46e8a. All six closed artifacts validate against the
canonical590node/35execution-group plan; existing verify_shards and actual native job results
pass. Logs independently contain590unique passed calls/1770passed phases; all six native
parents0/cleanup0, G1three/G2six, distinct owned resources with final containers/networks/
volumes0,14real PythonTimer dumps. Plan/shards/aggregate all observe ImageVersion20261026.354.1,
not actual mixed-revision proof. Wall18m05s,89.2observed job-minutes, not billing. It does not
replace the rejected Full or qualify H3. [Exact receipt](first-hosted-receipt.json).

Independent failure review confirms a BLOCKER and the prior local review blind spot:
YAML/Bash parsing and custom wiring assertions did not check allowed expression contexts;
one assertion mirrored the invalid job-env placement. GitHub's
[context table](https://docs.github.com/en/actions/reference/workflows-and-actions/contexts#context-availability)
excludes runner from job-level env and allows it in step env/run/with. The smallest subsequent
local repair is relocating both assignments to the existing preparation steps using native
RUNNER_TEMP, preserving restore/save and npm's same owned directory. Reuse a mature semantic
checker such as actionlint for the actual workflows; do not create a custom expression parser,
new framework or expanded test matrix. This repair is proposed, NOT_IMPLEMENTED in this run.

H3 remains NOT_ACCEPTED; original H2 exact a5c80203 acceptance is retained, H4-H5 NOT_STARTED.
No retry, second push, PR-body edit, main merge, protection change or new remote run. Local
results below are historical local evidence and cannot prove Hosted workflow validity.

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
4warnings/271.92s. Security, lockfile, documentation, lint, formatting, typing and npm/
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

The first later metadata freeze893de47 was blocked by one generic-api-key finding in an
ordinary prose line152 describing checks. It contains no credential; the failure receipt is
retained. Current prose is reworded without changing meaning. Its already committed public
historical occurrence is proposed for the existing exact history review mechanism, bound to
commit/path/line/fingerprint/whole-line hashes/redacted-match hash. This grants no dir/index
exemption, path allowlist or scanner-rule change, and does not rewrite Git history. The
existing history test adds that one expected occurrence and retains all wrong-scope, changed-
commit, changed-match and other field rejection checks. Actual independent approval and the
final full scanner result are recorded separately, not inferred from this proposal.

## Local expression-context repair — 2026-10-30

User authorizes only local repair/check/review/freeze, no push/new Hosted/protection/H4.
Base `befa8e966ce7047cefaabc49b431f2ab2fd3368c`, same Root/Worktree/branch. The two invalid
job-level npm_config_cache assignments are removed. Each existing preparation shell exports
`npm_config_cache="${RUNNER_TEMP:?}/commerceops-npm"` before the original commands. No extra
assignment is added to live verification steps. Restore/save path, cache identity/key, all
original checks/deadlines/permissions/cleanup and the final gate remain unchanged. Real Bash
checks prove the npm directory matches the cache action's parent even with spaces in the
runner path; absent RUNNER_TEMP rejects rather than choosing another directory.

Mature [actionlint](https://github.com/rhysd/actionlint/blob/v1.7.12/docs/usage.md)1.7.12 is
pinned by executable SHA-256 for this native Darwin/ARM host and Linux/x86_64. Official release
archive checksums were verified before extracting the executable into ignored .tools only.
No global installation, Go dependency, new service or Hosted job. The small stdlib wrapper
`python -m scripts.check_workflows` verifies the local executable hash then checks all actual
workflow files. Missing, altered or unsupported binaries fail, never silently skip. It does
not install/download a tool at runtime. ShellCheck/pyflakes integrations are explicitly off:
this invocation validates workflow/expression semantics; existing Python and Bash gates stay.
No actionlint error-ignore rules or custom expression parser are introduced.

Fast/Impacted now invoke this check for workflow changes or checker changes. Existing
high-risk/unknown mappings still require Full. Pre-publish must run Fast for the exact
candidate and default full scripts.scan_secrets; local semantic success is not Hosted proof.

Actual checks: old published e33cc4b workflow is rejected native1 with exactly the two runner
context expression errors at69and531. Current two complete workflows pass native0/0.166036s
(wrapper wall). Focused247pass/14.44s, followed by final affected2pass/.24s after restricting
runtime exports to the two preparation steps. Ruff/mypy5files/format/diff pass. Three new
necessary offline cases assert Fast/Impacted wiring and missing/incorrect checker fail-closed;
no business test deleted. Fast actually LOCAL_PASS/24.982684s, semantic check0/.046714s;
full_gateNOT_RUN/full_requiredtrue/merge_eligiblefalse. Its recorded working-tree revision
preceded this result-only documentation and one equivalent out-of-root path guard.

For a fresh Darwin/ARM Worktree, install the pinned local release explicitly, then run:

```sh
mkdir -p .tools/actionlint-download
curl --fail --location --output .tools/actionlint-download/actionlint.tar.gz \
  https://github.com/rhysd/actionlint/releases/download/v1.7.12/actionlint_1.7.12_darwin_arm64.tar.gz
printf '%s  %s\n' aba9ced2dee8d27fecca3dc7feb1a7f9a52caefa1eb46f3271ea66b6e0e6953f \
  .tools/actionlint-download/actionlint.tar.gz | shasum -a 256 -c -
tar -xzf .tools/actionlint-download/actionlint.tar.gz -C .tools actionlint
uv run --frozen python -m scripts.check_workflows
```

Linux/x86_64 uses official actionlint_1.7.12_linux_amd64.tar.gz, archive checksum
`8aca8db96f1b94770f1b0d72b6dddcb1ebb8123cb3712530b08cc387b349a3d8`; the wrapper separately
verifies its pinned binary digest. Other platforms fail until a scoped pin is approved.
The original Full41028393476 failure and Shadow41028403294 success remain immutable. Repair
Hosted/PG/Web/N01/cache-net-benefit acceptance NOT_RUN; H3 remains NOT_ACCEPTED and H4 not
started. Independent repair review/final full scanner bind the final freeze separately.

Frozen repair `b54fcf2129b1c1b43568cd8020152748c45e2c10` now has existing independent Sol
Reviewer ACCEPT/no BLOCKER, no source correction. Exact frozen Fast LOCAL_PASS/27.746037s,
actionlint0/.045684s, full_gateNOT_RUN/full_requiredtrue/merge_eligiblefalse. Actual current
collection2969offline/590integration is collection only;3new cases, no business deletion.
[Repair receipt](context-repair-local.json). This supersedes only the earlier local repair
proposal; it does not rewrite the failed e33cc4b Hosted result or qualify H3. Final result-only
metadata SHA receives default full scanning, with external actual receipt. No new remote run.
