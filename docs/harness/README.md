# H1 local verification and handoff

This stage adds local feedback and typed task records. It does not run a scheduler, reserve quota, invoke a model, access business secrets or grant publication authority. The existing `scripts.check`, workflows, Full required PG/Web/N01/pair checks and business tests are unchanged.

The project `.codex/config.toml` pins Sol/medium, ChatGPT authentication, workspace-write and no sandbox network access. The native read-only config probe attributes these values to this project's configuration layer and confirms the Sol catalog entry. This verifies loading, not real inference or the future H4 Worker boundary. Strict startup currently rejects a pre-existing global legacy field; its failure is retained without changing global configuration or trust.

## PF-1 task and Reviewer contract

PF-1 applies incrementally from the H1 freeze handoff on 2026-10-28. Internal Harness tasks state the development cost they reduce and first identify existing scripts or mature tools to reuse. Add only the local implementation needed for the approved stage. Unjustified cross-layer abstractions, a second scheduler, extra services or tables, or repeated infrastructure built to test infrastructure trigger `SCOPE_REVIEW`; pause only the expansion and propose the smallest local repair. This adds no management system or UI work.

Use R0/R1 targeted visual or ordinary-interaction checks, R2 data/integration correctness, and R3 necessary real permission, transaction, idempotency, UNKNOWN and recovery checks. These are development feedback levels: existing Required Checks, Full CI and all V3/M2 safety evidence remain mandatory. Reuse valid evidence for the same frozen code and scope; rerun only when changes, failures or uncovered risks justify it.

Reviewer reports two axes: correctness/safety and avoidable complexity/product experience. Classify findings as `BLOCKER` (reproducible failure or actual contract breach), `FOLLOW_UP` (nonblocking improvement), or `OUT_OF_SCOPE` (unrelated or speculative expansion); recommend `ACCEPT`, `FIX_LOCAL` or `SCOPE_REVIEW`. Do not turn a nonblocking hypothetical into an infrastructure dependency. H0-H5 internal work has product UI result `NOT_APPLICABLE`; future authorized user-facing changes require user goals and key interactions, prototype/key-state review for important UI, and separate visual/product acceptance. Passing API/browser tests alone cannot substitute for that acceptance. M3 remains unapproved.

Start with [CURRENT_STATE](../../CURRENT_STATE.md). It is generated from the [reviewed authority observation](state_snapshot.json), not inferred from old STATUS prose. The observation records #49/#51 read-only state and exact source pins. `scripts.current_state` rejects a changed observation hash or changed historical AGENTS bytes; `--json` adds live local HEAD/branch/dirty facts and labels remote freshness SNAPSHOT_ONLY. Refresh requires an intentional reviewed source/pin update, then `--write`; it never executes Issue prose or fetches credentials.

```sh
uv sync --frozen
uv run --frozen python -m scripts.current_state
uv run --frozen python -m scripts.current_state --json
uv run --frozen python -m scripts.verify fast
uv run --frozen python -m scripts.verify impacted
uv run --frozen python -m scripts.harness_contract docs/harness/task.example.json
```

`python -m scripts.verify` also works directly with this Worktree's activated Python environment. Each run prints one JSON object; child output is hashed, not echoed into the report. `wall_seconds` uses a monotonic clock. Every planned check has its own command, exit code, timing and PASSED/FAILED/INTERRUPTED/NOT_RUN status. Remaining checks stay NOT_RUN after failure/interruption. `full_gate` always remains NOT_RUN and `merge_eligible` is always false here.

The changed-path set is the union of committed changes since `--base`, staged/unstaged/deleted paths and nonignored untracked files. Default base is the accepted M2 SHA; pass the task's actual frozen base when it changes. There is no path override that can hide changed files. `--spec` additionally validates exact base/branch/Worktree and every changed path against allowed/forbidden scopes. A DRAFT spec may be used for local check planning; it authorizes no execution. No spec means unknown risk.

Fast parses changed Python and local Harness JSON, checks Git whitespace, runs Ruff lint/format and mypy on changed Python, verifies trusted state/archive, checks Markdown links/fences and runs the H1 offline contract suite when relevant. Existing tests are not rewritten. H1's map covers only its own scripts/tests/docs and entry/archive. Impacted includes the same mapped local checks; an unmapped path adds a NOT_RUN coverage check and exits 3. Unknown/high/critical tasks, verification/control code, and any unmapped path require Full. Low-risk recognized documents can obtain local feedback, but they still cannot authorize a merge. A local pass does not claim Full or production proof.

Exit codes: 0 LOCAL_PASS; 1/input error or the failed child's nonzero exit; 3 incomplete Impacted coverage; 124 check timeout; 130 SIGINT; 143 SIGTERM. Per-check timeout defaults to 120 seconds (explicit range 1–600). SIGINT/SIGTERM stop the verifier's new child process group, wait/reap its direct child and preserve interrupted state. SIGKILL/power loss cannot emit a final report; persistent recovery belongs to H4. No automatic retry.

## Task and attempt validation

[TaskSpec schema](task.schema.json) and [RunAttempt schema](attempt.schema.json) are versioned strict Pydantic contracts. Unknown fields, unsafe paths, unsupported models, missing approval references, invalid counters and false success states fail closed. Only exact paths or trailing `/**` scopes are supported; forbidden scopes take precedence. The [example](task.example.json) is DRAFT and grants no authority. It records Sol/medium, bounded attempts/turns/walltime and no paid API fallback. Every frozen digest covers the complete normalized TaskSpec including defaults, owner and local approval reference, excluding only `spec_sha256` itself.

A local approval reference is data for review, not a signed or verified approval receipt. Astra needs a scoped reference and still needs actual trusted approval/quota checks before H4 execution. RunAttempt must bind the exact task/spec and model/effort, stay within task caps, use a unique attempt ID and contiguous previous attempts, and cannot retry success, interruption or UNKNOWN. The validator has no persistent store; callers must supply the complete previous attempt list and all active owner records. It cannot atomically consume approvals, enforce leases or prove subscription quota. H4 must implement those boundaries before real dispatch.

Use `--attempt FILE --previous FILE` (repeatable) to validate an attempt against a READY task. Use `--active FILE` (repeatable) to reject worktree/branch/overlapping allowed-file scopes. File conflicts are conservative even when forbidden subscopes could make them disjoint. Ownership validation is a local preflight, not a concurrent lock. All examples and synthetic test approvals are explicitly non-executable.

Roll back this stage by reverting its ordinary local commits; historical AGENTS bytes remain in the archive and accepted base. No workflow or resource migration is needed. H1 independent review is required before H2 edits; Full/Hosted proof remains separately pending.
