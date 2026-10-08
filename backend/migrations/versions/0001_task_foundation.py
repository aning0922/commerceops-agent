"""最小任务持久层；冻结 SQL，不依赖未来应用模型。"""

from alembic import op

revision = "0001_task_foundation"
down_revision = None
branch_labels = None
depends_on = None

DDL = """
CREATE TABLE business.organizations (
 id uuid PRIMARY KEY, name text NOT NULL,
 feishu_tenant_key text NOT NULL UNIQUE, feishu_app_id text NOT NULL UNIQUE,
 created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE (id, feishu_app_id, feishu_tenant_key)
);
CREATE TABLE business.shops (
 id uuid PRIMARY KEY, organization_id uuid NOT NULL REFERENCES business.organizations(id),
 adapter_kind text NOT NULL, external_shop_key text NOT NULL, timezone text NOT NULL,
 currency text NOT NULL CHECK (currency ~ '^[A-Z]{3}$'), config_ref text NOT NULL,
 environment text NOT NULL CHECK (environment IN ('mock','test')),
 created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE (organization_id, id), UNIQUE (organization_id, adapter_kind, external_shop_key)
);
CREATE TABLE business.principals (
 id uuid PRIMARY KEY, organization_id uuid NOT NULL REFERENCES business.organizations(id),
 display_name text NOT NULL, enabled boolean NOT NULL DEFAULT true,
 roles text[] NOT NULL CHECK (roles <@ ARRAY['operator','approver','admin']::text[]),
 auth_version integer NOT NULL DEFAULT 1 CHECK (auth_version > 0),
 created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE (organization_id, id)
);
CREATE TABLE business.identities (
 id uuid PRIMARY KEY, organization_id uuid NOT NULL, principal_id uuid NOT NULL,
 provider text NOT NULL, app_id text NOT NULL, "tenant_key" text NOT NULL,
 external_subject text NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY (organization_id, principal_id) REFERENCES business.principals(organization_id,id),
 FOREIGN KEY (organization_id, app_id, tenant_key)
 REFERENCES business.organizations(id,feishu_app_id,feishu_tenant_key),
 UNIQUE (provider,app_id,tenant_key,external_subject)
);
CREATE TABLE business.conversations (
 id uuid PRIMARY KEY, organization_id uuid NOT NULL REFERENCES business.organizations(id),
 channel text NOT NULL, chat_id text NOT NULL, actor_id uuid NOT NULL, topic_key text NOT NULL,
 summary text, summary_version integer NOT NULL DEFAULT 1 CHECK (summary_version > 0),
 created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY (organization_id,actor_id) REFERENCES business.principals(organization_id,id),
 UNIQUE (organization_id,id,actor_id),
 UNIQUE (organization_id,channel,chat_id,actor_id,topic_key)
);
CREATE TABLE business.business_tasks (
 id uuid PRIMARY KEY, organization_id uuid NOT NULL, shop_id uuid NOT NULL,
 conversation_id uuid NOT NULL, requester_id uuid NOT NULL,
 kind text NOT NULL, normalized_request jsonb NOT NULL
 CHECK (jsonb_typeof(normalized_request) = 'object' AND normalized_request ? 'schema_version'),
 state text NOT NULL DEFAULT 'queued' CHECK (state IN
 ('queued','analyzing','awaiting_approval','executing','completed','rejected','expired',
 'needs_reapproval','failed','needs_attention')),
 version integer NOT NULL DEFAULT 1 CHECK (version > 0), active_plan_id uuid,
 workflow_version text NOT NULL, thread_id text NOT NULL UNIQUE CHECK (thread_id = id::text),
 failure_code text,
 created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY (organization_id,shop_id) REFERENCES business.shops(organization_id,id),
 FOREIGN KEY (organization_id,requester_id) REFERENCES business.principals(organization_id,id),
 FOREIGN KEY (organization_id,conversation_id,requester_id)
 REFERENCES business.conversations(organization_id,id,actor_id),
 CONSTRAINT active_plan_reserved CHECK (active_plan_id IS NULL),
 UNIQUE (organization_id,shop_id,id), UNIQUE (organization_id,id)
);
CREATE INDEX tasks_state_updated ON business.business_tasks(state,updated_at);
CREATE TABLE business.inbox_events (
 id uuid PRIMARY KEY, organization_id uuid NOT NULL, shop_id uuid NOT NULL,
 source text NOT NULL, app_id text NOT NULL, tenant_key text NOT NULL,
 event_id text NOT NULL, message_id text, payload_hash text NOT NULL,
 sanitized_payload jsonb NOT NULL CHECK
 (jsonb_typeof(sanitized_payload) = 'object' AND sanitized_payload ? 'schema_version'),
 received_at timestamptz NOT NULL DEFAULT now(), status text NOT NULL
 CHECK (status IN ('received','processed','rejected')), task_id uuid,
 created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY (organization_id,shop_id) REFERENCES business.shops(organization_id,id),
 FOREIGN KEY (organization_id,app_id,tenant_key)
 REFERENCES business.organizations(id,feishu_app_id,feishu_tenant_key),
 FOREIGN KEY (organization_id,shop_id,task_id)
 REFERENCES business.business_tasks(organization_id,shop_id,id),
 UNIQUE (source,app_id,tenant_key,event_id)
);
CREATE UNIQUE INDEX inbox_message_unique
 ON business.inbox_events(source,app_id,tenant_key,message_id)
 WHERE message_id IS NOT NULL;
CREATE TABLE business.jobs (
 id uuid PRIMARY KEY, organization_id uuid NOT NULL, shop_id uuid NOT NULL, task_id uuid NOT NULL,
 kind text NOT NULL, dedupe_key text NOT NULL UNIQUE, payload_ref text NOT NULL,
 status text NOT NULL DEFAULT 'ready'
 CHECK (status IN ('ready','running','done','retry_wait','dead')),
 attempts integer NOT NULL DEFAULT 0 CHECK (attempts >= 0),
 available_at timestamptz NOT NULL DEFAULT now(), lease_owner text, lease_until timestamptz,
 last_error text,
 created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY (organization_id,shop_id,task_id)
 REFERENCES business.business_tasks(organization_id,shop_id,id),
 CHECK ((lease_owner IS NULL) = (lease_until IS NULL)),
 CHECK (status <> 'running' OR lease_owner IS NOT NULL)
);
CREATE INDEX jobs_ready ON business.jobs(available_at,id) WHERE status = 'ready';
CREATE TABLE business.audit_events (
 id uuid PRIMARY KEY, organization_id uuid NOT NULL REFERENCES business.organizations(id),
 task_id uuid, actor_id uuid, source text NOT NULL, action text NOT NULL,
 entity_type text NOT NULL, entity_id text NOT NULL, before_state jsonb, after_state jsonb,
 reason text, trace_id uuid NOT NULL, occurred_at timestamptz NOT NULL DEFAULT now(),
 created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY (organization_id,task_id) REFERENCES business.business_tasks(organization_id,id),
 FOREIGN KEY (organization_id,actor_id) REFERENCES business.principals(organization_id,id)
);
"""


