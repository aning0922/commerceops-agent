"""H1 local contracts only: validation is not authorization or a task scheduler."""

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Sha = Annotated[str, Field(pattern=r"^[0-9a-f]{40}$")]
Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Identifier = Annotated[str, Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,79}$")]
Check = Literal["fast", "impacted", "full"]
ApprovalReference = Annotated[
    str, Field(min_length=1, max_length=500, pattern=r"^\S(?:[^\r\n\x00]*\S)?$")
]


class StrictContract(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class ModelPolicy(StrictContract):
    model: Literal["gpt-6.1-sol", "gpt-6-astra"] = "gpt-6.1-sol"
    effort: Literal["medium", "high"] = "medium"
    astra_approval_ref: ApprovalReference | None = None
    allow_api_key_billing: Literal[False] = False

    @field_validator("allow_api_key_billing", mode="before")
    @classmethod
    def literal_false(cls, value: object) -> object:
        if value is not False:
            raise ValueError("API billing fallback must be the literal boolean false")
        return value

    @model_validator(mode="after")
    def approved_expert(self) -> Self:
        if self.model == "gpt-6-astra" and not self.astra_approval_ref:
            raise ValueError("Astra requires an explicit approval reference")
        return self


class Bounds(StrictContract):
    max_attempts: Annotated[int, Field(ge=1, le=2)] = 2
    max_turns_per_attempt: Annotated[int, Field(ge=1, le=6)] = 6
    max_wall_minutes: Annotated[int, Field(ge=1, le=45)] = 45


class Owner(StrictContract):
    owner_id: Identifier
    worktree: str
    branch: Annotated[str, Field(pattern=r"^codex/[a-zA-Z0-9._/-]+$")]

    @field_validator("worktree")
    @classmethod
    def absolute_worktree(cls, value: str) -> str:
        path = Path(value)
        if not path.is_absolute() or str(path.resolve()) != value:
            raise ValueError("worktree must be an absolute canonical path")
        return value


def safe_scope(value: str) -> str:
    path = PurePosixPath(value)
    if (
        not value
        or path.is_absolute()
        or ".." in path.parts
        or "\\" in value
        or value.startswith("-")
        or str(path) != value
        or any(char in value for char in "?[]\n\r\0")
    ):
        raise ValueError("scope must be a normalized repository path or trailing /** prefix")
    if "*" in value and (not value.endswith("/**") or "*" in value[:-3]):
        raise ValueError("only a trailing /** wildcard is supported")
    return value


def in_scope(path: str, scope: str) -> bool:
    return path == scope or (scope.endswith("/**") and path.startswith(scope[:-2]))


def scopes_overlap(left: str, right: str) -> bool:
    return (
        in_scope(left.removesuffix("/**"), right)
        or in_scope(right.removesuffix("/**"), left)
        or left == right
    )


class LocalApproval(StrictContract):
    """A reference to trusted approval; not a cryptographic authorization receipt."""

    approval_id: Identifier
    approval_ref: ApprovalReference
    scope: Literal["local_only"] = "local_only"


class TaskSpec(StrictContract):
    schema_version: Literal["harness-task-v3.1"]
    task_id: Identifier
    issue_ref: Annotated[str, Field(pattern=r"^GH-[1-9][0-9]*$")]
    spec_sha256: Digest
    base_sha: Sha
    summary: Annotated[str, Field(min_length=1, max_length=500)]
    state: Literal["DRAFT", "APPROVED", "READY"]
    risk: Literal["low", "normal", "high", "critical", "unknown"]
    owner: Owner
    allowed_files: Annotated[tuple[str, ...], Field(min_length=1)]
    forbidden_files: tuple[str, ...]
    model_policy: ModelPolicy = ModelPolicy()
    bounds: Bounds = Bounds()
    required_checks: Annotated[tuple[Check, ...], Field(min_length=1)]
    approval: LocalApproval | None = None

    @field_validator("allowed_files", "forbidden_files", mode="before")
    @classmethod
    def scopes(cls, values: object) -> tuple[str, ...]:
        if not isinstance(values, (list, tuple)) or any(
            not isinstance(item, str) for item in values
        ):
            raise ValueError("scope must be an array of strings")
        if len(values) != len(set(values)):
            raise ValueError("duplicate scope")
        return tuple(safe_scope(value) for value in values)

    @field_validator("required_checks", mode="before")
    @classmethod
    def immutable_checks(cls, values: object) -> object:
        return tuple(values) if isinstance(values, list) else values

    @model_validator(mode="after")
    def consistent(self) -> Self:
        if self.state != "DRAFT" and self.approval is None:
            raise ValueError("approved/ready tasks need a trusted local approval reference")
        if len(self.required_checks) != len(set(self.required_checks)):
            raise ValueError("duplicate required checks")
        if not {"fast", "impacted"}.issubset(self.required_checks):
            raise ValueError("fast and impacted checks are mandatory")
        if self.risk in {"high", "critical", "unknown"} and "full" not in self.required_checks:
            raise ValueError("high/critical/unknown risk requires full")
        if self.spec_sha256 != spec_digest(self.model_dump()):
            raise ValueError("spec digest mismatch")
        return self

    def permits(self, path: str) -> bool:
        safe_scope(path)
        return any(in_scope(path, item) for item in self.allowed_files) and not any(
            in_scope(path, item) for item in self.forbidden_files
        )


def spec_digest(spec: dict[str, object]) -> str:
    """Bind the complete normalized specification, including owner and approval."""
    payload = {key: value for key, value in spec.items() if key != "spec_sha256"}
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


class RunAttempt(StrictContract):
    schema_version: Literal["harness-attempt-v3.1"]
    task_id: Identifier
    spec_sha256: Digest
    attempt_id: Identifier
    attempt_number: Annotated[int, Field(ge=1, le=2)]
    turns: Annotated[int, Field(ge=0, le=6)]
    wall_seconds: Annotated[float, Field(ge=0, le=2700, allow_inf_nan=False)]
    state: Literal[
        "NOT_RUN", "RUNNING", "LOCAL_PASS", "FAILED", "INTERRUPTED", "NEEDS_RECONCILIATION"
    ]
    exit_code: int | None
    resolved_model: Literal["gpt-6.1-sol", "gpt-6-astra"]
    effort: Literal["medium", "high"]
    usage_source: Literal["UNKNOWN"] = "UNKNOWN"

    @model_validator(mode="after")
    def truthful_result(self) -> Self:
        if self.state in {"NOT_RUN", "RUNNING", "NEEDS_RECONCILIATION"}:
            if self.exit_code is not None:
                raise ValueError("unknown or nonterminal result cannot claim an exit code")
        elif self.state == "LOCAL_PASS" and self.exit_code != 0:
            raise ValueError("LOCAL_PASS requires exit 0")
        elif self.state in {"FAILED", "INTERRUPTED"} and self.exit_code in {None, 0}:
            raise ValueError("failure/interruption requires a nonzero exit")
        return self


def validate_attempt(spec: TaskSpec, attempt: RunAttempt, previous: list[RunAttempt]) -> None:
    if spec.state != "READY" or spec.approval is None:
        raise ValueError("only READY tasks can have attempts")
    if attempt.task_id != spec.task_id or attempt.spec_sha256 != spec.spec_sha256:
        raise ValueError("attempt must bind exact task/spec")
    if attempt.attempt_number > spec.bounds.max_attempts:
        raise ValueError("attempt cap exceeded")
    if attempt.turns > spec.bounds.max_turns_per_attempt:
        raise ValueError("turn cap exceeded")
    if attempt.wall_seconds > spec.bounds.max_wall_minutes * 60:
        raise ValueError("wall cap exceeded")
    if (attempt.resolved_model, attempt.effort) != (
        spec.model_policy.model,
        spec.model_policy.effort,
    ):
        raise ValueError("attempt model/effort does not match approved specification")
    if any(
        item.task_id != spec.task_id or item.spec_sha256 != spec.spec_sha256 for item in previous
    ):
        raise ValueError("previous attempts must belong to the same frozen task")
    if len({item.attempt_id for item in previous}) != len(previous):
        raise ValueError("duplicate previous attempt")
    if attempt.attempt_id in {item.attempt_id for item in previous}:
        raise ValueError("attempt ID already consumed")
    if [item.attempt_number for item in previous] != list(range(1, attempt.attempt_number)):
        raise ValueError("attempts must be contiguous and cannot reset")
    if any(item.state not in {"FAILED"} for item in previous):
        raise ValueError("reconcile interruption/unknown; do not blindly retry or rerun success")


def validate_owners(spec: TaskSpec, active: list[TaskSpec]) -> None:
    """Conservative single writer rule; not an atomic lease (H4 owns dispatch)."""
    for other in active:
        if (
            spec.owner.worktree == other.owner.worktree
            or spec.owner.branch == other.owner.branch
            or any(
                scopes_overlap(left, right)
                for left in spec.allowed_files
                for right in other.allowed_files
            )
        ):
            raise ValueError("active worktree, branch, or file ownership conflict")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("spec", type=Path)
    parser.add_argument("--attempt", type=Path)
    parser.add_argument("--previous", type=Path, action="append", default=[])
    parser.add_argument("--active", type=Path, action="append", default=[])
    args = parser.parse_args()
    try:
        spec = TaskSpec.model_validate_json(args.spec.read_text())
        validate_owners(
            spec, [TaskSpec.model_validate_json(path.read_text()) for path in args.active]
        )
        if args.attempt:
            validate_attempt(
                spec,
                RunAttempt.model_validate_json(args.attempt.read_text()),
                [RunAttempt.model_validate_json(path.read_text()) for path in args.previous],
            )
    except (ValueError, OSError):
        print(json.dumps({"status": "FAILED", "reason": "invalid local contract"}))
        raise SystemExit(1) from None
    print(json.dumps({"status": "VALID_LOCAL_CONTRACT", "execution_authorized": False}))


if __name__ == "__main__":
    main()
