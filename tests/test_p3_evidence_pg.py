"""实际PG证据身份/显式文法/参数来源/确定性复算负例。"""

import asyncio
import copy
from uuid import UUID, uuid4

import pytest
from commerceops.domain.commerce_values import canonical_bytes, facts_hash
from commerceops.infrastructure.database import connect
from commerceops.infrastructure.inventory_repository import AnalysisUnsafe
from commerceops.infrastructure.replenishment_execution import ExecutionStore
from commerceops.infrastructure.replenishment_repository import ApprovalStore
from commerceops.infrastructure.worker_lock import WorkerSession, open_async
from commerceops.workflows.inventory_analysis import MockCollectorFactory
from psycopg import sql
from psycopg.errors import CheckViolation, ForeignKeyViolation
from psycopg.types.json import Jsonb

from tests.inventory_support import DIRECTORY
from tests.p3_support import P3Fixture
from tests.test_p3_approval_pg import start
from tests.test_p3_execution_pg import execute
from tests.test_p3_pg import fixture as fixture

pytestmark = pytest.mark.integration


def test_actual_pg_observation_wrong_ids_lineage_discriminator_hash_mutation_delete_rejected(
    fixture: P3Fixture,
) -> None:
    f = fixture
    task, child, receipt = execute(f)
    child.stop_clean()
    with connect(f.inventory.owner) as db:
        original = db.execute(
            "SELECT * FROM business.p3_observations WHERE task_id=%s", (task,)
        ).fetchone()
        binding = db.execute(
            "SELECT * FROM business.p3_task_sources WHERE task_id=%s", (task,)
        ).fetchone()
        assert original and binding
        for changes in (
            {"id": binding["snapshot_id"]},
            {"report_id": binding["source_report_id"]},
            {"id": binding["source_report_id"]},
            {"report_id": binding["snapshot_id"]},
            {"task_id": uuid4()},
            {"shop_id": uuid4()},
            {"original_facts_hash": "0" * 64},
            {"generation_plan_id": uuid4()},
            {"material_hash": "malformed"},
            {"report_id": original["id"]},
        ):
            clone = {**original, "id": uuid4(), "report_id": uuid4(), **changes}
            insert_statement = sql.SQL(
                "INSERT INTO business.p3_observations({}) VALUES({})"
            ).format(
                sql.SQL(",").join(map(sql.Identifier, clone)),
                sql.SQL(",").join(sql.Placeholder() for _ in clone),
            )
            with pytest.raises((CheckViolation, ForeignKeyViolation)), db.transaction():
                db.execute(
                    insert_statement,
                    tuple(
                        Jsonb(value) if isinstance(value, dict) else value
                        for value in clone.values()
                    ),
                )
                db.execute("SET CONSTRAINTS ALL IMMEDIATE")
        for statement in (
            "UPDATE business.p3_observations SET generation_config_version='fake' WHERE task_id=%s",
            "UPDATE business.p3_observations SET report='{}'::jsonb WHERE task_id=%s",
            "DELETE FROM business.p3_observations WHERE task_id=%s",
            "UPDATE business.replenishment_plans SET evidence_kind='p3_observation',"
            "p3_observation_id=gen_random_uuid() WHERE task_id=%s",
            "UPDATE business.replenishment_plans SET p3_observation_id=gen_random_uuid() WHERE "
            "task_id=%s",
            "UPDATE business.p3_task_sources SET facts_hash=repeat('0',64) WHERE task_id=%s",
        ):
            with pytest.raises(CheckViolation), db.transaction():
                db.execute(statement, (task,))
    assert (
        f.client.get(f"/api/v1/tasks/{task}/report?report_id={original['report_id']}").status_code
        == 200
    )
    assert f.client.get(f"/api/v1/tasks/{task}/report?report_id={uuid4()}").status_code == 404
    assert (
        f.client.get(f"/api/v1/tasks/{task}/execution").json()["execution_id"]
        == receipt["execution_id"]
    )


def test_actual_pg_source_parameters_rule_config_or_balanced_forged_quantity_fail_authority(
    fixture: P3Fixture,
) -> None:
    f = fixture
    task_id = UUID(f.create(f.new_cycle())["task_id"])
    child, _ = start(f, task_id)
    child.until("after_ready")
    child.stop_clean()

    async def probe() -> None:
        session = WorkerSession(f.config.database, f.inventory.data.organization)
        await session.start()
        try:
            store = ExecutionStore(
                ApprovalStore(f.config, session), MockCollectorFactory(DIRECTORY)
            )
            async with await open_async(f.config.database) as db:
                task = await (
                    await db.execute(
                        "SELECT * FROM business.business_tasks WHERE id=%s", (task_id,)
                    )
                ).fetchone()
                binding = await (
                    await db.execute(
                        "SELECT * FROM business.p3_task_sources WHERE task_id=%s", (task_id,)
                    )
                ).fetchone()
                plan = await (
                    await db.execute(
                        "SELECT * FROM business.replenishment_plans WHERE task_id=%s", (task_id,)
                    )
                ).fetchone()
                assert task and binding and plan
                await store.evidence(db, task, plan, binding)
                for field, value in (
                    ("parameters", {**binding["parameters"], "L": 4}),
                    ("source_report_id", uuid4()),
                    ("snapshot_id", uuid4()),
                    ("facts_hash", "0" * 64),
                ):
                    with pytest.raises(AnalysisUnsafe):
                        await store.evidence(db, task, plan, {**binding, field: value})
                for variant in ("quantity", "config", "source_hash"):
                    forged = copy.deepcopy(plan)
                    if variant == "quantity":
                        forged["content"]["items"][0]["quantity"] += 1
                    elif variant == "config":
                        forged["content"]["config_version"] = "unproven-rule-version"
                    else:
                        forged["content"]["source"]["facts_hash"] = "0" * 64
                    forged["plan_hash"] = facts_hash(forged["content"])
                    forged["canonical_content"] = canonical_bytes(forged["content"]).decode()
                    with pytest.raises(AnalysisUnsafe):
                        await store.evidence(db, task, forged, binding)
        finally:
            await session.close(clean=True)

    asyncio.run(probe())
    with connect(f.config.database) as db:
        assert db.execute(
            "SELECT count(*) AS n FROM business.executions WHERE task_id=%s", (task_id,)
        ).fetchone() == {"n": 0}
