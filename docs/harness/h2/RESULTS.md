# H2 local results and independent-review handoff

Status: **LOCAL_CANDIDATE**, not H2 accepted. Hosted, real PG, old/new same-SHA Full,
measured speed and job-minutes: **NOT_RUN**. Product UI: NOT_APPLICABLE.

Independent review accepted frozen local candidate `14c901437de6004875974e9a0fd49d8aa666e2a4` / tree `eb72691b53491d7c3169b326451f838dbbc18ddd`: no BLOCKER; correctness/safety and complexity both accepted for local readiness. Existing Sol/high Reviewer reused valid tests and audited source/workflow without repeating suites or running resources. FOLLOW_UP is the actual authorized same-SHA Hosted acceptance; unrelated Node setup and extra infrastructure are OUT_OF_SCOPE. Shadow caps: plan15 + six shards×45 + aggregate15 =300 job-minute ceiling, separate from old Full; not expected duration or billing.

PF-1.1 received at this frozen review boundary; worktree was clean, builder frozen and Root owned handoff. Its short authoritative index is in [existing task/Reviewer rules](../README.md#pf-11-development-freedom-effective-at-h2-review-handoff). No stage restarted or acceptance repeated; no code/test/resource retirement was triggered merely by policy receipt. Existing v1 remains only because current required workflow still consumes it until the approved H3 switch.
Base: `650249016cb4d782e843c1dc8686afa7c1e68aa7` on `codex/harness-v3`, following
H1 independent local acceptance at `17e2e1af5e77b1c09b1de45d51c357a8e4da1dd4`.
Freeze is the ordinary local commit containing this handoff; obtain its exact SHA with
`git log -1 --format=%H -- docs/harness/h2/RESULTS.md`. No future SHA is prefilled.

Scope: two existing Python helpers, one focused pure test file, safe historical timing
weights/research notes and one restricted PR shadow workflow. Original `quality.yml`,
business code, business fixtures, locks, permissions, clocks and command/cleanup budgets
are unchanged. No subagents, PG/Docker/browser/models/global installation or remote writes
were used by this implementation task. No generic platform or additional service was added.

## Executed checks

| Command or scope | Actual exit/result | Recorded time |
| --- | --- | --- |
| Ruff lint + format and mypy on both helpers/new test file | 0, all pass | Final combined invocation 1.10s incl. focused pytest |
| Initial direct v2/v1/partition suite after native-exit fix | 0, 126 passed | pytest 0.23s |
| Final new v2, old v1/partition, shutdown, existing N01 source contract | 0, 186 passed | pytest 1.12s; command batch 2.09s incl. docs/diff |
| `python -m scripts.check_docs` | 0; 123 Markdown files, errors 0 | Included above |
| `git diff --check` | 0 | Included above |
| `python -m scripts.verify fast --base 650249016cb4d782e843c1dc8686afa7c1e68aa7` | 0, LOCAL_PASS; Full required, merge_eligible=false | 2.814386s |

Fast reports the new CI/evidence/diagnostic/test paths as unmapped/high risk and correctly
keeps `full_gate=NOT_RUN`. Its included H1 contracts pass. Focused tests execute the real new
helper functions and `run_combined()` with a fake command callable; no synthetic result is
presented as real PG evidence. Both 4/6 plans execute all 590 historical IDs/35 existing
command groups in simulation, and new-node tests prove the historical count is not a ceiling.

## Failures retained and limits

Initial authoring checks found Ruff formatting/long lines and one optional shard-ID mypy
error; these were corrected before the passing focused runs. No PG or CI retry occurred.
An expanded existing offline run yielded **187 passed, 38 failed in 3.34s**. All 38 failures
were in unchanged `test_live_failure_ci_gate.py`; the first-case short reproduction showed
`FileNotFoundError` for this Worktree's absent `.tools/node/bin/node` (1 failed/1 passed,
0.28s). This is a local tool-setup failure, not proof of any business assertion or new
regression. Tools were not installed, tests were not weakened, and Full is not claimed.
The later 186-pass focused run excludes that unrelated Node-dependent suite; it does not
supersede its failed result. Existing N01 checks were exercised as a limited workflow-source
compatibility check, not browser evidence.

The slow fixture analysis and simulation are in [README](README.md). No test fixture,
real-clock/backoff, child-process, approval, UNKNOWN, once, permissions or cleanup semantic
was optimized speculatively. The first Hosted shadow must measure actual image/build/
collection/G1/cleanup overhead before any speed claim.

## Independent Reviewer focus

- Correctness/safety: v1 remains compatible; whole-group assignment cannot overcollect;
  plan/source/tree/tools/run/attempt/environment and actual image bindings are exact;
  new nodes enter the dynamic full set; G1 three/G2 six and all native/cleanup failures
  are mandatory. Native parent exit starts unknown and is finalized only after actual wait.
- Workflow: same PR merge `github.sha` in every job, same-repository/head-branch guard,
  no heavy work for unrelated branches, matrix failure cannot become aggregate success,
  and original Full/required checks stay untouched.
- PF-1: reuse existing grouping/lifecycle, no second orchestration framework; UI N/A.
  Recommend ACCEPT/FIX_LOCAL/SCOPE_REVIEW on local candidate separately from Hosted approval.

Next boundary: obtain independent review of this exact local freeze. If accepted locally,
request explicit publication plus Hosted shadow authorization for the concrete workflow.
Actual H2 acceptance additionally needs completed same-SHA original Full and new shadow,
exact full-set comparison, real Web/N01/offline/security/G1/G2/native cleanup evidence and
measured walltime/job-minutes, retaining all failed/cancelled outcomes. H3 implementation
remains gated. Branch protection/required-check changes remain separately unapproved.
