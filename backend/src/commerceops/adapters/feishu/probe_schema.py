"""隔离技术 schema 的显式 owner 初始化；不属于正式业务 migration。"""

from commerceops.infrastructure.database import DatabaseSettings, connect

DDL = """
CREATE SCHEMA IF NOT EXISTS feishu_probe;
CREATE TABLE IF NOT EXISTS feishu_probe.cards (
 id uuid PRIMARY KEY, organization_id uuid NOT NULL, shop_id uuid NOT NULL,
 binding jsonb NOT NULL, nonce_sha256 text NOT NULL,
 expires_at timestamptz NOT NULL, chat_id text NOT NULL, message_id text NOT NULL,
 send_uuid uuid NOT NULL DEFAULT gen_random_uuid() UNIQUE,
 send_status text NOT NULL DEFAULT 'registered' CHECK
 (send_status IN ('registered','draft','inflight','sent','unknown')),
 decision text CHECK (decision IN ('approve_with_assumptions','reject_assumptions')),
 decided_by uuid, decided_value_sha256 text, decided_at timestamptz,
 FOREIGN KEY (organization_id,shop_id) REFERENCES business.shops(organization_id,id),
 FOREIGN KEY (organization_id,decided_by) REFERENCES business.principals(organization_id,id),
 UNIQUE (organization_id,shop_id,id),
 CHECK ((decision IS NULL) = (decided_by IS NULL)),
 CHECK ((decision IS NULL) = (decided_value_sha256 IS NULL)),
 CHECK ((decision IS NULL) = (decided_at IS NULL))
);
CREATE TABLE IF NOT EXISTS feishu_probe.receipts (
 id uuid PRIMARY KEY, organization_id uuid NOT NULL, shop_id uuid NOT NULL,
 app_id text NOT NULL, tenant_key text NOT NULL, kind text NOT NULL,
 message_id text, context_message_id text, probe_id uuid, actor_id uuid NOT NULL,
 payload_sha256 text NOT NULL, sanitized_payload jsonb NOT NULL, result text NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY (organization_id,shop_id) REFERENCES business.shops(organization_id,id),
 FOREIGN KEY (organization_id,app_id,tenant_key)
 REFERENCES business.organizations(id,feishu_app_id,feishu_tenant_key),
 FOREIGN KEY (organization_id,actor_id) REFERENCES business.principals(organization_id,id),
 FOREIGN KEY (organization_id,shop_id,probe_id)
 REFERENCES feishu_probe.cards(organization_id,shop_id,id),
 CHECK ((kind='message' AND message_id IS NOT NULL AND context_message_id IS NULL
 AND probe_id IS NULL) OR (kind='card' AND message_id IS NULL
 AND context_message_id IS NOT NULL AND probe_id IS NOT NULL)),
 UNIQUE(app_id,tenant_key,message_id)
);
CREATE TABLE IF NOT EXISTS feishu_probe.event_keys (
 app_id text NOT NULL, tenant_key text NOT NULL, event_id text NOT NULL,
 receipt_id uuid NOT NULL REFERENCES feishu_probe.receipts(id) DEFERRABLE INITIALLY DEFERRED,
 PRIMARY KEY(app_id,tenant_key,event_id)
);
CREATE TABLE IF NOT EXISTS feishu_probe.base_operations (
 id uuid PRIMARY KEY, organization_id uuid NOT NULL, shop_id uuid NOT NULL,
 app_token text NOT NULL, table_id text NOT NULL, client_token uuid NOT NULL UNIQUE,
 request_sha256 text NOT NULL, fields jsonb NOT NULL,
 pending_kind text NOT NULL DEFAULT 'create' CHECK(pending_kind IN ('create','update')),
 pending_fields jsonb, pending_sha256 text,
 status text NOT NULL DEFAULT 'ready' CHECK
 (status IN ('ready','inflight','succeeded','unknown','blocked','conflict')),
 record_id text, last_code integer, updated_at timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY (organization_id,shop_id) REFERENCES business.shops(organization_id,id)
);
GRANT USAGE ON SCHEMA feishu_probe TO commerceops_app;
GRANT SELECT, INSERT ON feishu_probe.receipts, feishu_probe.event_keys TO commerceops_app;
GRANT SELECT, INSERT, UPDATE ON feishu_probe.cards, feishu_probe.base_operations TO commerceops_app;
"""


def setup_probe_schema(settings: DatabaseSettings) -> None:
    if settings.user == "commerceops_app":
        raise ValueError("probe schema requires explicit deployment owner")
    with connect(settings) as connection:
        for statement in DDL.split(";"):
            if statement.strip():
                connection.execute(statement)
