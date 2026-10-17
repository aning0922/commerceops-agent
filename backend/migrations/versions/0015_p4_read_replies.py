"""两种显式读取的专用 immutable carrier；原 IM/outbox/历史 migration 不改。"""

from alembic import op

revision = "0015_p4_read_replies"
down_revision = "0014_p3_template_results"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE business.p4_read_replies (
    id uuid PRIMARY KEY,inbox_id uuid NOT NULL UNIQUE REFERENCES
    business.p4_inbox_receipts(inbox_id),
    organization_id uuid NOT NULL,shop_id uuid NOT NULL,principal_id uuid NOT NULL,
    identity_id uuid NOT NULL REFERENCES business.identities(id),auth_version bigint NOT NULL
    CHECK(auth_version>0),
    app_id text NOT NULL,tenant_key text NOT NULL,open_id text NOT NULL,chat_id text NOT NULL,
    chat_type text NOT NULL CHECK(chat_type IN ('p2p','group')),
    kind text NOT NULL CHECK(kind IN ('task_status','explain_report')),
    task_id uuid NOT NULL,task_version bigint NOT NULL CHECK(task_version>0),task_state text
    NOT NULL,
    source_kind text,source_task_id uuid,observation_id uuid,report_id uuid,snapshot_id uuid,
    facts_hash text,
    as_of timestamptz NOT NULL,payload jsonb NOT NULL,canonical_payload text NOT NULL,
    payload_hash text NOT NULL,provider_uuid uuid NOT NULL UNIQUE,
    status text NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','sending','sent',
    'unknown','dead')),
    attempts integer NOT NULL DEFAULT 0 CHECK(attempts BETWEEN 0 AND 1),
    claimed_by text,first_attempt_at timestamptz,message_id text,last_error text,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CHECK(source_kind IS NULL OR source_kind IN ('p2_original','p3_observation')),
    CHECK((source_kind IS NULL AND source_task_id IS NULL AND observation_id IS NULL
        AND report_id IS NULL AND snapshot_id IS NULL AND facts_hash IS NULL)
       OR (source_kind IS NOT NULL AND source_task_id IS NOT NULL AND report_id IS NOT NULL
        AND snapshot_id IS NOT NULL AND facts_hash ~ '^[a-f0-9]{64}$'
        AND ((source_kind='p3_observation')=(observation_id IS NOT NULL))
        AND (observation_id IS NULL OR snapshot_id=observation_id))),
    CHECK(kind<>'explain_report' OR source_kind IS NOT NULL),
    CHECK(canonical_payload::jsonb=payload
      AND payload_hash=encode(sha256(convert_to(canonical_payload,'UTF8')),'hex')),
    CHECK((status='sent')=(message_id IS NOT NULL)),
    CHECK(status NOT IN ('sending','sent','unknown') OR attempts=1),
    CHECK((attempts=1)=(claimed_by IS NOT NULL AND first_attempt_at IS NOT NULL)),
    FOREIGN KEY(organization_id,principal_id) REFERENCES business.principals(organization_id,id),
    FOREIGN KEY(organization_id,shop_id,task_id) REFERENCES
    business.business_tasks(organization_id,shop_id,id),
    FOREIGN KEY(organization_id,shop_id,source_task_id) REFERENCES
    business.business_tasks(organization_id,shop_id,id),
    FOREIGN KEY(organization_id,shop_id,task_id,observation_id)
      REFERENCES business.p3_observations(organization_id,shop_id,task_id,id)
    )""")
    op.execute("""CREATE FUNCTION business.p4_read_reply_current(reply uuid) RETURNS boolean
    LANGUAGE plpgsql AS $$ DECLARE r business.p4_read_replies; t business.business_tasks;
      i business.identities; p business.principals; s business.p3_task_sources;
      e business.inbox_events; v business.p4_inbox_receipts; a business.analysis_reports;
      o business.p3_observations; allowed boolean;
    BEGIN
      SELECT * INTO r FROM business.p4_read_replies WHERE id=reply FOR SHARE;
      IF r.id IS NULL THEN RETURN false; END IF;
      SELECT * INTO t FROM business.business_tasks WHERE id=r.task_id FOR SHARE;
      SELECT * INTO i FROM business.identities WHERE id=r.identity_id FOR SHARE;
      SELECT * INTO p FROM business.principals WHERE id=r.principal_id FOR SHARE;
      SELECT * INTO e FROM business.inbox_events WHERE id=r.inbox_id;
      SELECT * INTO v FROM business.p4_inbox_receipts WHERE inbox_id=r.inbox_id;
      IF t.id IS NULL OR i.id IS NULL OR p.id IS NULL OR e.id IS NULL OR v.inbox_id IS NULL
        OR NOT p.enabled OR i.provider<>'feishu'
        OR (t.organization_id,t.shop_id,t.version,t.state) IS DISTINCT FROM
           (r.organization_id,r.shop_id,r.task_version,r.task_state)
        OR (i.organization_id,i.principal_id,i.app_id,i.tenant_key,i.external_subject,
        p.auth_version)
          IS DISTINCT FROM (r.organization_id,r.principal_id,r.app_id,r.tenant_key,r.open_id,
          r.auth_version)
        OR (e.organization_id,e.shop_id,e.app_id,e.tenant_key,v.identity_id) IS DISTINCT FROM
           (r.organization_id,r.shop_id,r.app_id,r.tenant_key,r.identity_id)
        OR e.sanitized_payload->>'event_type'<>'p4.explicit_read'
        OR e.sanitized_payload->>'principal_id' IS DISTINCT FROM r.principal_id::text
        OR e.sanitized_payload->>'chat_id' IS DISTINCT FROM r.chat_id
        OR e.sanitized_payload->>'chat_type' IS DISTINCT FROM r.chat_type
        OR v.result->>'reply_id' IS DISTINCT FROM r.id::text
        OR v.result->>'reply_payload_hash' IS DISTINCT FROM r.payload_hash
        OR v.result->>'as_of' IS DISTINCT FROM r.payload->>'as_of'
        OR v.result->>'read_intent' IS DISTINCT FROM r.kind
        OR v.result->>'referenced_task_id' IS DISTINCT FROM r.task_id::text THEN RETURN
        false; END IF;
      allowed=false;
      IF t.requester_id=r.principal_id THEN
        allowed=business.lock_p3_permission(r.principal_id,r.organization_id,r.shop_id,
          r.identity_id,r.auth_version,'operator');
      END IF;
      IF NOT allowed AND EXISTS(SELECT 1 FROM business.approvals x WHERE x.task_id=t.id
        AND x.organization_id=r.organization_id AND x.shop_id=r.shop_id
        AND r.principal_id=ANY(x.eligible_principal_ids)) THEN
        allowed=business.lock_p3_permission(r.principal_id,r.organization_id,r.shop_id,
          r.identity_id,r.auth_version,'approver');
      END IF;
      IF NOT allowed OR NOT EXISTS(SELECT 1 FROM business.conversations c
        WHERE c.id=t.conversation_id AND c.organization_id=r.organization_id
        AND c.channel='feishu' AND c.chat_id=r.chat_id
        UNION ALL SELECT 1 FROM business.p4_card_bindings b JOIN business.outbox x ON
        x.id=b.outbox_id
        WHERE x.task_id=t.id AND x.organization_id=r.organization_id AND x.shop_id=r.shop_id
        AND b.source_mode='feishu' AND b.chat_id=r.chat_id) THEN RETURN false; END IF;
      IF r.source_kind IS NULL THEN
        RETURN r.kind='task_status' AND NOT EXISTS(SELECT 1 FROM business.analysis_reports a
          WHERE a.task_id=COALESCE((SELECT source_task_id FROM business.p3_task_sources WHERE
          task_id=t.id),t.id));
      END IF;
      IF t.kind='inventory_replenishment' THEN
        SELECT * INTO s FROM business.p3_task_sources WHERE task_id=t.id;
        IF s.task_id IS NULL OR s.source_task_id<>r.source_task_id THEN RETURN false; END IF;
      ELSIF t.kind<>'inventory_analysis_only' OR r.source_task_id<>t.id THEN RETURN false; END IF;
      IF r.source_kind='p2_original' THEN
        SELECT * INTO a FROM business.analysis_reports WHERE id=r.report_id;
        IF a.id IS NULL OR (a.organization_id,a.shop_id,a.task_id,a.snapshot_id,a.facts_hash)
          IS DISTINCT FROM (r.organization_id,r.shop_id,r.source_task_id,r.snapshot_id,r.facts_hash)
          OR (s.task_id IS NOT NULL AND (s.source_report_id,s.snapshot_id,s.facts_hash)
            IS DISTINCT FROM (r.report_id,r.snapshot_id,r.facts_hash)) THEN RETURN false; END IF;
      ELSE
        SELECT * INTO o FROM business.p3_observations WHERE id=r.observation_id;
        IF o.id IS NULL OR (o.organization_id,o.shop_id,o.task_id,o.source_task_id,
        o.report_id,o.facts_hash)
          IS DISTINCT FROM (r.organization_id,r.shop_id,r.task_id,r.source_task_id,
          r.report_id,r.facts_hash)
          OR (o.original_report_id,o.original_snapshot_id,o.original_facts_hash)
            IS DISTINCT FROM (s.source_report_id,s.snapshot_id,s.facts_hash) THEN RETURN
            false; END IF;
      END IF;
      IF r.kind='explain_report' THEN
        IF r.payload->>'read_code'='NOT_READY' THEN
          RETURN NOT EXISTS(SELECT 1 FROM business.p3_template_results z WHERE
            z.p3_task_id=r.task_id AND z.report_id=r.report_id AND z.status='ready')
          AND NOT EXISTS(SELECT 1 FROM business.model_explanations z WHERE
            z.parent_task_id=r.source_task_id AND z.report_id=r.report_id);
        END IF;
        IF r.payload#>>'{explanation,schema_version}'='p4-p3-template-read-v1' THEN
          RETURN EXISTS(SELECT 1 FROM business.p3_template_results z WHERE
          z.id=(r.payload#>>'{explanation,explanation_id}')::uuid
            AND z.organization_id=r.organization_id AND z.shop_id=r.shop_id AND
            z.p3_task_id=r.task_id
            AND z.source_kind=r.source_kind AND z.report_id=r.report_id AND
            z.snapshot_id=r.snapshot_id
            AND z.facts_hash=r.facts_hash AND z.status='ready' AND
            z.result=r.payload#>'{explanation,result}');
        END IF;
        RETURN EXISTS(SELECT 1 FROM business.model_explanations z WHERE
        z.id=(r.payload#>>'{explanation,explanation_id}')::uuid
          AND z.organization_id=r.organization_id AND z.shop_id=r.shop_id AND
          z.parent_task_id=r.source_task_id
          AND z.report_id=r.report_id AND z.facts_hash=r.facts_hash AND
          z.result=r.payload#>'{explanation,result}');
      END IF;
      RETURN true;
    END $$""")
    op.execute("""CREATE FUNCTION business.p4_bind_read_reply() RETURNS trigger LANGUAGE
    plpgsql AS $$
    BEGIN
      IF NOT COALESCE(jsonb_typeof(NEW.payload)='object' AND
      NEW.payload->>'schema_version'='p4-read-reply-v1'
        AND NEW.payload->>'kind'=NEW.kind AND NEW.payload->>'task_id'=NEW.task_id::text
        AND (NEW.payload->>'task_version')::bigint=NEW.task_version AND
        NEW.payload->>'task_state'=NEW.task_state
        AND (NEW.payload->>'as_of')::timestamptz=NEW.as_of
        AND NEW.payload->>'read_code' IN ('OK','NOT_READY')
        AND ((NEW.kind='explain_report' AND NEW.payload->>'read_code'='OK')=
             (NEW.payload->'explanation'<>'null'::jsonb))
        AND (NEW.kind='explain_report' OR NEW.payload->>'read_code'='OK')
        AND ((NEW.source_kind IS NULL)=(NEW.payload->'source'='null'::jsonb)),false)
        OR (NEW.source_kind IS NOT NULL AND NOT COALESCE(
          NEW.payload#>>'{source,source_kind}'=NEW.source_kind
          AND NEW.payload#>>'{source,source_task_id}'=NEW.source_task_id::text
          AND NEW.payload#>>'{source,report_id}'=NEW.report_id::text
          AND NEW.payload#>>'{source,snapshot_id}'=NEW.snapshot_id::text
          AND NEW.payload#>>'{source,facts_hash}'=NEW.facts_hash
          AND NEW.payload#>>'{source,observation_id}' IS NOT DISTINCT FROM
          NEW.observation_id::text,false)) THEN
        RAISE EXCEPTION 'P4 typed read reply binding required' USING ERRCODE='23514'; END IF;
      IF TG_OP='UPDATE' AND (to_jsonb(NEW)-ARRAY['status','attempts','claimed_by',
      'first_attempt_at','message_id','last_error']
        IS DISTINCT FROM to_jsonb(OLD)-ARRAY['status','attempts','claimed_by',
        'first_attempt_at','message_id','last_error']
        OR (OLD.status IN ('sent','unknown','dead') AND NEW IS DISTINCT FROM OLD)
        OR (OLD.status='sending' AND NEW.status NOT IN ('sending','sent','unknown','dead'))
        OR NEW.attempts<OLD.attempts OR (OLD.claimed_by IS NOT NULL AND NEW.claimed_by IS
        DISTINCT FROM OLD.claimed_by)
        OR (OLD.first_attempt_at IS NOT NULL AND NEW.first_attempt_at IS DISTINCT FROM
        OLD.first_attempt_at)) THEN
        RAISE EXCEPTION 'P4 read reply identity/unknown immutable' USING ERRCODE='23514'; END IF;
      RETURN NEW;
    END $$""")
    op.execute("""CREATE TRIGGER p4_read_reply_binding BEFORE INSERT OR UPDATE ON
    business.p4_read_replies
      FOR EACH ROW EXECUTE FUNCTION business.p4_bind_read_reply()""")
    op.execute("""CREATE FUNCTION business.p4_check_read_reply_insert() RETURNS trigger
    LANGUAGE plpgsql AS $$ BEGIN IF NOT business.p4_read_reply_current(NEW.id) THEN
      RAISE EXCEPTION 'P4 original inbox/source/actor required' USING ERRCODE='23514';
    END IF; RETURN NEW; END $$""")
    op.execute("""CREATE TRIGGER p4_read_reply_source AFTER INSERT ON business.p4_read_replies
      FOR EACH ROW EXECUTE FUNCTION business.p4_check_read_reply_insert()""")
    op.execute("""CREATE TRIGGER p4_read_reply_no_delete BEFORE DELETE ON business.p4_read_replies
      FOR EACH ROW EXECUTE FUNCTION business.reject_inventory_mutation()""")
    op.execute("""CREATE TRIGGER p4_read_reply_no_truncate BEFORE TRUNCATE ON
    business.p4_read_replies
      FOR EACH STATEMENT EXECUTE FUNCTION business.reject_inventory_mutation()""")
    op.execute("ALTER TABLE business.p4_sdk_calls DROP CONSTRAINT p4_sdk_calls_scope_kind_check")
    op.execute("""ALTER TABLE business.p4_sdk_calls ADD CHECK(scope_kind IN
      ('preflight','base_projection','approval_card','task_result','clarification',
      'read_reply'))""")
    op.execute("""CREATE FUNCTION business.p4_bind_read_reply_sdk_call() RETURNS trigger
    LANGUAGE plpgsql AS $$
      DECLARE r business.p4_read_replies; w business.p4_sdk_windows;
      BEGIN IF NEW.scope_kind='read_reply' THEN
        SELECT * INTO r FROM business.p4_read_replies WHERE id=NEW.subject_id FOR UPDATE;
        SELECT * INTO w FROM business.p4_sdk_windows WHERE id=NEW.window_id;
        IF r.id IS NULL OR w.id IS NULL OR NOT w.configured_enabled
          OR w.expires_at<=clock_timestamp()
          OR w.method_caps<>'{"auth.v3.tenant_access_token.internal": 1,"bot.v3.info": 1,
            "im.v1.message.create": 1}'::jsonb
          OR NEW.task_id IS NULL OR NEW.method<>'im.v1.message.create'
          OR (r.task_id,r.organization_id,r.shop_id) IS DISTINCT FROM (NEW.task_id,
          w.organization_id,w.shop_id)
          OR r.status<>'sending' OR r.attempts<>1 OR NOT business.p4_read_reply_current(r.id) THEN
          RAISE EXCEPTION 'P4 SDK read reply subject binding required' USING ERRCODE='23514';
          END IF;
      END IF; RETURN NEW; END $$""")
    op.execute("""CREATE TRIGGER p4_read_reply_sdk_binding BEFORE INSERT ON business.p4_sdk_calls
      FOR EACH ROW EXECUTE FUNCTION business.p4_bind_read_reply_sdk_call()""")
    op.execute("""CREATE UNIQUE INDEX p4_read_reply_one_method_attempt
      ON business.p4_sdk_calls(subject_id) WHERE scope_kind='read_reply'""")


def downgrade() -> None:
    raise RuntimeError("P4 read reply unknown history cannot be removed destructively")
