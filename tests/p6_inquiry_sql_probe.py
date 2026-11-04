"""Root-run owned SQL diagnostic. Importing this module never connects or starts PG.

The caller supplies the explicitly owned PG service/settings and an outer deadline.
Only this process's new UUID database is created/dropped. stdout contains fixed-stage
booleans and sanitized SQLSTATE/constraint identifiers, never payloads or SQL text.
"""

import ast
import asyncio
import hashlib
import json
import os
import re
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, TextIO
from uuid import uuid4

import psycopg
from commerceops.application.commerce.readonly_inquiry_executor import NAMES, Tool, execute
from commerceops.application.commerce.readonly_inquiry_service_contracts import ResultPayload
from commerceops.entrypoints.database import grant_runtime, migrate, setup_checkpointer
from commerceops.infrastructure.database import DatabaseSettings, connect
from commerceops.infrastructure.queue import JobQueue
from commerceops.infrastructure.readonly_inquiry_store import InquiryConfig, InquiryStore
from commerceops.infrastructure.worker_lock import WorkerSession
from commerceops.workflows.readonly_inquiry import runtime_factory
from psycopg import sql
from psycopg.types.json import Jsonb

from tests.inventory_support import DIRECTORY
from tests.p3_support import initialize_p3
from tests.test_p6_inquiry_pg import InquiryFixture

STAGES = frozenset(
    {
        "bootstrap",
        "accept",
        "worker_start",
        "executor_complete",
        "json_shape",
        "terminal_function",
        "canonical",
        "hash",
        "size",
        "permission",
        "session",
        "table_check",
        "finish",
        "job_done",
        "cleanup",
    }
)


def constraint_identifier(value: str | None) -> str | None:
    if value is not None and re.fullmatch(r"readonly_inquiries_[a-z0-9_]{1,44}", value):
        return value
    return None


def frozen_result_schema() -> dict[str, Any]:
    path = Path(__file__).parents[1] / "backend/migrations/versions/0021_p6_readonly_inquiries.py"
    tree = ast.parse(path.read_text())
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "JSON_VALIDATOR"
            for target in node.targets
        ):
            source = ast.literal_eval(node.value)
            matched = re.search(r" schema jsonb := '(.*?)'::jsonb;", source, re.S)
            if matched is not None:
                value: dict[str, Any] = json.loads(matched.group(1))
                return value
    raise ValueError("FROZEN_SCHEMA_UNAVAILABLE")


def emit(
    output: TextIO,
    stage: str,
    ok: bool,
    error: BaseException | None = None,
    constraint: str | None = None,
) -> None:
    if stage not in STAGES:
        raise ValueError("UNKNOWN_DIAGNOSTIC_STAGE")
    state = None
    if isinstance(error, psycopg.Error):
        if error.sqlstate is not None and re.fullmatch(r"[0-9A-Z]{5}", error.sqlstate):
            state = error.sqlstate
        constraint = error.diag.constraint_name or constraint
    output.write(
        json.dumps(
            {
                "stage": stage,
                "ok": ok,
                "sqlstate": state,
                "constraint": constraint_identifier(constraint),
            }
        )
        + "\n"
    )
    output.flush()


