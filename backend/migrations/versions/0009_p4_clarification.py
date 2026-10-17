"""1:1入站绑定固定澄清回复；不创建业务task/job或模型预算。"""

from alembic import op

revision = "0009_p4_clarification"
down_revision = "0008_p4_feishu"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE business.p4_clarification_replies (
    id uuid PRIMARY KEY,inbox_id uuid NOT NULL UNIQUE REFERENCES business.inbox_events(id),
    organization_id uuid NOT NULL,shop_id uuid NOT NULL,principal_id uuid NOT NULL,
    identity_id uuid NOT NULL,chat_id text NOT NULL,chat_type text NOT NULL
    CHECK(chat_type IN ('p2p','group')),
    reason_code text NOT NULL CHECK(reason_code='REQUEST_NEEDS_CLARIFICATION'),
    template_version text NOT NULL CHECK(template_version='p4-clarification-v1'),
    provider_uuid uuid NOT NULL UNIQUE,status text NOT NULL DEFAULT 'pending'
    CHECK(status IN ('pending','sending','sent','unknown','dead')),
    attempts integer NOT NULL DEFAULT 0 CHECK(attempts BETWEEN 0 AND 1),
    claimed_by text,first_attempt_at timestamptz,message_id text,last_error text,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CHECK(status<>'pending' OR attempts=0),
    CHECK(status NOT IN ('sending','sent','unknown') OR attempts=1),
    CHECK((status='sent')=(message_id IS NOT NULL)),
    FOREIGN KEY(organization_id,shop_id) REFERENCES business.shops(organization_id,id),
    FOREIGN KEY(organization_id,identity_id,principal_id)
    REFERENCES business.identities(organization_id,id,principal_id))""")
    op.execute("""CREATE FUNCTION business.p4_immutable_clarification() RETURNS trigger
    LANGUAGE plpgsql AS $$ BEGIN
    IF TG_OP='DELETE' OR (NEW.id,NEW.inbox_id,NEW.organization_id,NEW.shop_id,NEW.principal_id,
    NEW.identity_id,NEW.chat_id,NEW.chat_type,NEW.reason_code,NEW.template_version,
    NEW.provider_uuid,NEW.created_at) IS DISTINCT FROM
    (OLD.id,OLD.inbox_id,OLD.organization_id,OLD.shop_id,OLD.principal_id,OLD.identity_id,
    OLD.chat_id,OLD.chat_type,OLD.reason_code,OLD.template_version,OLD.provider_uuid,OLD.created_at)
    OR (OLD.status IN ('sent','unknown','dead') AND NEW IS DISTINCT FROM OLD)
    OR (OLD.status='sending' AND NEW.status NOT IN ('sending','sent','unknown','dead'))
    OR (OLD.first_attempt_at IS NOT NULL AND
    NEW.first_attempt_at IS DISTINCT FROM OLD.first_attempt_at)
    OR (OLD.claimed_by IS NOT NULL AND NEW.claimed_by IS DISTINCT FROM OLD.claimed_by)
    OR NEW.attempts<OLD.attempts THEN
    RAISE EXCEPTION 'clarification identity or original send receipt is immutable'
    USING ERRCODE='23514'; END IF; RETURN NEW; END $$""")
    op.execute("""CREATE TRIGGER p4_immutable_clarification BEFORE UPDATE OR DELETE
    ON business.p4_clarification_replies FOR EACH ROW
    EXECUTE FUNCTION business.p4_immutable_clarification()""")
    op.execute("""CREATE TRIGGER p4_no_truncate BEFORE TRUNCATE
    ON business.p4_clarification_replies FOR EACH STATEMENT
    EXECUTE FUNCTION business.reject_inventory_mutation()""")


def downgrade() -> None:
    raise RuntimeError("P4 clarification receipt history cannot be removed destructively")
