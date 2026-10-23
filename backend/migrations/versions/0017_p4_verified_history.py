"""原两条查询的独立历史来源、跨来源唯一键与一次取回账本。"""

from alembic import op

revision = "0017_p4_verified_history"
down_revision = "0016_p4_clarification_requests"
branch_labels = None
depends_on = None

CURRENT_READ_REPLY = """
CREATE OR REPLACE FUNCTION business.p4_read_reply_current(reply uuid) RETURNS
        boolean
    LANGUAGE plpgsql AS $$ DECLARE r business.p4_read_replies; t
        business.business_tasks;
      i business.identities; p business.principals; s
        business.p3_task_sources;
      e business.inbox_events; v business.p4_inbox_receipts; a
        business.analysis_reports;
      o business.p3_observations; allowed boolean;
    BEGIN
      SELECT * INTO r FROM business.p4_read_replies WHERE id=reply FOR SHARE;
      IF r.id IS NULL THEN RETURN false; END IF;
      SELECT * INTO t FROM business.business_tasks WHERE id=r.task_id FOR
        SHARE;
      SELECT * INTO i FROM business.identities WHERE id=r.identity_id FOR
        SHARE;
      SELECT * INTO p FROM business.principals WHERE id=r.principal_id FOR
        SHARE;
      SELECT * INTO e FROM business.inbox_events WHERE id=r.inbox_id;
      SELECT * INTO v FROM business.p4_inbox_receipts WHERE
        inbox_id=r.inbox_id;
      IF t.id IS NULL OR i.id IS NULL OR p.id IS NULL OR NOT
        business.p4_read_reply_origin_current(r)
        OR NOT p.enabled OR i.provider<>'feishu'
        OR (t.organization_id,t.shop_id,t.version,t.state) IS DISTINCT FROM
           (r.organization_id,r.shop_id,r.task_version,r.task_state)
        OR (i.organization_id,i.principal_id,i.app_id,i.tenant_key,
        i.external_subject,
        p.auth_version)
          IS DISTINCT FROM (r.organization_id,r.principal_id,r.app_id,
        r.tenant_key,r.open_id,
          r.auth_version)
 THEN RETURN
        false; END IF;
      allowed=false;
      IF t.requester_id=r.principal_id THEN
        allowed=business.lock_p3_permission(r.principal_id,r.organization_id,
        r.shop_id,
          r.identity_id,r.auth_version,'operator');
      END IF;
      IF NOT allowed AND EXISTS(SELECT 1 FROM business.approvals x WHERE
        x.task_id=t.id
        AND x.organization_id=r.organization_id AND x.shop_id=r.shop_id
        AND r.principal_id=ANY(x.eligible_principal_ids)) THEN
        allowed=business.lock_p3_permission(r.principal_id,r.organization_id,
        r.shop_id,
          r.identity_id,r.auth_version,'approver');
      END IF;
      IF NOT allowed OR NOT EXISTS(SELECT 1 FROM business.conversations c
        WHERE c.id=t.conversation_id AND c.organization_id=r.organization_id
        AND c.channel='feishu' AND c.chat_id=r.chat_id
        UNION ALL SELECT 1 FROM business.p4_card_bindings b JOIN
        business.outbox x ON
        x.id=b.outbox_id
        WHERE x.task_id=t.id AND x.organization_id=r.organization_id AND
        x.shop_id=r.shop_id
        AND b.source_mode='feishu' AND b.chat_id=r.chat_id) THEN RETURN false;
        END IF;
      IF r.source_kind IS NULL THEN
        RETURN r.kind='task_status' AND NOT EXISTS(SELECT 1 FROM
        business.analysis_reports a
          WHERE a.task_id=COALESCE((SELECT source_task_id FROM
        business.p3_task_sources
        WHERE
          task_id=t.id),t.id));
      END IF;
      IF t.kind='inventory_replenishment' THEN
        SELECT * INTO s FROM business.p3_task_sources WHERE task_id=t.id;
        IF s.task_id IS NULL OR s.source_task_id<>r.source_task_id THEN RETURN
        false; END
        IF;
      ELSIF t.kind<>'inventory_analysis_only' OR r.source_task_id<>t.id THEN
        RETURN false;
        END IF;
      IF r.source_kind='p2_original' THEN
        SELECT * INTO a FROM business.analysis_reports WHERE id=r.report_id;
        IF a.id IS NULL OR (a.organization_id,a.shop_id,a.task_id,
        a.snapshot_id,
        a.facts_hash)
          IS DISTINCT FROM (r.organization_id,r.shop_id,r.source_task_id,
        r.snapshot_id,
        r.facts_hash)
          OR (s.task_id IS NOT NULL AND (s.source_report_id,s.snapshot_id,
        s.facts_hash)
            IS DISTINCT FROM (r.report_id,r.snapshot_id,r.facts_hash)) THEN
        RETURN false;
        END IF;
      ELSE
        SELECT * INTO o FROM business.p3_observations WHERE
        id=r.observation_id;
        IF o.id IS NULL OR (o.organization_id,o.shop_id,o.task_id,
        o.source_task_id,
        o.report_id,o.facts_hash)
          IS DISTINCT FROM (r.organization_id,r.shop_id,r.task_id,
        r.source_task_id,
          r.report_id,r.facts_hash)
          OR (o.original_report_id,o.original_snapshot_id,
        o.original_facts_hash)
            IS DISTINCT FROM (s.source_report_id,s.snapshot_id,s.facts_hash)
        THEN RETURN
            false; END IF;
      END IF;
      IF r.kind='explain_report' THEN
        IF r.payload->>'read_code'='NOT_READY' THEN
          RETURN NOT EXISTS(SELECT 1 FROM business.p3_template_results z WHERE
            z.p3_task_id=r.task_id AND z.report_id=r.report_id AND
        z.status='ready')
          AND NOT EXISTS(SELECT 1 FROM business.model_explanations z WHERE
            z.parent_task_id=r.source_task_id AND z.report_id=r.report_id);
        END IF;
        IF r.payload#>>'{explanation,schema_version}'='p4-p3-template-read-v1'
        THEN
          RETURN EXISTS(SELECT 1 FROM business.p3_template_results z WHERE
          z.id=(r.payload#>>'{explanation,explanation_id}')::uuid
            AND z.organization_id=r.organization_id AND z.shop_id=r.shop_id
        AND
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
    END $$"""


