"""正式平台身份桥接与入站回执；旧probe/旧outbox禁发约束保留。"""

from alembic import op

revision = "0008_p4_feishu"
down_revision = "0007_p3_execution"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE OR REPLACE FUNCTION business.lock_p3_permission(
    actor uuid,org uuid,shop uuid,identity uuid,auth bigint,requested_role text)
    RETURNS boolean LANGUAGE plpgsql VOLATILE SECURITY DEFINER
    SET search_path=pg_catalog,business AS $$ BEGIN
    PERFORM 1 FROM business.principals p WHERE p.id=actor AND p.organization_id=org
    AND p.enabled AND p.auth_version=auth AND requested_role=ANY(p.roles) FOR SHARE;
    IF NOT FOUND THEN RETURN false; END IF;
    RETURN EXISTS(SELECT 1 FROM business.principal_shop_scopes s
    JOIN business.principal_role_shop_grants g ON g.principal_id=s.principal_id
    AND g.organization_id=s.organization_id AND g.shop_id=s.shop_id
    WHERE s.principal_id=actor AND s.organization_id=org AND s.shop_id=shop
    AND s.enabled AND g.enabled AND g.role=requested_role
    AND EXISTS(SELECT 1 FROM business.identities i
    WHERE i.id=identity AND i.principal_id=actor AND i.organization_id=org
    AND ((i.provider='web' AND EXISTS(SELECT 1 FROM business.web_credentials c
    WHERE c.identity_id=i.id AND c.principal_id=i.principal_id
    AND c.organization_id=i.organization_id AND c.enabled))
    OR (i.provider='feishu' AND EXISTS(SELECT 1 FROM business.organizations o
    WHERE o.id=i.organization_id AND o.feishu_app_id=i.app_id
    AND o.feishu_tenant_key=i.tenant_key)))) FOR SHARE OF s,g);
    END $$""")
    # 原约束自动名按实际catalog中的定义选择，不能猜CHECK序号。
    op.execute("""DO $$ DECLARE constraint_name text; BEGIN
    SELECT conname INTO STRICT constraint_name FROM pg_constraint
    WHERE conrelid='business.approvals'::regclass AND contype='c'
    AND pg_get_constraintdef(oid) LIKE '%decision_source%';
    EXECUTE format('ALTER TABLE business.approvals DROP CONSTRAINT %I',constraint_name);
    END $$""")
    op.execute("""ALTER TABLE business.approvals ADD CONSTRAINT p4_decision_source
    CHECK(decision_id IS NULL OR (decision_action IN
    ('approve','reject','approve_with_assumptions','reject_assumptions')
    AND decision_payload_hash ~ '^[a-f0-9]{64}$' AND decided_by IS NOT NULL
    AND decided_at IS NOT NULL AND decision_source IN ('web','feishu')
    AND decision_request_key IS NOT NULL))""")
    op.execute("""CREATE TABLE business.p4_inbox_receipts (
    inbox_id uuid PRIMARY KEY REFERENCES business.inbox_events(id),
    identity_id uuid NOT NULL REFERENCES business.identities(id),
    result jsonb NOT NULL CHECK(jsonb_typeof(result)='object'),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp())""")
    op.execute("""CREATE TABLE business.p4_card_bindings (
    approval_id uuid PRIMARY KEY REFERENCES business.approvals(id),
    outbox_id uuid NOT NULL UNIQUE REFERENCES business.outbox(id),
    chat_id text NOT NULL,message_id text NOT NULL UNIQUE,
    source_mode text NOT NULL CHECK(source_mode IN ('offline_fake','feishu')),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp())""")
    for table in ("p4_inbox_receipts", "p4_card_bindings"):
        for event in ("UPDATE OR DELETE", "TRUNCATE"):
            op.execute(f"""CREATE TRIGGER p4_immutable_{event.split()[0].lower()}
            BEFORE {event} ON business.{table} FOR EACH STATEMENT
            EXECUTE FUNCTION business.reject_inventory_mutation()""")


def downgrade() -> None:
    raise RuntimeError("P4 audit/identity history cannot be downgraded destructively")
