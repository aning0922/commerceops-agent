"""PG 技术 fixture；无模型/平台连接/业务审批。"""

from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

from psycopg import Connection
from psycopg.types.json import Jsonb


@dataclass(frozen=True)
class Seed:
    organization: UUID
    shop: UUID
    principal: UUID
    conversation: UUID
    task: UUID
    app: str
    tenant: str


def seed(
    connection: Connection[dict[str, Any]],
    *,
    task: UUID | None = None,
    workflow_version: str = "g1-fixture-v1",
) -> Seed:
    data = Seed(uuid4(), uuid4(), uuid4(), uuid4(), task or uuid4(), str(uuid4()), str(uuid4()))
    connection.execute(
        """INSERT INTO business.organizations(id,name,feishu_app_id,feishu_tenant_key)
        VALUES (%s,%s,%s,%s)""",
        (data.organization, "PG technical fixture", data.app, data.tenant),
    )
    connection.execute(
        """INSERT INTO business.shops
        (id,organization_id,adapter_kind,external_shop_key,timezone,currency,config_ref,environment)
        VALUES (%s,%s,'mock',%s,'Asia/Shanghai','CNY','technical_fixture','test')""",
        (data.shop, data.organization, str(uuid4())),
    )
    connection.execute(
        """INSERT INTO business.principals(id,organization_id,display_name,roles)
        VALUES (%s,%s,'PG technical actor',ARRAY['operator'])""",
        (data.principal, data.organization),
    )
    connection.execute(
        """INSERT INTO business.identities
        (id,organization_id,principal_id,provider,app_id,tenant_key,external_subject)
        VALUES (%s,%s,%s,'technical_fixture',%s,%s,%s)""",
        (uuid4(), data.organization, data.principal, data.app, data.tenant, str(uuid4())),
    )
    connection.execute(
        """INSERT INTO business.conversations
        (id,organization_id,channel,chat_id,actor_id,topic_key)
        VALUES (%s,%s,'technical_fixture',%s,%s,'G1')""",
        (data.conversation, data.organization, str(uuid4()), data.principal),
    )
    connection.execute(
        """INSERT INTO business.business_tasks
        (id,organization_id,shop_id,conversation_id,requester_id,kind,
        normalized_request,workflow_version,thread_id)
        VALUES (%s,%s,%s,%s,%s,'technical_fixture',%s,%s,%s)""",
        (
            data.task,
            data.organization,
            data.shop,
            data.conversation,
            data.principal,
            Jsonb({"schema_version": 1, "source_mode": "postgres_technical"}),
            workflow_version,
            str(data.task),
        ),
    )
    return data


def inbox(connection: Connection[dict[str, Any]], data: Seed, *, event: str, message: str) -> None:
    connection.execute(
        """INSERT INTO business.inbox_events
        (id,organization_id,shop_id,source,app_id,tenant_key,event_id,message_id,
        payload_hash,sanitized_payload,status,task_id)
        VALUES (%s,%s,%s,'technical_fixture',%s,%s,%s,%s,'fixture_hash',%s,'processed',%s)""",
        (
            uuid4(),
            data.organization,
            data.shop,
            data.app,
            data.tenant,
            event,
            message,
            Jsonb({"schema_version": 1}),
            data.task,
        ),
    )