def upgrade() -> None:
    for statement in DDL.split(";"):
        if statement.strip():
            op.execute(statement)
    op.execute("""
CREATE FUNCTION business.preserve_task_identity() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF (NEW.id, NEW.thread_id, NEW.organization_id, NEW.shop_id,
     NEW.conversation_id, NEW.requester_id, NEW.workflow_version)
 IS DISTINCT FROM (OLD.id, OLD.thread_id, OLD.organization_id, OLD.shop_id,
     OLD.conversation_id, OLD.requester_id, OLD.workflow_version) THEN
  RAISE EXCEPTION 'task identity is immutable' USING ERRCODE = '23514';
 END IF;
 RETURN NEW;
END $$
""")
    op.execute("""
CREATE TRIGGER preserve_task_identity BEFORE UPDATE ON business.business_tasks
 FOR EACH ROW EXECUTE FUNCTION business.preserve_task_identity()
""")

    op.execute("""
CREATE FUNCTION business.require_auth_version() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF (NEW.roles, NEW.enabled) IS DISTINCT FROM (OLD.roles, OLD.enabled)
    AND NEW.auth_version <> OLD.auth_version + 1 THEN
  RAISE EXCEPTION 'permission changes require next auth_version' USING ERRCODE = '23514';
 END IF;
 IF NEW.auth_version < OLD.auth_version THEN
  RAISE EXCEPTION 'auth_version cannot decrease' USING ERRCODE = '23514';
 END IF;
 RETURN NEW;
END $$
""")
    op.execute("""
CREATE TRIGGER require_auth_version BEFORE UPDATE ON business.principals
 FOR EACH ROW EXECUTE FUNCTION business.require_auth_version()
""")


def downgrade() -> None:
    # 历史不提供自动删除；空测试库通过删除本任务专用卷重建。
    raise RuntimeError("destructive downgrade is disabled; restore a verified backup")
