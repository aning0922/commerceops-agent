"""当前实例SDK方法有限窗口/消耗/unknown账本，不触平台或修改业务outbox。"""

from alembic import op

revision = "0011_p4_sdk_ledger"
down_revision = "0010_p4_base_delivery"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE business.p4_sdk_windows (
    id uuid PRIMARY KEY,organization_id uuid NOT NULL,shop_id uuid NOT NULL,
    expires_at timestamptz NOT NULL,configured_enabled boolean NOT NULL,method_caps jsonb NOT NULL,
    verification_mode text NOT NULL CHECK(verification_mode IN ('offline_fake','controlled_sdk')),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    FOREIGN KEY(organization_id,shop_id) REFERENCES business.shops(organization_id,id))""")
    op.execute("""CREATE TABLE business.p4_sdk_calls (
    id uuid PRIMARY KEY,window_id uuid NOT NULL REFERENCES business.p4_sdk_windows(id),
    subject_id uuid NOT NULL,task_id uuid REFERENCES business.business_tasks(id),
    scope_kind text NOT NULL CHECK(scope_kind IN
    ('preflight','base_projection','approval_card','task_result','clarification')),
    method text NOT NULL CHECK(method IN ('im.v1.message.create',
    'bitable.v1.app_table_record.create','bitable.v1.app_table_record.list',
    'bitable.v1.app_table_record.update','bitable.v1.app_table.list','bitable.v1.app_table_field.list')),
    status text NOT NULL DEFAULT 'started'
    CHECK(status IN ('started','returned','raised','not_called')),
    http_status integer,provider_code integer,
    started_at timestamptz NOT NULL DEFAULT clock_timestamp(),completed_at timestamptz,
    CHECK((status='started')=(completed_at IS NULL)),
    CHECK((scope_kind IN ('preflight','clarification'))=(task_id IS NULL)))""")
    op.execute("""CREATE TABLE business.p4_im_deliveries (
    outbox_id uuid PRIMARY KEY REFERENCES business.outbox(id),
    organization_id uuid NOT NULL,shop_id uuid NOT NULL,task_id uuid NOT NULL,
    identity_id uuid NOT NULL REFERENCES business.identities(id),
    approval_id uuid REFERENCES business.approvals(id),
    kind text NOT NULL CHECK(kind IN ('approval_card','task_result')),
    chat_id text NOT NULL,chat_type text NOT NULL CHECK(chat_type IN ('p2p','group')),
    provider_uuid uuid NOT NULL UNIQUE,payload jsonb NOT NULL,payload_hash text NOT NULL,
    verification_mode text NOT NULL CHECK(verification_mode IN ('offline_fake','controlled_sdk')),
    status text NOT NULL DEFAULT 'pending'
    CHECK(status IN ('pending','sending','sent','unknown','dead')),
    attempts integer NOT NULL DEFAULT 0 CHECK(attempts BETWEEN 0 AND 1),
    claimed_by text,first_attempt_at timestamptz,message_id text,last_error text,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CHECK((kind='approval_card')=(approval_id IS NOT NULL)),
    CHECK((status='sent')=(message_id IS NOT NULL)),
    CHECK(status NOT IN ('sending','sent','unknown') OR attempts=1),
    FOREIGN KEY(organization_id,shop_id,task_id)
    REFERENCES business.business_tasks(organization_id,shop_id,id))""")
    op.execute("""CREATE FUNCTION business.p4_sdk_call_immutable() RETURNS trigger
    LANGUAGE plpgsql AS $$ BEGIN
    IF TG_OP='DELETE' OR (NEW.id,NEW.window_id,NEW.subject_id,NEW.task_id,NEW.scope_kind,
    NEW.method,NEW.started_at) IS DISTINCT FROM (OLD.id,OLD.window_id,OLD.subject_id,
    OLD.task_id,OLD.scope_kind,OLD.method,OLD.started_at)
    OR (OLD.status<>'started' AND NEW IS DISTINCT FROM OLD) THEN
    RAISE EXCEPTION 'P4 SDK original call is immutable' USING ERRCODE='23514'; END IF;
    RETURN NEW; END $$""")
    op.execute("""CREATE TRIGGER p4_sdk_call_immutable BEFORE UPDATE OR DELETE
    ON business.p4_sdk_calls FOR EACH ROW EXECUTE FUNCTION business.p4_sdk_call_immutable()""")
    op.execute("""CREATE TRIGGER p4_sdk_window_immutable BEFORE UPDATE OR DELETE
    ON business.p4_sdk_windows FOR EACH ROW
    EXECUTE FUNCTION business.reject_inventory_mutation()""")
    op.execute("""CREATE FUNCTION business.p4_im_immutable() RETURNS trigger
    LANGUAGE plpgsql AS $$ BEGIN
    IF TG_OP='DELETE' OR (NEW.outbox_id,NEW.organization_id,NEW.shop_id,NEW.task_id,
    NEW.identity_id,NEW.approval_id,NEW.kind,NEW.chat_id,NEW.chat_type,NEW.provider_uuid,
    NEW.payload,NEW.payload_hash,NEW.verification_mode,NEW.created_at)
    IS DISTINCT FROM (OLD.outbox_id,OLD.organization_id,OLD.shop_id,OLD.task_id,
    OLD.identity_id,OLD.approval_id,OLD.kind,OLD.chat_id,OLD.chat_type,OLD.provider_uuid,
    OLD.payload,OLD.payload_hash,OLD.verification_mode,OLD.created_at)
    OR (OLD.status IN ('sent','unknown','dead') AND NEW IS DISTINCT FROM OLD)
    OR NEW.attempts<OLD.attempts
    OR (OLD.first_attempt_at IS NOT NULL
    AND NEW.first_attempt_at IS DISTINCT FROM OLD.first_attempt_at)
    OR (OLD.claimed_by IS NOT NULL AND NEW.claimed_by IS DISTINCT FROM OLD.claimed_by) THEN
    RAISE EXCEPTION 'P4 original IM identity/unknown is immutable' USING ERRCODE='23514'; END IF;
    RETURN NEW; END $$""")
    op.execute("""CREATE TRIGGER p4_im_immutable BEFORE UPDATE OR DELETE
    ON business.p4_im_deliveries
    FOR EACH ROW EXECUTE FUNCTION business.p4_im_immutable()""")
    for table in ("p4_sdk_windows", "p4_sdk_calls", "p4_im_deliveries"):
        op.execute(f"""CREATE TRIGGER p4_sdk_no_truncate BEFORE TRUNCATE ON business.{table}
        FOR EACH STATEMENT EXECUTE FUNCTION business.reject_inventory_mutation()""")


def downgrade() -> None:
    raise RuntimeError("P4 SDK unknown method history cannot be removed destructively")
