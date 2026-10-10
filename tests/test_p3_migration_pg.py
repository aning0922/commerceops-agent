"""先真实运行0004 P2完成图，再升级当前P3 head核对业务/三类checkpoint。"""

import asyncio
import hashlib
import shutil
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from commerceops.entrypoints.database import migrate, setup_checkpointer
from commerceops.infrastructure.database import DatabaseSettings, connect
from psycopg import sql

from tests.inventory_support import initialize, run_worker

pytestmark = pytest.mark.integration


def test_current_p3_preserves_real_completed_p2_and_checkpoint_bytes(tmp_path: Path) -> None:
    settings = DatabaseSettings()
    name = "p3_preserve_" + uuid4().hex
    owner = settings.model_copy(update={"name": name})
    old_migrations = tmp_path / "pre-p3"
    shutil.copytree("backend/migrations", old_migrations)
    for file in (old_migrations / "versions").glob("*.py"):
        if file.name[:4].isdigit() and int(file.name[:4]) > 4:
            file.unlink()
    tables = (
        "business.business_tasks",
        "business.commerce_snapshots",
        "business.snapshot_products",
        "business.snapshot_order_lines",
        "business.snapshot_refunds",
        "business.analysis_reports",
        "checkpoints.checkpoints",
        "checkpoints.checkpoint_blobs",
        "checkpoints.checkpoint_writes",
    )

    def snapshot() -> dict[str, tuple[int, str]]:
        result = {}
        with connect(owner) as db:
            for table in tables:
                rows = db.execute(
                    sql.SQL("SELECT row_to_json(t)::text AS body FROM {} t").format(
                        sql.Identifier(*table.split("."))
                    )
                ).fetchall()
                encoded = "\n".join(sorted(row["body"] for row in rows)).encode()
                result[table] = len(rows), hashlib.sha256(encoded).hexdigest()
        return result

    with psycopg.connect(**settings.kwargs(), autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        try:
            migrate(owner, migrations=old_migrations)
            asyncio.run(setup_checkpointer(owner))
            # 仅迁移保留探针用owner生成旧P2基线；P3运行权限由其他fixture单独证明。
            f = initialize(owner, owner)
            task, job = f.create()
            asyncio.run(run_worker(f, job))
            assert f.row(task)["state"] == "completed"
            before = snapshot()
            assert before["checkpoints.checkpoints"][0] == 3
            migrate(owner)
            assert snapshot() == before
            assert f.row(task)["state"] == "completed"
        finally:
            admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))
