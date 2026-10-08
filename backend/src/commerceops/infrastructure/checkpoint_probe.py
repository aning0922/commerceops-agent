"""隔离的 PG 技术回执；只在显式 test context 下使用，无正式审批/补货。"""

import hashlib
import json
from typing import Any
from uuid import UUID, uuid4

from psycopg import AsyncConnection

from commerceops.application.runner import RunRequest
from commerceops.infrastructure.database import DatabaseSettings
from commerceops.infrastructure.queue import OwnershipLost
from commerceops.infrastructure.repository import PersistenceConflict
from commerceops.infrastructure.worker_lock import WorkerSession, open_async


class ProbeUnsafe(Exception):
    """不可解释的技术状态；必须持久标记而非从 START 重建。"""


def request_hash(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(encoded.encode()).hexdigest()


class ProbeStore:
    def __init__(self, settings: DatabaseSettings, session: WorkerSession, *, mode: str):
        if mode != "test" or settings != session.settings:
            raise ValueError("explicit trusted test context required")
        self.settings = settings
        self.session = session

    async def guard(
        self, db: AsyncConnection[dict[str, Any]], r: RunRequest, *, authorize: bool = True,
    ) -> dict[str, Any]:
        await self.session.check()
        if r.owner != self.session.owner or r.thread_id != str(r.task_id):
            raise OwnershipLost("probe owner/thread mismatch")
        cursor = await db.execute(
            """SELECT t.*,p.enabled,p.roles,s.environment FROM business.jobs j
            JOIN business.business_tasks t ON t.id=j.task_id
            JOIN business.principals p ON p.id=t.requester_id AND p.organization_id=t.organization_id
            JOIN business.shops s ON s.id=t.shop_id AND s.organization_id=t.organization_id
            WHERE j.id=%s AND j.task_id=%s AND j.organization_id=%s AND j.shop_id=%s
            AND j.status='running' AND j.lease_owner=%s
            AND t.organization_id=j.organization_id AND t.shop_id=j.shop_id
            AND t.workflow_version=%s AND t.thread_id=%s FOR UPDATE OF j""",
            (r.job_id, r.task_id, r.organization_id, r.shop_id, r.owner,
             r.workflow_version, r.thread_id),
        )
        row = await cursor.fetchone()
        if not row:
            raise OwnershipLost("probe job/task identity changed")
        if authorize and (
            not row["enabled"] or "operator" not in row["roles"] or row["environment"] != "test"
        ):
            raise ProbeUnsafe("trusted technical principal/test shop required")
        return row

    async def load(self, r: RunRequest) -> dict[str, Any]:
        async with await open_async(self.settings) as db, db.transaction():
            task = await self.guard(db, r)
            cursor = await db.execute(
                """INSERT INTO checkpoint_probe.runs
                (task_id,organization_id,shop_id,thread_id,workflow_version,request_hash)
                VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT (task_id) DO NOTHING""",
                (r.task_id, r.organization_id, r.shop_id, r.thread_id, r.workflow_version,
                 request_hash(task["normalized_request"])),
            )
            cursor = await db.execute(
                """SELECT x.*,d.decision_ref,d.approved FROM checkpoint_probe.runs x
                LEFT JOIN checkpoint_probe.decisions d ON d.task_id=x.task_id
                WHERE x.task_id=%s""", (r.task_id,),
            )
            row = await cursor.fetchone()
            if not row or any(row[k] != v for k, v in {
                "organization_id": r.organization_id, "shop_id": r.shop_id,
                "thread_id": r.thread_id, "workflow_version": r.workflow_version,
                "request_hash": request_hash(task["normalized_request"]),
            }.items()):
                raise ProbeUnsafe("probe manifest mismatch")
            return row

    async def mark(self, r: RunRequest, status: str, *, started: bool = False) -> None:
        async with await open_async(self.settings) as db, db.transaction():
            await self.guard(db, r, authorize=status != "needs_attention")
            await db.execute(
                """UPDATE checkpoint_probe.runs SET status=%s,started=started OR %s
                WHERE task_id=%s""", (status, started, r.task_id),
            )
            if status == "needs_attention":
                await db.execute(
                    """UPDATE business.business_tasks SET state='needs_attention',
                    failure_code='CHECKPOINT_PROBE_UNSAFE',version=version+1,
                    updated_at=clock_timestamp() WHERE id=%s""", (r.task_id,),
                )

    async def decision(self, r: RunRequest, ref: str, hashed: str) -> bool:
        try:
            parsed = UUID(ref)
        except (ValueError, TypeError, AttributeError):
            raise ProbeUnsafe("only persisted decision reference is accepted") from None
        async with await open_async(self.settings) as db, db.transaction():
            task = await self.guard(db, r)
            if request_hash(task["normalized_request"]) != hashed:
                raise ProbeUnsafe("probe request changed after freeze")
            cursor = await db.execute(
                """SELECT approved FROM checkpoint_probe.decisions
                WHERE task_id=%s AND decision_ref=%s AND organization_id=%s AND shop_id=%s
                AND principal_id=%s AND workflow_version=%s AND request_hash=%s
                AND approval_mode='simulated'""",
                (r.task_id, parsed, r.organization_id, r.shop_id, task["requester_id"],
                 r.workflow_version, hashed),
            )
            row = await cursor.fetchone()
            if not row:
                raise ProbeUnsafe("persistent simulated decision binding mismatch")
            return bool(row["approved"])

    async def receipt(self, r: RunRequest, hashed: str, ref: str) -> str:
        if not await self.decision(r, ref, hashed):
            raise ProbeUnsafe("rejected probe cannot create receipt")
        async with await open_async(self.settings) as db, db.transaction():
            task = await self.guard(db, r)
            if request_hash(task["normalized_request"]) != hashed:
                raise ProbeUnsafe("probe request changed before receipt")
            key = f"p104:{r.task_id}"
            await db.execute(
                """INSERT INTO checkpoint_probe.receipts
                (operation_key,task_id,organization_id,shop_id,request_hash,result_ref)
                VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT (operation_key) DO NOTHING""",
                (key, r.task_id, r.organization_id, r.shop_id, hashed, str(uuid4())),
            )
            cursor = await db.execute(
                "SELECT * FROM checkpoint_probe.receipts WHERE operation_key=%s", (key,),
            )
            row = await cursor.fetchone()
            if not row or (row["task_id"], row["organization_id"], row["shop_id"],
                           row["request_hash"]) != (
                r.task_id, r.organization_id, r.shop_id, hashed,
            ):
                raise PersistenceConflict("probe operation key semantics conflict")
            result = str(row["result_ref"])
        # 返回时 receipt 已 COMMIT；调用者 barrier 在下一 Graph checkpoint 之前。
        return result

    async def existing_receipt(self, r: RunRequest, hashed: str) -> str | None:
        async with await open_async(self.settings) as db, db.transaction():
            await self.guard(db, r)
            cursor = await db.execute(
                "SELECT * FROM checkpoint_probe.receipts WHERE operation_key=%s",
                (f"p104:{r.task_id}",),
            )
            row = await cursor.fetchone()
            if row is None:
                return None
            if (row["task_id"],row["organization_id"],row["shop_id"],row["request_hash"]) != (
                r.task_id,r.organization_id,r.shop_id,hashed,
            ):
                raise ProbeUnsafe("existing receipt binding mismatch")
            return str(row["result_ref"])
