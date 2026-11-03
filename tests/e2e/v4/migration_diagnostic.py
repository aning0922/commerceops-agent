"""Root-window-only migration diagnostic. No resources are provisioned here.

CLI: python -m tests.e2e.v4.migration_diagnostic --public-migration-sha256 HEX
Uses the original DatabaseSettings/migrate entrypoint; only Root's fresh owned
container env may supply COMMERCEOPS_DB_* and its newly generated password file.
The outer Root supervisor must enforce the absolute UTC/cleanup deadline.
"""

import argparse
import ast
import hashlib
import json
import os
import re
from collections.abc import Callable, Iterator
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
PUBLIC = "backend/migrations/versions/0024_v4_demo_foundation.py"
TYPES = frozenset(
    {
        "Exception",
        "RuntimeError",
        "ValueError",
        "ValidationError",
        "OSError",
        "FileNotFoundError",
        "PermissionError",
        "OperationalError",
        "ProgrammingError",
        "IntegrityError",
        "DataError",
        "InternalError",
        "DatabaseError",
        "DBAPIError",
        "StatementError",
        "SyntaxError",
        "UndefinedTable",
        "UndefinedColumn",
        "UndefinedFunction",
        "InvalidFunctionDefinition",
        "DuplicateObject",
        "InvalidTableDefinition",
        "InvalidForeignKey",
        "CheckViolation",
        "ForeignKeyViolation",
        "UniqueViolation",
        "NotNullViolation",
        "InsufficientPrivilege",
        "InvalidPassword",
        "InvalidAuthorizationSpecification",
        "ConnectionFailure",
        "ConnectionException",
        "CannotConnectNow",
        "InvalidTextRepresentation",
        "CompileError",
        "ArgumentError",
        "InvalidRequestError",
        "CommandError",
        "AssertionError",
        "TypeError",
        "KeyError",
    }
)


def public_sql(expected: str) -> tuple[Path, frozenset[str]]:
    path = ROOT / PUBLIC
    if not re.fullmatch(r"[a-f0-9]{64}", expected) or path.is_symlink():
        raise ValueError("public migration fingerprint required")
    raw = path.read_bytes()
    if len(raw) > 1_000_000 or hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError("public migration fingerprint mismatch")
    tree = ast.parse(raw)
    strings = frozenset(
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and type(node.value) is str
        and re.match(r"\s*(CREATE|ALTER|GRANT|REVOKE|DROP|DO|SELECT)\b", node.value)
    )
    return path.resolve(), strings


def attribute(value: object, name: str) -> Any:
    try:
        return getattr(value, name, None)
    except Exception:
        return None


def diagnostic(
    error: BaseException, path: Path, approved_sql: frozenset[str]
) -> list[dict[str, Any]]:
    pending: list[BaseException] = [error]
    seen: set[int] = set()
    result: list[dict[str, Any]] = []
    while pending and len(result) < 8:
        current = pending.pop(0)
        if id(current) in seen:
            continue
        seen.add(id(current))
        state = attribute(current, "sqlstate")
        diag = attribute(current, "diag")
        if diag is None:
            diag = attribute(attribute(current, "orig"), "diag")
        position = attribute(diag, "statement_position")
        if type(position) is str and re.fullmatch(r"[1-9][0-9]{0,6}", position):
            position = int(position)
        if type(position) is not int or not 1 <= position <= 9_999_999:
            position = None
        statement = attribute(current, "statement")
        excerpt = None
        if type(statement) is str and statement in approved_sql:
            offset = max(0, (position or 1) - 1 - 60)
            excerpt = statement[offset : offset + 160]
        lines: list[int] = []
        tb = current.__traceback__
        while tb:
            if Path(tb.tb_frame.f_code.co_filename).resolve() == path:
                lines.append(tb.tb_lineno)
            tb = tb.tb_next
        result.append(
            {
                "exception_type": type(current).__name__
                if type(current).__name__ in TYPES
                else "OTHER",
                "sqlstate": state
                if type(state) is str and re.fullmatch(r"[0-9A-Z]{5}", state)
                else None,
                "statement_position": position,
                "public_migration_lines": lines[-4:],
                "public_sql_excerpt": excerpt,
            }
        )
        for name in ("orig", "__cause__", "__context__"):
            linked = attribute(current, name)
            if isinstance(linked, BaseException) and id(linked) not in seen:
                pending.append(linked)
    return result


@contextmanager
def suppress_raw_output() -> Iterator[None]:
    """Suppress library/Python/native stdout+stderr, including exception messages."""
    saved = [os.dup(1), os.dup(2)]
    try:
        with open(os.devnull, "w", encoding="utf-8") as sink:
            os.dup2(sink.fileno(), 1)
            os.dup2(sink.fileno(), 2)
            with redirect_stdout(sink), redirect_stderr(sink):
                yield
    finally:
        # Flush Python streams before restoring their underlying file descriptors.
        import sys

        sys.stdout.flush()
        sys.stderr.flush()
        for target, descriptor in zip((1, 2), saved, strict=True):
            os.dup2(descriptor, target)
            os.close(descriptor)


def run(expected: str, operation: Callable[[], None]) -> tuple[int, dict[str, Any]]:
    path = ROOT / PUBLIC
    approved: frozenset[str] = frozenset()
    stage = "PUBLIC_SOURCE_CHECK"
    try:
        with suppress_raw_output():
            path, approved = public_sql(expected)
            stage = "ORIGINAL_MIGRATE"
            operation()
    except Exception as error:
        with suppress_raw_output():
            chain = diagnostic(error, path, approved)
        return 1, {"status": "FAILED", "stage": stage, "tests": "NOT_RUN", "chain": chain}
    return 0, {"status": "MIGRATED", "stage": "ORIGINAL_MIGRATE", "tests": "NOT_RUN"}


def original_migrate() -> None:
    from commerceops.entrypoints.database import migrate
    from commerceops.infrastructure.database import DatabaseSettings

    migrate(DatabaseSettings())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--public-migration-sha256", required=True)
    args = parser.parse_args()
    code, report = run(args.public_migration_sha256, original_migrate)
    print(json.dumps(report, ensure_ascii=True))
    raise SystemExit(code)


if __name__ == "__main__":
    main()