async def diagnose(f: InquiryFixture, question: str, output: TextIO) -> bool:
    try:
        receipt = f.store.create(f.web.actor, f.request(question=question))
        emit(output, "accept", True)
    except Exception as error:
        emit(output, "accept", False, error)
        return False
    session = WorkerSession(f.web.config.database, f.web.actor.organization_id)
    stage = "bootstrap"
    try:
        await session.start()
        emit(output, "worker_start", True)
    except Exception as error:
        emit(output, "worker_start", False, error)
        return False
    try:
        queue = JobQueue(session, task_ids=frozenset({receipt.task_id}))
        job = await queue.claim()
        if job is None:
            emit(output, stage, False)
            return False
        row, previous = f.store.load(job)
        if previous is not None:
            emit(output, stage, False)
            return False
        f.store.mark(job)
        context, choice, authority, reader = await runtime_factory(f.store, session)(job, row)
        stage = "executor_complete"
        outcome = await execute(
            context, choice, authority, {name: Tool("read", reader) for name in NAMES}
        )
        payload = ResultPayload.from_outcome(outcome)
        complete = payload.status == "complete" and bool(payload.evidence_refs)
        emit(output, stage, complete)
        if not complete:
            return False
        body = payload.model_dump(mode="json")
        schema = frozen_result_schema()
        canonical = payload.model_dump_json()
        digest = hashlib.sha256(canonical.encode()).hexdigest()
        candidate = {
            "state": "completed",
            "result": body,
            "result_canonical": canonical,
            "result_hash": digest,
            "version": row["version"] + 2,
        }
        checks: list[tuple[str, str, tuple[Any, ...]]] = [
            (
                "json_shape",
                "SELECT business.inquiry_json_valid(%s,%s,%s) AS ok",
                (Jsonb(body), Jsonb(schema), Jsonb(schema)),
            ),
            (
                "terminal_function",
                "SELECT business.valid_inquiry_payload(%s,%s,%s,'completed',%s,%s) AS ok",
                (Jsonb(body), canonical, digest, job.workflow_version, context.source_binding),
            ),
            ("canonical", "SELECT %s::jsonb=%s AS ok", (canonical, Jsonb(body))),
            (
                "hash",
                "SELECT encode(sha256(convert_to(%s,'UTF8')),'hex')=%s AS ok",
                (canonical, digest),
            ),
            ("size", "SELECT octet_length(%s::text)<=1048576 AS ok", (canonical,)),
            (
                "permission",
                "SELECT business.lock_p3_permission(%s,%s,%s,%s,%s,'operator') AS ok",
                (
                    f.web.actor.principal_id,
                    f.web.actor.organization_id,
                    receipt.shop_id,
                    f.web.actor.identity_id,
                    f.web.actor.auth_version,
                ),
            ),
            (
                "session",
                "SELECT EXISTS(SELECT 1 FROM business.web_sessions WHERE id=%s "
                "AND revoked_at IS NULL AND absolute_expires_at>clock_timestamp() "
                "AND idle_expires_at>clock_timestamp()) AS ok",
                (f.web.actor.session_id,),
            ),
        ]
        # Separate transactions: one diagnostic error cannot poison subsequent checks.
        all_ok = True
        for stage, statement, parameters in checks:
            try:
                with connect(f.web.config.database) as db:
                    f.store.bound_transaction(db)
                    checked = db.execute(statement, parameters).fetchone()
                    ok = checked is not None and checked["ok"] is True
                    all_ok &= ok
                    emit(output, stage, ok)
            except Exception as error:
                all_ok = False
                emit(output, stage, False, error)
        stage = "table_check"
        with connect(f.web.config.database) as db:
            f.store.bound_transaction(db)
            constraints = db.execute("""SELECT conname,pg_get_expr(conbin,conrelid) AS expression
                FROM pg_constraint WHERE conrelid='business.readonly_inquiries'::regclass
                AND contype='c' ORDER BY conname""").fetchall()
        if not 1 <= len(constraints) <= 64:
            emit(output, stage, False)
            return False
        # Expressions come exclusively from the committed table's CHECK catalog,
        # evaluated over a composite candidate record; they are never printed.
        for check in constraints:
            name = constraint_identifier(check["conname"])
            if name is None:
                emit(output, stage, False)
                return False
            try:
                with connect(f.web.config.database) as db:
                    f.store.bound_transaction(db)
                    check_statement = sql.SQL("""WITH candidate AS (
                        SELECT (jsonb_populate_record(NULL::business.readonly_inquiries,
                        to_jsonb(i)||%s::jsonb)).* FROM business.readonly_inquiries i
                        WHERE i.task_id=%s) SELECT ({}) IS TRUE AS ok FROM candidate""").format(
                        sql.SQL(check["expression"])
                    )
                    checked = db.execute(
                        check_statement, (Jsonb(candidate), receipt.task_id)
                    ).fetchone()
                    ok = checked is not None and checked["ok"] is True
                    all_ok &= ok
                    emit(output, stage, ok, constraint=name)
            except Exception as error:
                all_ok = False
                emit(output, stage, False, error, name)
        stage = "finish"
        f.store.finish(job, payload)
        emit(output, stage, True)
        stage = "job_done"
        await queue.done(job)
        emit(output, stage, True)
        return all_ok
    except Exception as error:
        emit(output, stage, False, error)
        return False
    finally:
        await session.close(clean=True)


def run(question: str, output: TextIO) -> int:
    settings = DatabaseSettings()
    if settings.runtime_password_file is None:
        emit(output, "bootstrap", False)
        return 1
    owner = settings.model_copy(update={"name": "p6_inquiry_probe_" + uuid4().hex})
    app = owner.model_copy(
        update={
            "user": "commerceops_app",
            "password_file": settings.runtime_password_file,
        }
    )
    with psycopg.connect(
        **settings.kwargs(),
        autocommit=True,
        options="-c statement_timeout=5000 -c lock_timeout=1000",
    ) as admin:
        result = 1
        try:
            admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(owner.name)))
            migrate(owner)
            asyncio.run(setup_checkpointer(owner))
            grant_runtime(owner)
            with TemporaryDirectory(prefix="p6-inquiry-probe-") as directory:
                web = initialize_p3(owner, app, Path(directory))
                try:
                    f = InquiryFixture(
                        web,
                        InquiryStore(
                            web.config,
                            InquiryConfig(web.inventory.data.shop, DIRECTORY, enabled=True),
                        ),
                    )
                    emit(output, "bootstrap", True)
                    result = 0 if asyncio.run(diagnose(f, question, output)) else 1
                finally:
                    web.client.close()
        except Exception as error:
            emit(output, "bootstrap", False, error)
        finally:
            try:
                admin.execute(
                    sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(
                        sql.Identifier(owner.name)
                    )
                )
                emit(output, "cleanup", True)
            except Exception as error:
                emit(output, "cleanup", False, error)
                result = 1
        return result


def main() -> int:
    output = sys.stdout
    # Suppress third-party/bootstrap output, including exception formatting. Only
    # emit() writes to the saved output stream; no logging/report contains SQL data.
    with open(os.devnull, "w") as quiet, redirect_stdout(quiet), redirect_stderr(quiet):
        try:
            if len(sys.argv) != 1:
                emit(output, "bootstrap", False)
                return 1
            return run("库存 合成演示商品 100", output)
        except Exception as error:
            emit(output, "bootstrap", False, error)
            return 1


if __name__ == "__main__":
    raise SystemExit(main())
