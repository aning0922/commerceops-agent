# H2 local results and independent-review handoff

Status: **LOCAL_REPAIR_CANDIDATE**, not H2 accepted. First Hosted Full/shadow: **FAILURE**
at the scan gate. Real PG, completed old/new Full comparison and measured speed: **NOT_RUN**.
Product UI: NOT_APPLICABLE. The first-attempt job timings are preserved in its receipt.

Final corrective source `17fda8ccf12a319a54b241a23b9d12212aa43dc3` independently ACCEPTED by the existing Sol Reviewer: no remaining local BLOCKER, complexity reasonable, UI N/A. This covers the exact-history repair and missing Fast wiring; it does not authorize remote retry. Actual full scan on this frozen source exited0 in26.345007s: dir/index0; history native1 with8 reviewed public findings, zero blocking. [Frozen-source receipt](final-corrective-source-scan.json). Default/full history behavior and negative controls remain intact.

## First approved Hosted attempt and local repair

The user approved publishing head `8b9e5d41f372ef81d690631b787170a4eab7e4cf` as Draft [PR52](https://github.com/aning0922/commerceops-agent/pull/52) and exactly one original Full plus one shadow. Full40658357111 and shadow40658357225 both ended FAILURE, attempt1. Native checkout logs from both confirm merge `feb88aeb380df379b96fa42620d696e22be16123`. [Receipt](first-hosted-receipt.json) preserves actual jobs and timestamps. The failure was before dependencies/test execution at the unchanged sensitive scan; all six shard executions and PG/Web/N01/offline tests were NOT_RUN. No speed result exists. No retry, PR edit, merge, protection or business-resource action was taken.

The scanner found five current public-source matches: three pytest type annotations, one fixed export canary, and one configuration prose line. Native git scan found13: three existing approved public records, five corresponding source-commit records, and five records on that failed synthetic merge. All positions were recorded without Secret/Match output. Independent existing Sol Reviewer verified the five source declarations are public and approved forming a minimal local repair candidate, with a frozen re-review still required.

Current spelling was changed without weakening behavior: use the project's existing `MonkeyPatch as Patch` import pattern, a short explicit dummy canary, and ordinary configuration prose. The existing git-only immutable public-history classification gained exactly five source records (3→8), each binding rule/path/line/commit/fingerprint, redacted-match hash and source-line hashes. `.gitleaks.toml` remains byte-identical:222 rules and17 rule-level exact exceptions unchanged. Directory/index are never exempt; synthetic merge/future commits are not implicitly approved. No history or protected refs were rewritten or removed.

Actual local validation of this repair: Ruff/mypy on four affected Python files passed; the three directly affected suites passed **156 tests in106.11s**. Initial Ruff long-literal/format failures were corrected before that passing run. The native full scanner then exited0 in26.107522s: dir0/index0; git native exit1 with8 findings, all8 exact reviewed public records and zero blocking. [Scan receipt](secret-gate-repair-scan.json) distinguishes native scanner findings from the classifier's exit. The same binary version8.30.1 was reused read-only from an existing project-local installation via an ignored symlink; no global install or Node setup expansion occurred.

The allowed remote attempts are spent. This local repair has not been pushed and cannot restart CI without fresh explicit authorization. H2 remains unaccepted and H3 stays gated; the earlier local acceptance below does not turn the failed Hosted attempt into a pass.

The first failure also exposed an H1 contract omission: material05 requires current-content Secret feedback, absent from the original Fast plan. The existing scanner now has an explicit local `--current-only` mode (dir/index; history NOT_RUN); its default remains full-history. Fast invokes that mode. No new scanner, service or rule was introduced. Existing synthetic cases were reused to prove default history blocking, current/index blocking and explicit local history omission:11 affected checks passed in11.62s. A real Fast run with a temporary synthetic current finding failed in19.538530s without disclosing the value; the canary was removed and never staged. [Negative receipt](fast-secret-negative.json).

The first normal Fast attempt then failed in22.569331s on an obsolete test assertion that permanently expected H2-H5 NOT_RUN. [Failure retained](fast-secret-first-normal-failed.json). PF-1.1 correction now checks that the pinned current stage is rendered and still rejects an unreviewed snapshot edit; no safety assertion was removed. Targeted state regression passed in0.07s, and the corrected actual Fast passed all9 checks in21.694184s, with Full still NOT_RUN. [Normal receipt](fast-secret-positive.json). These are local feedback timings with current-content coverage, not a Full-CI speed comparison.

Independent review accepted frozen local candidate `14c901437de6004875974e9a0fd49d8aa666e2a4` / tree `eb72691b53491d7c3169b326451f838dbbc18ddd`: no BLOCKER; correctness/safety and complexity both accepted for local readiness. Existing Sol/high Reviewer reused valid tests and audited source/workflow without repeating suites or running resources. FOLLOW_UP is the actual authorized same-SHA Hosted acceptance; unrelated Node setup and extra infrastructure are OUT_OF_SCOPE. Shadow caps: plan15 + six shards×45 + aggregate15 =300 job-minute ceiling, separate from old Full; not expected duration or billing.

PF-1.1 received at this frozen review boundary; worktree was clean, builder frozen and Root owned handoff. Its short authoritative index is in [existing task/Reviewer rules](../README.md#pf-11-development-freedom-effective-at-h2-review-handoff). No stage restarted or acceptance repeated; no code/test/resource retirement was triggered merely by policy receipt. Existing v1 remains only because current required workflow still consumes it until the approved H3 switch.

Earlier collection at source `7c1b49e9fdba0df21b66338d7282753c577659ef` was2858offline/590integration (preserved in Git history). Current corrective-source collection at17fda8cc is **2863offline/590integration**, exit0, wall8.321470s/7.951296s. The delta is11 added/6 removed node IDs: five old scanner cases now carry explicit default-mode parameter IDs, five current-only variants were added, and the exact-history test was renamed for its reviewed current set. No business behavior or PG protection was retired. [Current exact collection](current-collection.json) is **collection only, not test execution passes**. No valid same-SHA collection was repeated.
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
