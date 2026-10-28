# H1 local result

Status: **LOCAL_GATE_ACCEPTED** at frozen code `17e2e1af5e77b1c09b1de45d51c357a8e4da1dd4`, independently reviewed by existing Sol/high Reviewer under PF-1. Correctness/safety ACCEPT; complexity reasonable; product UI NOT_APPLICABLE; no remaining BLOCKER. Independent incremental regression: 1 passed/0.24s; TaskSpec VALID_LOCAL_CONTRACT/execution_authorized=false. Valid earlier evidence was reused, not rerun mechanically. This local Gate does not grant merge authority. Full/Hosted/PG/Web/model inference for this candidate remain NOT_RUN.

PF-1 was received before H1 freeze and attached to the existing task/Reviewer contract and handoff. Only those short documentation additions apply now: internal development cost, reuse, proportionate development checks, dual-axis findings and `SCOPE_REVIEW`. No product UI, extra Agent, service or schema field was introduced for the addendum. Builder encountered a Sol capacity error after preserving the implementation and validation records; Root continues the same local closeout without model upgrade or duplicate task dispatch.

Base: `6d3a8f7bf3d36c6c1dcfd5072a3297be4cc88265`. First freeze: `fc65bfbefc068f1c726dac37350dd6f901d7d785`. Machine reports below are explicitly pre-freeze Worktree evidence (HEAD still base), not invented exact-candidate CI. Independent review reuses valid unchanged-source evidence and checks only actual fixes and newly affected paths.

## Changes and invariants

- Preserved original AGENTS exactly: 52,917 bytes, SHA256 `121290e12d2e4349e3c90f685058c4c359bcb1251872d87d0de280f7bcde2837`; archive stays at repository root so original relative links keep working. New AGENTS is 2,263 bytes.
- Added short generated CURRENT_STATE with read-only #49 closed/#51 open authority observation, accepted M2 base/CI, H0 fixed handoff/code pointers and Harness pending states. A reviewed hash pin plus exact original-Git byte comparison guards regeneration. Remote freshness remains SNAPSHOT_ONLY; `--json` supplies live local Git state.
- Added strict versioned TaskSpec/RunAttempt JSON schemas, canonical digest, owner/scope/model/check/counter validation and offline tests. Sol/medium default; literal false API fallback; nonblank scoped Astra reference required. Local approval references are not cryptographic receipts or execution permission. Persistent one-time authorization, atomic ownership and recovery remain H4.
- Added Fast/Impacted local entry with committed/staged/unstaged/deleted/untracked path union, changed Python AST/Ruff/mypy, relevant docs/state/contracts checks and per-check JSON command/exit/timing. High-risk/unknown/unmapped changes require Full. Every report keeps `full_gate=NOT_RUN` and `merge_eligible=false`.
- Existing business/backend/frontend files, existing business tests, `scripts.check`, workflows, locks, required gates and resource contracts are unchanged. The accepted 2778 offline/590 real PG baseline is preserved; only H1 offline tests were added. No Full execution is claimed.

## Actual validation

Commands use this Worktree's `.venv/bin/python`; the documented `uv run --frozen python` form uses the same pinned environment. Full argv and per-check timings are in the linked JSON.

| Command / scenario | Exit | Actual wall seconds | Evidence |
| --- | ---: | ---: | --- |
| `uv sync --frozen` | 0 | 0.994 tool wall | Local .venv only; lock unchanged |
| `python -m pytest -q -m offline tests/test_harness_contract.py tests/test_harness_verify.py` | 0 | 1.49 pytest wall | 35 passed; includes real subprocess exit7, timeout124, child SIGTERM143 and owned child reaping |
| `python -m scripts.verify fast --spec docs/harness/task.example.json`, run1 | 0 | 2.696956 | [JSON](evidence/fast-freeze-1.json) |
| Same Fast, run2 | 0 | 2.492908 | [JSON](evidence/fast-freeze-2.json) |
| `python -m scripts.verify impacted --spec docs/harness/task.example.json` | 0 | 2.478158 | [JSON](evidence/impacted-freeze.json) |
| Fast with actual malformed untracked Harness JSON | 1 | 0.071123 | [FAILED JSON](evidence/error.json); temporary fixture removed |
| Actual Fast CLI SIGTERM during changed-Python mypy | 143 | 0.454419 | [INTERRUPTED JSON](evidence/interrupted-freeze.json); owned child82861 absent, remaining checks NOT_RUN |
| Impacted with actual unrecognized untracked path, no spec | 3 | 2.441186 | [NOT_RUN JSON](evidence/impacted-not-run.json); full_required=true, fixture removed |

