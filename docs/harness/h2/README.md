# H2 PG Full local candidate

Status: **LOCAL_IMAGE_REPAIR_CANDIDATE / SCOPE_REVIEW; H2 acceptance pending.** Fourth
original Full passed for06e319b/8e95fb8a; Shadow failed four runner revision comparisons
and two image-proof checks. Local B is independently accepted and unpushed; A is a
proposed contract change only. See [actual results](RESULTS.md), [fourth receipt](fourth-hosted-receipt.json)
and [one-field proposal](environment-contract-proposal.json).
This stage reduces the existing PG critical path by assigning existing bounded execution
commands to four or six isolated shards. It extends `scripts.pg_ci_evidence` and
`scripts.pg_diagnostic`; it adds no scheduler, DB, service, fixture shortcut or model call.
Product UI result: NOT_APPLICABLE. PF-1 review covers correctness/safety and avoidable complexity.

## Compatibility and boundaries

The old two-positional-file `python -m scripts.pg_ci_evidence existing.json phase3.json`
invocation, v1 schema/validation and `quality.yml` remain unchanged. Diagnostic arguments are
additive: omitting `--shard-plan`/`--shard-id` retains the old execution groups, scopes,
G1/G2, 300-second commands, immutable deadline, 75-second reserve and 60-second cleanup cap.
The focused suite compares the old workflow bytes with accepted `6d3a8f7`.

V2's authoritative set is actual full current integration collection, not the historical
590 count. `plan_shards()` derives `combined_groups(full)` and assigns its complete commands
with deterministic LPT; it never schedules an arbitrary module path that could overcollect.
The checkpoint-containing command stays on shard zero, which runs the original G1 lifecycle
and all six G2 scenarios. Missing/new timing rows use positive defaults; stale timing rows
cannot select or omit tests. Acceptance keeps original-five plus two terminal singletons;
terminal recovery keeps selected four-case commands and real independent DB preparation.

`validate_plan()` regenerates the canonical plan. `shard_groups()` compares each runtime's
actual full collection before any test command. `safe_shard_report()` exports closed metadata,
not private raw records. `validate_shard()`/`verify_shards()` require exact selected, actual
collection and passed node lists, complete group membership, no duplicates/missing shards,
matching SHA/tree, locked tools/binary hashes, runner/Compose identity, run ID/attempt and plan.
Every native command and diagnostic parent must exit zero; stopping, cleanup and zero owned
container/network/volume inventory are mandatory. Random projects/volumes must be unique;
actual PostgreSQL image IDs must agree. Smoke requires exactly G1 three and G2 six; v1's
historical five-required/optional-sixth behavior remains unchanged.

The diagnostic exports `native_exit: null`. Only the workflow wrapper, **after the diagnostic
process exits**, runs `finalize --exit "$native_exit"`. Finalization is one-shot and records
failure as failure; it never declares a job successful. Aggregation also checks real matrix
job results. Cancelled/failed/skipped jobs cannot be rescued by otherwise valid artifacts.
Missing artifacts and malformed JSON fail closed. This metadata is trusted CI process
attestation, not a cryptographic claim against a hostile runner.

## Native baseline and slow-test analysis

Timing provenance: H0 `evidence/ci/40432280677.events.json`, accepted source `6d3a8f7`, actual
native pytest setup/call/teardown events. `weights.json` sums those phases per node; its byte
SHA256 is `54a07934951a5f4bbf8443e09a182d0f3de3773ce7b1a467109b9ac84b8620bf`.
It is scheduling input only; the current checkout supplies authoritative collection.

| Historical module | Nodes | Total seconds | Setup | Call | Teardown |
| --- | ---: | ---: | ---: | ---: | ---: |
| `test_p4_acceptance_pg.py` | 7 | 647.944 | 0.291 | 647.199 | 0.454 |
| `test_p4_terminal_recovery_pg.py` | 12 | 510.661 | 272.589 | 236.276 | 1.797 |