def upgrade() -> None:
    op.execute("""
CREATE TABLE business.p4_history_recoveries (
      id uuid PRIMARY KEY,organization_id uuid NOT NULL,shop_id uuid NOT NULL,
      app_id text NOT NULL,tenant_key text NOT NULL,chat_id text NOT NULL,
      request jsonb NOT NULL,canonical_request text NOT NULL,request_hash text
        NOT NULL,
      status text NOT NULL DEFAULT 'collecting' CHECK(status IN ('collecting',
        'verified',
        'hold')),
      pages jsonb NOT NULL DEFAULT '[]' CHECK(jsonb_typeof(pages)='array' AND
        jsonb_array_length(pages)<=2),
      registered_at timestamptz NOT NULL DEFAULT clock_timestamp(),
        completed_at timestamptz,
      error_code text,
      UNIQUE(app_id,tenant_key,chat_id),
      FOREIGN KEY(organization_id,shop_id) REFERENCES
        business.shops(organization_id,id),
      CHECK(request=canonical_request::jsonb AND
        request_hash=encode(sha256(convert_to(canonical_request,'UTF8')),
        'hex')),
      CHECK(COALESCE(request->>'schema_version'='p4-original-query-history-v1'
        AND request->'enabled'='true'::jsonb AND
        request->>'recovery_id'=id::text
        AND request->>'organization_id'=organization_id::text AND
        request->>'shop_id'=shop_id::text
        AND request->>'app_id'=app_id AND request->>'tenant_key'=tenant_key
        AND
        request->>'chat_id'=chat_id
        AND jsonb_array_length(request->'expected_texts')=2
        AND (request->>'not_before')::timestamptz<=registered_at
        AND registered_at<(request->>'expires_at')::timestamptz
        AND (request->>'expires_at')::timestamptz>(request->>'not_before')::timestamptz
        AND (request->>'expires_at')::timestamptz<=
        (request->>'not_before')::timestamptz+interval '120 seconds',false)),
      CHECK((status='collecting')=(completed_at IS NULL)))""")
    op.execute("""
CREATE TABLE business.p4_history_messages (
      id uuid PRIMARY KEY,recovery_id uuid NOT NULL REFERENCES
        business.p4_history_recoveries(id),
      app_id text NOT NULL,tenant_key text NOT NULL,message_id text NOT NULL,
      text text NOT NULL,text_hash text NOT NULL,semantic_hash text NOT NULL,
        canonical_semantic text NOT NULL,
      kind text NOT NULL CHECK(kind IN ('task_status','explain_report')),
      task_id uuid NOT NULL REFERENCES business.business_tasks(id),report_id
        uuid,
      sent_at timestamptz NOT NULL,observed_at timestamptz NOT NULL,
        processed_at timestamptz
        NOT NULL DEFAULT clock_timestamp(),
      page_sha256 text NOT NULL,wire_row jsonb NOT NULL,receipt jsonb NOT NULL,

      reply_id uuid NOT NULL REFERENCES business.p4_read_replies(id)
        DEFERRABLE INITIALLY DEFERRED,
      existing_inbox_id uuid REFERENCES business.p4_inbox_receipts(inbox_id),
      UNIQUE(app_id,tenant_key,message_id),UNIQUE(recovery_id,kind),
      CHECK(text_hash=encode(sha256(convert_to(text,'UTF8')),'hex')),
      CHECK(semantic_hash=encode(sha256(convert_to(canonical_semantic,'UTF8')),
        'hex')),
      CHECK((kind='explain_report')=(report_id IS NOT NULL)),
      CHECK(sent_at BETWEEN '2026-10-17 13:01:45+00'::timestamptz AND
        '2026-10-17 13:05:45+00'::timestamptz),
      CHECK(sent_at<=observed_at AND observed_at<=processed_at),
      CHECK(COALESCE(wire_row->>'message_id'=message_id AND
        wire_row->>'msg_type'='text'
        AND wire_row->'deleted'='false'::jsonb AND
        wire_row->'updated'='false'::jsonb
        AND wire_row->>'create_time'=wire_row->>'update_time'
        AND wire_row->>'create_time' ~ '^[1-9][0-9]{12}$'
        AND to_timestamp((wire_row->>'create_time')::numeric/1000)=sent_at
        AND ((wire_row#>>'{body,content}')::jsonb)->>'text'=text,false)),
      CHECK(COALESCE(receipt->>'reply_id'=reply_id::text AND
        receipt->>'read_intent'=kind
        AND receipt->>'referenced_task_id'=task_id::text
        AND receipt->>'referenced_report_id' IS NOT DISTINCT FROM
        report_id::text,false)))""")
    op.execute("""
ALTER TABLE business.p4_read_replies ALTER COLUMN inbox_id DROP NOT NULL;
      ALTER TABLE business.p4_read_replies ADD COLUMN history_message_id uuid
        UNIQUE
        REFERENCES business.p4_history_messages(id);
      ALTER TABLE business.p4_read_replies ADD CONSTRAINT
        p4_read_reply_one_origin
        CHECK((inbox_id IS NULL)<>(history_message_id IS NULL))""")
    op.execute("""
CREATE TABLE business.p4_read_message_sources (
      app_id text NOT NULL,tenant_key text NOT NULL,message_id text NOT NULL,
      inbox_id uuid UNIQUE REFERENCES business.p4_inbox_receipts(inbox_id),
      history_message_id uuid UNIQUE REFERENCES
        business.p4_history_messages(id),
      PRIMARY KEY(app_id,tenant_key,message_id),
      CHECK((inbox_id IS NULL)<>(history_message_id IS NULL)))""")
    op.execute("""
INSERT INTO business.p4_read_message_sources(app_id,tenant_key,message_id,
        inbox_id)
      SELECT e.app_id,e.tenant_key,e.message_id,r.inbox_id FROM
        business.p4_read_replies r
      JOIN business.inbox_events e ON e.id=r.inbox_id WHERE e.message_id IS
        NOT NULL""")
    op.execute("""
CREATE FUNCTION business.p4_history_collection_current(recovery uuid) RETURNS
        boolean
    LANGUAGE plpgsql AS $$ DECLARE b business.p4_history_recoveries; i
        business.identities;
        p business.principals;
    BEGIN
      SELECT * INTO b FROM business.p4_history_recoveries WHERE id=recovery
        FOR SHARE;
      IF b.id IS NULL OR b.status<>'collecting' OR
        clock_timestamp()>=(b.request->>'expires_at')::timestamptz THEN RETURN
        false; END
        IF;
      SELECT * INTO i FROM business.identities WHERE
        id=(b.request->>'identity_id')::uuid
        FOR SHARE;
      SELECT * INTO p FROM business.principals WHERE
        id=(b.request->>'principal_id')::uuid
        FOR SHARE;
      IF i.id IS NULL OR p.id IS NULL OR NOT p.enabled OR i.provider<>'feishu'
        OR (i.organization_id,i.principal_id,i.app_id,i.tenant_key,
        i.external_subject,
        p.auth_version)
        IS DISTINCT FROM (b.organization_id,p.id,b.app_id,b.tenant_key,
        b.request->>'open_id',
        (b.request->>'auth_version')::bigint)
        THEN RETURN false; END IF;
      RETURN business.lock_p3_permission(p.id,b.organization_id,b.shop_id,i.id,

        p.auth_version,'operator');
    END $$""")
    op.execute("""
CREATE FUNCTION business.p4_bind_history_batch() RETURNS trigger LANGUAGE
        plpgsql AS $$
    BEGIN
      IF TG_OP='UPDATE' THEN
        IF OLD.status<>'collecting' OR to_jsonb(NEW)-ARRAY['status','pages',
        'completed_at',
        'error_code']
          IS DISTINCT FROM to_jsonb(OLD)-ARRAY['status','pages','completed_at',
        'error_code']
          OR jsonb_array_length(NEW.pages)<jsonb_array_length(OLD.pages)
          OR EXISTS(SELECT 1 FROM jsonb_array_elements(OLD.pages) WITH
        ORDINALITY x(v,n)
                    WHERE NEW.pages->((x.n-1)::int) IS DISTINCT FROM x.v) THEN
          RAISE EXCEPTION 'P4 history once immutable' USING ERRCODE='23514';
        END IF;
        IF NEW.status='verified' AND (
          NOT business.p4_history_collection_current(OLD.id)
          OR jsonb_array_length(NEW.pages) NOT BETWEEN 1 AND 2
          OR (SELECT count(*) FROM business.p4_history_messages WHERE
        recovery_id=NEW.id)<>2
          OR (SELECT count(*) FROM business.p4_sdk_calls WHERE
        window_id=NEW.id AND
        method='auth.v3.tenant_access_token.internal' AND status='returned'
        AND http_status
        BETWEEN 200 AND 299 AND provider_code=0)<>1
          OR (SELECT count(*) FROM business.p4_sdk_calls WHERE
        window_id=NEW.id AND
        method='bot.v3.info' AND status='returned' AND http_status BETWEEN 200
        AND 299 AND
        provider_code=0)<>1
          OR (SELECT count(*) FROM business.p4_sdk_calls WHERE
        window_id=NEW.id AND
        method='im.v1.message.list' AND status='returned' AND http_status
        BETWEEN 200 AND
        299 AND provider_code=0)<>jsonb_array_length(NEW.pages)
          OR (SELECT count(*) FROM business.p4_sdk_calls WHERE
        window_id=NEW.id)<>2+jsonb_array_length(NEW.pages)) THEN
          RAISE EXCEPTION 'P4 complete history observation required' USING
        ERRCODE='23514';
        END IF;
      END IF;
      RETURN NEW;
    END $$""")
    op.execute("""
CREATE TRIGGER p4_history_batch_binding BEFORE UPDATE ON
        business.p4_history_recoveries
      FOR EACH ROW EXECUTE FUNCTION business.p4_bind_history_batch()""")
    op.execute("""
CREATE FUNCTION business.p4_bind_history_message() RETURNS trigger LANGUAGE
        plpgsql AS $$
    DECLARE b business.p4_history_recoveries;
    BEGIN
      SELECT * INTO b FROM business.p4_history_recoveries WHERE
        id=NEW.recovery_id FOR
        SHARE;
      IF b.id IS NULL OR b.status<>'collecting' OR (NEW.app_id,NEW.tenant_key)
        IS DISTINCT
        FROM (b.app_id,b.tenant_key)
        OR NEW.wire_row->>'chat_id' IS DISTINCT FROM b.chat_id
        OR NEW.wire_row#>>'{sender,id}' IS DISTINCT FROM b.request->>'open_id'
        OR NEW.wire_row#>>'{sender,id_type}' IS DISTINCT FROM 'open_id'
        OR NEW.wire_row#>>'{sender,sender_type}' IS DISTINCT FROM 'user'
        OR NEW.wire_row#>>'{sender,tenant_key}' IS DISTINCT FROM b.tenant_key
        OR NEW.text IS DISTINCT FROM b.request->'expected_texts'->>(CASE
        NEW.kind WHEN
        'task_status' THEN 0 ELSE 1 END)
        OR NEW.observed_at<(b.request->>'not_before')::timestamptz OR
        NEW.observed_at>=(b.request->>'expires_at')::timestamptz
        OR NOT EXISTS(SELECT 1 FROM jsonb_array_elements(b.pages) p WHERE
        p->>'raw_sha256'=NEW.page_sha256)
        OR NEW.canonical_semantic::jsonb IS DISTINCT FROM
        jsonb_build_object('chat',
        b.chat_id,'open_id',b.request->>'open_id','text',NEW.text)
        OR (NEW.kind='task_status' AND NEW.text !~
        ('^查询任务[ '||chr(9)||']*'||NEW.task_id::text||'[ '||chr(9)||']*进度$'))
        OR (NEW.kind='explain_report' AND NEW.text !~
        ('^解释任务[ '||chr(9)||']*'||NEW.task_id::text||
        '[ '||chr(9)||']*的报告[ '||chr(9)||']*'||NEW.report_id::text||'$'))
        THEN
        RAISE EXCEPTION 'P4 original history source required' USING
        ERRCODE='23514';
      END IF;
      RETURN NEW;
    END $$""")
    op.execute("""
CREATE TRIGGER p4_history_message_binding BEFORE INSERT ON
        business.p4_history_messages
      FOR EACH ROW EXECUTE FUNCTION business.p4_bind_history_message()""")
    op.execute("""
CREATE FUNCTION business.p4_bind_read_message_source() RETURNS trigger
        LANGUAGE plpgsql AS
        $$
    DECLARE e business.inbox_events;
    BEGIN
      IF TG_TABLE_NAME='p4_read_replies' THEN
        IF NEW.inbox_id IS NOT NULL THEN
          SELECT * INTO e FROM business.inbox_events WHERE id=NEW.inbox_id;
          IF e.message_id IS NOT NULL THEN
            INSERT INTO business.p4_read_message_sources VALUES(e.app_id,
        e.tenant_key,
        e.message_id,e.id,NULL);
          END IF;
        END IF;
      ELSIF NEW.existing_inbox_id IS NULL THEN
        INSERT INTO business.p4_read_message_sources VALUES(NEW.app_id,
        NEW.tenant_key,
        NEW.message_id,NULL,NEW.id);
      ELSIF NOT EXISTS(SELECT 1 FROM business.p4_read_message_sources k WHERE
        (k.app_id,k.tenant_key,k.message_id,k.inbox_id)=(NEW.app_id,
        NEW.tenant_key,
        NEW.message_id,NEW.existing_inbox_id)) THEN
        RAISE EXCEPTION 'P4 existing live read message required' USING
        ERRCODE='23514';
      END IF;
      RETURN NEW;
    END $$""")
    op.execute("""
CREATE TRIGGER p4_read_reply_00_message_source AFTER INSERT ON
        business.p4_read_replies
      FOR EACH ROW EXECUTE FUNCTION business.p4_bind_read_message_source();
      CREATE TRIGGER p4_history_message_source AFTER INSERT ON
        business.p4_history_messages
      FOR EACH ROW EXECUTE FUNCTION business.p4_bind_read_message_source()""")
    op.execute("""
CREATE FUNCTION business.p4_read_reply_origin_current(r
        business.p4_read_replies) RETURNS
        boolean
    LANGUAGE plpgsql AS $$ DECLARE e business.inbox_events; v
        business.p4_inbox_receipts;
      m business.p4_history_messages; b business.p4_history_recoveries;
    BEGIN
      IF r.inbox_id IS NOT NULL THEN
        SELECT * INTO e FROM business.inbox_events WHERE id=r.inbox_id;
        SELECT * INTO v FROM business.p4_inbox_receipts WHERE
        inbox_id=r.inbox_id;
        RETURN COALESCE(e.id IS NOT NULL AND v.inbox_id IS NOT NULL
          AND (e.organization_id,e.shop_id,e.app_id,e.tenant_key,
        v.identity_id)=(r.organization_id,r.shop_id,r.app_id,r.tenant_key,
        r.identity_id)
          AND e.sanitized_payload->>'event_type'='p4.explicit_read'
          AND e.sanitized_payload->>'principal_id'=r.principal_id::text
          AND e.sanitized_payload->>'chat_id'=r.chat_id AND
        e.sanitized_payload->>'chat_type'=r.chat_type
          AND v.result->>'reply_id'=r.id::text AND
        v.result->>'reply_payload_hash'=r.payload_hash
          AND v.result->>'as_of'=r.payload->>'as_of' AND
        v.result->>'read_intent'=r.kind
          AND v.result->>'referenced_task_id'=r.task_id::text,false);
      END IF;
      SELECT * INTO m FROM business.p4_history_messages WHERE
        id=r.history_message_id;
      SELECT * INTO b FROM business.p4_history_recoveries WHERE
        id=m.recovery_id;
      RETURN COALESCE(m.id IS NOT NULL AND b.status='verified' AND
        r.chat_type='p2p'
        AND m.existing_inbox_id IS NULL AND m.reply_id=r.id
        AND (b.organization_id,b.shop_id,b.app_id,b.tenant_key,
        b.chat_id)=(r.organization_id,
        r.shop_id,r.app_id,r.tenant_key,r.chat_id)
        AND (b.request->>'principal_id',b.request->>'identity_id',
        b.request->>'open_id',
        (b.request->>'auth_version')::bigint)=(r.principal_id::text,
        r.identity_id::text,
        r.open_id,r.auth_version)
        AND (m.kind,m.task_id)=(r.kind,r.task_id)
        AND m.receipt->>'reply_payload_hash'=r.payload_hash AND
        m.receipt->>'as_of'=r.payload->>'as_of'
        AND EXISTS(SELECT 1 FROM business.p4_read_message_sources k WHERE
          (k.app_id,k.tenant_key,k.message_id,k.history_message_id)=(m.app_id,
        m.tenant_key,
        m.message_id,m.id)),false);
    END $$""")
    op.execute(CURRENT_READ_REPLY)
    op.execute("""
ALTER TABLE business.p4_sdk_calls DROP CONSTRAINT p4_sdk_calls_method_check;
      ALTER TABLE business.p4_sdk_calls ADD CONSTRAINT
        p4_sdk_calls_method_check
        CHECK(method IN
      ('auth.v3.tenant_access_token.internal','bot.v3.info',
        'im.v1.message.create',
        'im.v1.message.list',
       'bitable.v1.app_table_record.create','bitable.v1.app_table_record.list',

        'bitable.v1.app_table_record.update',
       'bitable.v1.app_table.list','bitable.v1.app_table_field.list'));
      ALTER TABLE business.p4_sdk_calls DROP CONSTRAINT
        p4_sdk_calls_scope_kind_check;
      ALTER TABLE business.p4_sdk_calls ADD CONSTRAINT
        p4_sdk_calls_scope_kind_check
        CHECK(scope_kind IN
      ('preflight','base_projection','approval_card','task_result',
        'clarification',
        'read_reply','history_read'));
      ALTER TABLE business.p4_sdk_calls DROP CONSTRAINT p4_sdk_calls_check1;
      ALTER TABLE business.p4_sdk_calls ADD CONSTRAINT
        p4_sdk_calls_task_binding
        CHECK((scope_kind IN ('preflight','clarification',
        'history_read'))=(task_id IS
        NULL))""")
    op.execute("""
CREATE FUNCTION business.p4_bind_history_sdk_call() RETURNS trigger LANGUAGE
        plpgsql AS $$
    DECLARE w business.p4_sdk_windows;
    BEGIN
      SELECT * INTO w FROM business.p4_sdk_windows WHERE id=NEW.window_id;
      IF NEW.scope_kind='history_read' OR NEW.method='im.v1.message.list' OR
        w.method_caps ?
        'im.v1.message.list' THEN
        IF w.method_caps<>jsonb_build_object('auth.v3.tenant_access_token.internal',1,
          'bot.v3.info',1,'im.v1.message.list',2)
          OR NOT w.configured_enabled OR w.expires_at<=clock_timestamp()
          OR NOT business.p4_history_collection_current(w.id)
          OR NEW.subject_id<>w.id OR NEW.task_id IS NOT NULL
          OR NOT ((NEW.scope_kind='history_read' AND
        NEW.method='im.v1.message.list')
            OR (NEW.scope_kind='preflight' AND NEW.method IN
        ('auth.v3.tenant_access_token.internal','bot.v3.info')))
          OR NOT EXISTS(SELECT 1 FROM business.p4_history_recoveries b WHERE
        b.id=w.id
            AND (b.organization_id,b.shop_id,
        (b.request->>'expires_at')::timestamptz)=(w.organization_id,w.shop_id,
        w.expires_at))
        THEN
          RAISE EXCEPTION 'P4 history SDK narrow once binding required' USING
        ERRCODE='23514'; END IF;
      END IF;
      RETURN NEW;
    END $$""")
    op.execute("""
CREATE TRIGGER p4_history_sdk_binding BEFORE INSERT ON business.p4_sdk_calls
      FOR EACH ROW EXECUTE FUNCTION business.p4_bind_history_sdk_call()""")
    for table in ("p4_history_messages", "p4_read_message_sources"):
        op.execute(f"""CREATE TRIGGER p4_history_immutable BEFORE UPDATE OR DELETE
          ON business.{table}
          FOR EACH ROW EXECUTE FUNCTION business.reject_inventory_mutation()""")
    op.execute("""
CREATE TRIGGER p4_history_no_delete BEFORE DELETE ON
        business.p4_history_recoveries
      FOR EACH ROW EXECUTE FUNCTION business.reject_inventory_mutation()""")
    for table in ("p4_history_recoveries", "p4_history_messages", "p4_read_message_sources"):
        op.execute(f"""CREATE TRIGGER p4_history_no_truncate BEFORE TRUNCATE ON business.{table}
          FOR EACH STATEMENT EXECUTE FUNCTION business.reject_inventory_mutation()""")


def downgrade() -> None:
    raise RuntimeError("Verified original history and consumed attempts cannot be removed")
