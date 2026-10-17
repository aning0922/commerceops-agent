"""F02单请求/轮次/原T1消费；旧v1回复和0015原库不回填。"""

from alembic import op

revision = "0016_p4_clarification_requests"
down_revision = "0015_p4_read_replies"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE business.p4_clarification_requests (
    id uuid PRIMARY KEY,origin_inbox_id uuid NOT NULL UNIQUE REFERENCES business.inbox_events(id),
    organization_id uuid NOT NULL,shop_id uuid NOT NULL,app_id text NOT NULL,
    tenant_key text NOT NULL,principal_id uuid NOT NULL,identity_id uuid NOT NULL,
    auth_version bigint NOT NULL CHECK(auth_version>0),
    chat_id text NOT NULL,chat_type text NOT NULL CHECK(chat_type IN ('p2p','group')),
    workflow_version text NOT NULL CHECK(workflow_version='p3-inventory-replenishment-v1'),
    source_hash text NOT NULL CHECK(source_hash ~ '^[a-f0-9]{64}$'),
    request_key uuid NOT NULL UNIQUE,round bigint NOT NULL CHECK(round>0),
    context jsonb NOT NULL CHECK(jsonb_typeof(context)='object'),
    candidate jsonb NOT NULL CHECK(jsonb_typeof(candidate)='object'),
    candidate_hash text NOT NULL CHECK(candidate_hash ~ '^[a-f0-9]{64}$'),
    state text NOT NULL CHECK(state IN
    ('awaiting_parameters','awaiting_confirmation','consumed','expired')),
    task_id uuid,confirmed_inbox_id uuid REFERENCES business.inbox_events(id),
    created_at timestamptz NOT NULL,expires_at timestamptz NOT NULL,updated_at timestamptz NOT NULL,
    CHECK(expires_at=created_at+interval '15 minutes'),
    CHECK((state='consumed')=(task_id IS NOT NULL AND confirmed_inbox_id IS NOT NULL)),
    CHECK((task_id IS NULL)=(confirmed_inbox_id IS NULL)),
    CHECK(candidate->>'request_id'=id::text AND (candidate->>'round')::bigint=round),
    CHECK(candidate->>'workflow_version'=workflow_version),
    CHECK(candidate ?& ARRAY['schema_version','request_id','round','kind','workflow_version',
        'source','window','scope','parameters','parameter_sources','task_id']),
    CHECK(candidate->'source'=context->'source' AND candidate->'window'=context->'window'
        AND candidate->'scope'=context->'scope'),
    CHECK(state<>'awaiting_parameters' OR candidate->>'kind'='question'),
    CHECK(state NOT IN ('awaiting_confirmation','consumed') OR candidate->>'kind'='ready'),
    FOREIGN KEY(organization_id,shop_id) REFERENCES business.shops(organization_id,id),
    FOREIGN KEY(organization_id,app_id,tenant_key)
    REFERENCES business.organizations(id,feishu_app_id,feishu_tenant_key),
    FOREIGN KEY(organization_id,identity_id,principal_id)
    REFERENCES business.identities(organization_id,id,principal_id),
    FOREIGN KEY(organization_id,shop_id,task_id)
    REFERENCES business.business_tasks(organization_id,shop_id,id))""")
    op.execute("""CREATE INDEX p4_clarification_request_scope
    ON business.p4_clarification_requests(organization_id,shop_id,principal_id,chat_id,state)""")
    op.execute("""CREATE FUNCTION business.p4_immutable_clarification_request() RETURNS trigger
    LANGUAGE plpgsql AS $$ BEGIN
    IF TG_OP='DELETE' OR (NEW.id,NEW.origin_inbox_id,NEW.organization_id,NEW.shop_id,NEW.app_id,
    NEW.tenant_key,NEW.principal_id,NEW.identity_id,NEW.auth_version,NEW.chat_id,NEW.chat_type,
    NEW.workflow_version,NEW.source_hash,NEW.request_key,NEW.context,NEW.created_at,NEW.expires_at)
    IS DISTINCT FROM
    (OLD.id,OLD.origin_inbox_id,OLD.organization_id,OLD.shop_id,OLD.app_id,OLD.tenant_key,
    OLD.principal_id,OLD.identity_id,OLD.auth_version,OLD.chat_id,OLD.chat_type,OLD.workflow_version,
    OLD.source_hash,OLD.request_key,OLD.context,OLD.created_at,OLD.expires_at)
    OR (OLD.state IN ('consumed','expired') AND NEW IS DISTINCT FROM OLD)
    OR (NEW.candidate IS DISTINCT FROM OLD.candidate AND
        (NEW.round<>OLD.round+1 OR NEW.state NOT IN
        ('awaiting_parameters','awaiting_confirmation')))
    OR (NEW.candidate IS NOT DISTINCT FROM OLD.candidate AND NEW.round<>OLD.round)
    OR (NEW.state='expired' AND clock_timestamp()<NEW.expires_at)
    THEN RAISE EXCEPTION 'F02 identity, expiry, round or terminal state is immutable'
    USING ERRCODE='23514'; END IF;
    IF NEW.state='consumed' AND OLD.state<>'consumed' THEN
    IF OLD.state<>'awaiting_confirmation' OR clock_timestamp()>=NEW.expires_at
    OR NOT EXISTS(SELECT 1 FROM business.inbox_events i
    JOIN business.p4_inbox_receipts r ON r.inbox_id=i.id
    JOIN business.web_requests w ON w.request_key=
        NEW.request_key
    AND w.principal_id=NEW.principal_id AND w.operation='create_task'
    JOIN business.business_tasks t ON t.id=w.task_id
    WHERE i.id=NEW.confirmed_inbox_id AND i.organization_id=NEW.organization_id
    AND i.shop_id=NEW.shop_id AND i.source='feishu_business' AND i.app_id=NEW.app_id
    AND i.tenant_key=NEW.tenant_key AND r.identity_id=NEW.identity_id
    AND i.task_id=NEW.task_id AND w.task_id=NEW.task_id
    AND t.requester_id=NEW.principal_id AND t.workflow_version=NEW.workflow_version
    AND r.result->>'clarification_id'=NEW.id::text
    AND (r.result->>'round')::bigint=NEW.round
    AND r.result->>'candidate_hash'=NEW.candidate_hash)
    THEN RAISE EXCEPTION 'F02 consumption requires original T1 and confirmation receipt'
    USING ERRCODE='23514'; END IF; END IF; RETURN NEW; END $$""")
    op.execute("""CREATE TRIGGER p4_immutable_clarification_request BEFORE UPDATE OR DELETE
    ON business.p4_clarification_requests FOR EACH ROW
    EXECUTE FUNCTION business.p4_immutable_clarification_request()""")
    op.execute("""CREATE TRIGGER p4_no_truncate BEFORE TRUNCATE
    ON business.p4_clarification_requests FOR EACH STATEMENT
    EXECUTE FUNCTION business.reject_inventory_mutation()""")
    op.execute("""ALTER TABLE business.p4_clarification_replies
    ADD COLUMN request_id uuid REFERENCES business.p4_clarification_requests(id),
    ADD COLUMN round bigint,ADD COLUMN kind text,ADD COLUMN frozen_payload jsonb,
    ADD COLUMN frozen_payload_hash text""")
    op.execute("""DO $$ DECLARE constraint_name text; BEGIN
    SELECT conname INTO STRICT constraint_name FROM pg_constraint
    WHERE conrelid='business.p4_clarification_replies'::regclass AND contype='c'
    AND pg_get_constraintdef(oid) LIKE '%template_version%';
    EXECUTE format('ALTER TABLE business.p4_clarification_replies DROP CONSTRAINT %I',
        constraint_name);
    END $$""")
    op.execute("""ALTER TABLE business.p4_clarification_replies
    ADD CONSTRAINT p4_clarification_template
    CHECK((template_version='p4-clarification-v1' AND request_id IS NULL AND round IS NULL
    AND kind IS NULL AND frozen_payload IS NULL AND frozen_payload_hash IS NULL)
    OR (template_version='p4-f02-reply-v1' AND request_id IS NOT NULL
    AND round IS NOT NULL AND round>0
    AND kind IS NOT NULL AND kind IN ('question','ready','created') AND frozen_payload IS NOT NULL
    AND frozen_payload_hash IS NOT NULL AND jsonb_typeof(frozen_payload)='object'
    AND frozen_payload_hash ~ '^[a-f0-9]{64}$'
    AND frozen_payload->>'request_id'=request_id::text
    AND (frozen_payload->>'round')::bigint=round AND frozen_payload->>'kind'=kind))""")
    op.execute("""CREATE OR REPLACE FUNCTION business.p4_immutable_clarification() RETURNS trigger
    LANGUAGE plpgsql AS $$ BEGIN
    IF TG_OP='DELETE' OR (NEW.id,NEW.inbox_id,NEW.organization_id,NEW.shop_id,NEW.principal_id,
    NEW.identity_id,NEW.chat_id,NEW.chat_type,NEW.reason_code,NEW.template_version,
    NEW.provider_uuid,NEW.created_at,NEW.request_id,NEW.round,NEW.kind,NEW.frozen_payload,
    NEW.frozen_payload_hash) IS DISTINCT FROM
    (OLD.id,OLD.inbox_id,OLD.organization_id,OLD.shop_id,OLD.principal_id,OLD.identity_id,
    OLD.chat_id,OLD.chat_type,OLD.reason_code,OLD.template_version,OLD.provider_uuid,OLD.created_at,
    OLD.request_id,OLD.round,OLD.kind,OLD.frozen_payload,OLD.frozen_payload_hash)
    OR (OLD.status IN ('sent','unknown','dead') AND NEW IS DISTINCT FROM OLD)
    OR (OLD.status='sending' AND NEW.status NOT IN ('sending','sent','unknown','dead'))
    OR (OLD.first_attempt_at IS NOT NULL
    AND NEW.first_attempt_at IS DISTINCT FROM OLD.first_attempt_at)
    OR (OLD.claimed_by IS NOT NULL AND NEW.claimed_by IS DISTINCT FROM OLD.claimed_by)
    OR NEW.attempts<OLD.attempts THEN
    RAISE EXCEPTION 'clarification identity or original send receipt is immutable'
    USING ERRCODE='23514'; END IF; RETURN NEW; END $$""")


def downgrade() -> None:
    raise RuntimeError("F02 request, turn and confirmation history cannot be removed destructively")