Fast's eight planned checks passed in both final measurements: baseline/staged whitespace, changed-Python Ruff lint/format, targeted mypy (five files), pinned state/archive, Markdown links/fences (122 files) and 35 H1 offline tests. Local times characterize this H1 batch only; they are not Full-CI performance or p95 claims. `git diff --check` also passed before freeze.

Retained failures: initial targeted suite had 32 pass/1 fail because a synthetic approval omitted its canonical default `scope`; the fixture was corrected, retaining digest strictness. Initial Ruff/format findings were corrected only in new files; no blanket formatting. A first signal-driver attempt used unsupported macOS `ps -P` child selection, found no child and sent no signal; its CLI result was uncollected. [Driver failure record](evidence/interruption-driver-failure.json) remains separate. Corrected `pgrep -P` discovery then observed a live verifier child, actual SIGTERM143 and no surviving observed child. Numeric-zero/whitespace-reference negatives and killed-child normalization were added before the final 35-test runs.

## Boundaries, rollback and next gate

Assigned policy is Sol/medium; actual model token/quota accounting is UNKNOWN and no reservation is claimed. No extra inference or paid API was invoked. GitHub access was read-only #49/#51 fetches. No push/PR/Issue/Hosted/protection changes; no business credentials, Docker, PG, browser, UTM or global configuration/service actions. Only the own Worktree `.venv`, temporary synthetic test directories and local evidence were created. Test subprocesses completed or were stopped/reaped; no service was started.

The H0 pointer in the pinned observation is the accepted handoff `b93da31`; H0 code freeze remains `b0d61e73`. Root subsequently produced a supplementary evidence handoff `5e9abac5541d75d1281429c32f0df43519beb80d` with code unchanged; its narrow review remains separate. This does not recast H0 mock proof as live dispatch.

PF-1 independent review of first freeze returned FIX_LOCAL on two actual H1 gaps. Root merged committed/cached/unstaged/untracked path sets separately and extended the existing regression with staged-invalid/worktree-restored cancellation. The targeted regression passed (exit0, 0.27s); targeted Ruff lint/format passed. No broad test infrastructure or repetition of the valid 35-test suite was required.

The second local repair adds the small approved project model configuration. Native `codex app-server` read-only initialize/config-read/model-list/account-read attributes Sol/medium, ChatGPT auth, never approval and workspace-write to this project's layer; sandbox network is false, Sol supports medium, auth is ChatGPT/pro. Probe native exit0/reaped, 1.338522s, zero thread/turn requests. [Effective configuration evidence](evidence/project-config-probe.json) is not inference proof. Strict startup first exited1 because the inherited global `features.rmcp_client` is unknown to this CLI; [failure retained](evidence/project-config-strict-failure.json), no global file/trust changes. Project configuration and the normal native load are independently reviewable; strict-global cleanup is outside this H1 scope.

Rollback: revert the ordinary H1 local commit(s); original AGENTS remains traceable at the accepted base and in the byte-preserving archive. No resource migration is needed. Independent frozen-SHA review and local rerun are pending; H2–H5 implementation and every candidate Full/Hosted/real integration gate are NOT_RUN. H4 must add trusted approval verification, persistent attempts, atomic leases/ownership, actual quota checks and isolated model configuration before dispatch. Future Runner cannot inherit global `danger-full-access`.