Acceptance's initialization is inside calls, so its tiny pytest setup total is misleading.
`initialize_schema()` applies exact historical migrations/checkpoints/grants.
`AcceptanceFixture.prepare()` creates isolated P3/API/identity/private child inputs.
`completed_origin()` and `prepare_single_ro()` perform native approval/unknown history,
real 60-second origin expiry and successive DB-clock backoffs. Terminal enrollment adds
six fresh provenance rejection processes, competing workers, cold replay, replacement
and revocation. Individual call durations are 0.490, 0.586, 168.321, 50.156, 4.234,
211.276 and 212.134 seconds. Reusing children would remove the cold-process evidence.

Recovery's module-scoped `failed_cases()` prepares each selected case in a separate DB,
serially through `prepare_failure()` and `verified_queued_origin()`. Three four-case
commands charge 91.689, 90.282 and 90.612 seconds of shared setup to their first tests.
Later-case preparation naturally overlaps the earlier cases' real 30-second cooldown.
Twelve singleton commands could lose that overlap. This candidate preserves those groups
and all real clock, SIGTERM, cancellation, permission, once and UNKNOWN semantics.
No fixture refactor is justified without measured stage-level evidence.

| Static scheduling simulation | Historical nodes/groups | Max cumulative pytest activity |
| --- | ---: | ---: |
| Four shards | 590 / 35 existing command groups | 1068.121s = 17.802m |
| Six shards | 590 / 35 existing command groups | 717.236s = 11.954m |

These are pure simulations using native historical durations. Startup, image build/pull,
collection, G1 lifecycle, new runner capacity and cleanup overhead are excluded. No measured
speedup, job-minutes improvement or 20–25-minute acceptance is claimed. The material's module
LPT 11.851m differs because actual command boundaries, not whole modules, are assigned here.

## Reviewable shadow execution boundary

The single prepared source is [harness-pg-shadow.yml](../../../.github/workflows/harness-pg-shadow.yml).
It runs only on PR events for this repository's own `codex/harness-v3` head branch. All jobs
checkout `github.sha`, the PR merge commit, alongside untouched original Full workflow.
It requires no new default-branch-only dispatch workflow and no required-check changes.
It is local source only: publishing this branch can start Hosted jobs, so push/PR/Hosted
execution still requires explicit authorization before publication.

The plan job collects current integration IDs without executing tests, then runs:

```sh
uv run --frozen python -m scripts.pg_ci_evidence plan \
  --full .audit/full.json --weights docs/harness/h2/weights.json \
  --shards 6 --output .audit/plan.json
```

Each isolated Hosted shard receives that exact artifact, verifies checkout/tools/run/runner,
registers the existing 43-minute absolute budget before checkout/preparation and uses:

```sh
uv run --frozen python -m scripts.pg_diagnostic \
  --session ci --round 1 --combined --no-child-trace \
  --shard-plan .audit/plan/plan.json --shard-id 0 --full-smoke \
  --deadline "$(cat .audit/ci-deadline)"
```

Other shards omit `--full-smoke`. The workflow captures actual native exit before finalizing
and uploads only closed JSON. Aggregation requires the plan, every shard report and real
matrix outcomes. The initial shadow is six shards; a four-shard comparison requires changing
both declared plan count and matrix/outcome range, then local review before publication.

Remote H2 acceptance must inspect completed **same merge SHA/tree** old Full and new shadow,
validate original pair and dynamic full-set equality, all original Web/N01/offline/security
jobs, real G1/G2/cleanup/native outcomes, and record total walltime/job-minutes and all failures.
A PG shadow pass alone is not Full approval. Preserve old required checks and old runner as
rollback. H3 implementation waits for H2 core qualification; required-check/protection changes
need separate authorization. No candidate H3/H4 runtime capability is implied.

Rollback: revert the ordinary H2 local commit. The original workflow, fixtures, locks,
business code and original default diagnostic mode require no migration or restoration.
