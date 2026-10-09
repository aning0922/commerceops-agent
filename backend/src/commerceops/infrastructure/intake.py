"""T1 PG adapter；返回在业务事务提交后，无网络/模型调用。"""

import hashlib
import json
from collections.abc import Callable
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb

from commerceops.application.intake import IntakeReceipt, TestInbound, TrustedTestContext
from commerceops.infrastructure.database import DatabaseSettings, connect
from commerceops.infrastructure.repository import PersistenceConflict, TaskRepository, TaskScope


class PgTestIntakeStore:
    def __init__(self, settings: DatabaseSettings):
        self.settings = settings

    def accept(
        self,
        context: TrustedTestContext,
        event: TestInbound,
        hook: Callable[[str], None] | None = None,
    ) -> IntakeReceipt:
        settings = self.settings
        if context.mode != "test" or not event.event_id or not event.workflow_version:
            raise ValueError("explicit technical test context required")
        if "schema_version" not in event.normalized_request:
            raise ValueError("schema_version required")
        semantic = {
            "organization": str(context.organization_id),
            "shop": str(context.shop_id),
            "actor": str(context.principal_id),
            "conversation": str(context.conversation_id),
            "request": event.normalized_request,
            "workflow_version": event.workflow_version,
        }
        digest = hashlib.sha256(
            json.dumps(semantic, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
        ).hexdigest()

        def point(name: str) -> None:
            if hook is not None:
                hook(name)

        with connect(settings) as db:
            # 锁当前身份，技术 test 不跳过 enabled/role/org/shop/conversation 校验。
            actor = db.execute(
                """SELECT p.id FROM business.principals p
                JOIN business.shops s ON s.organization_id=p.organization_id
                JOIN business.conversations c ON c.organization_id=p.organization_id
                AND c.actor_id=p.id
                JOIN business.organizations o ON o.id=p.organization_id
                WHERE p.organization_id=%s AND p.id=%s AND p.enabled AND 'operator'=ANY(p.roles)
                AND s.id=%s AND s.environment='test' AND c.id=%s
                AND o.feishu_app_id=%s AND o.feishu_tenant_key=%s FOR UPDATE OF p""",
                (
                    context.organization_id,
                    context.principal_id,
                    context.shop_id,
                    context.conversation_id,
                    event.app_id,
                    event.tenant_key,
                ),
            ).fetchone()
            if actor is None:
                raise PersistenceConflict("test actor or scope rejected")
            inbox_id = uuid4()
            inserted = db.execute(
                """INSERT INTO business.inbox_events
                (id,organization_id,shop_id,source,app_id,tenant_key,event_id,message_id,
                 payload_hash,sanitized_payload,status)
                VALUES (%s,%s,%s,'technical_test',%s,%s,%s,%s,%s,%s,'received')
                ON CONFLICT DO NOTHING RETURNING id""",
                (
                    inbox_id,
                    context.organization_id,
                    context.shop_id,
                    event.app_id,
                    event.tenant_key,
                    event.event_id,
                    event.message_id,
                    digest,
                    Jsonb({"schema_version": 1, "source_mode": "postgres_technical"}),
                ),
            ).fetchone()
            point("after_inbox")
            if inserted is None:
                rows = db.execute(
                    """SELECT * FROM business.inbox_events WHERE source='technical_test'
                    AND app_id=%s AND tenant_key=%s AND (event_id=%s OR message_id=%s)""",
                    (event.app_id, event.tenant_key, event.event_id, event.message_id),
                ).fetchall()
                if (
                    len(rows) != 1
                    or rows[0]["payload_hash"] != digest
                    or rows[0]["task_id"] is None
                ):
                    raise PersistenceConflict("inbound key semantic conflict")
                task_id = UUID(str(rows[0]["task_id"]))
            else:
                task_id = uuid4()
                db.execute(
                    """INSERT INTO business.business_tasks
                    (id,organization_id,shop_id,conversation_id,requester_id,kind,
                     normalized_request,workflow_version,thread_id)
                    VALUES (%s,%s,%s,%s,%s,'technical_test',%s,%s,%s)""",
                    (
                        task_id,
                        context.organization_id,
                        context.shop_id,
                        context.conversation_id,
                        context.principal_id,
                        Jsonb(event.normalized_request),
                        event.workflow_version,
                        str(task_id),
                    ),
                )
                point("after_task")
            repo = TaskRepository(db, TaskScope(context.organization_id, context.shop_id))
            job_id = repo.enqueue(task_id, "analyze", f"analyze:{task_id}", f"task:{task_id}")
            point("after_job")
            if inserted is not None:
                db.execute(
                    """UPDATE business.inbox_events SET task_id=%s,status='processed',
                           updated_at=clock_timestamp() WHERE id=%s""",
                    (task_id, inbox_id),
                )
                db.execute(
                    """INSERT INTO business.audit_events
                    (id,organization_id,task_id,actor_id,source,action,entity_type,entity_id,trace_id)
                    VALUES (%s,%s,%s,%s,'technical_test','task_accepted','task',%s,%s)""",
                    (
                        uuid4(),
                        context.organization_id,
                        task_id,
                        context.principal_id,
                        str(task_id),
                        uuid4(),
                    ),
                )
            receipt = IntakeReceipt(task_id, job_id, str(task_id), event.workflow_version)
            point("before_commit")
        point("after_commit")
        return receipt
