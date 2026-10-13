"""显式持久 C0 claim 的一次原键 create；保留 0010 全部历史与未知规则。"""

from alembic import op

revision = "0013_p4_first_create"
down_revision = "0012_p4_preflight_methods"
branch_labels = None
depends_on = None

TRIGGER_SQL = """CREATE OR REPLACE FUNCTION business.p4_base_delivery_identity() RETURNS trigger
    LANGUAGE plpgsql AS $$ DECLARE first_create boolean := false; BEGIN
    IF TG_OP='DELETE' THEN RAISE EXCEPTION 'P4 original projection cannot be deleted'
    USING ERRCODE='23514'; END IF;
    IF TG_OP='INSERT' THEN
      IF NEW.status<>'pending' OR NEW.attempts<>0 OR NEW.unknown_since IS NOT NULL THEN
        RAISE EXCEPTION 'P4 original projection must begin pending' USING ERRCODE='23514';
      END IF;
      IF NOT EXISTS(SELECT 1 FROM business.outbox o JOIN business.replenishment_items i
      ON i.id=o.aggregate_id AND i.organization_id=o.organization_id AND i.shop_id=o.shop_id
      AND i.task_id=o.task_id WHERE o.id=NEW.outbox_id AND o.destination='bitable'
      AND o.operation='item_projection' AND o.source_mode='mock' AND NOT o.sender_enabled
      AND o.organization_id=NEW.organization_id AND o.shop_id=NEW.shop_id AND o.task_id=NEW.task_id
      AND o.aggregate_id=NEW.item_id AND o.aggregate_version=NEW.version
      AND o.provider_idempotency_key IS NOT DISTINCT FROM NEW.client_token
      AND NEW.projection->>'item_id'=NEW.item_id::text
      AND NEW.projection->>'task_id'=NEW.task_id::text
      AND (NEW.projection->>'sync_version')::integer=NEW.version) THEN
        RAISE EXCEPTION 'P4 original projection binding invalid' USING ERRCODE='23514';
      END IF;
    ELSE
      -- P4 explicit C0 persisted claim
      IF OLD.status='unknown' AND OLD.version=1 AND OLD.attempts=1
      AND OLD.last_operation='create' AND OLD.last_error='INCOMPLETE_READBACK'
      AND OLD.external_id IS NULL AND OLD.unknown_since IS NOT NULL
      AND OLD.first_attempt_at IS NOT NULL AND OLD.verification_mode='controlled_sdk'
      AND NEW.status='sending' AND NEW.last_operation='create' AND NEW.attempts=2
      AND NEW.claimed_by IS NOT NULL AND length(NEW.claimed_by)>0
      AND (NEW.outbox_id,NEW.organization_id,NEW.shop_id,NEW.task_id,NEW.item_id,NEW.target_key,
      NEW.client_token,NEW.version,NEW.verification_mode,NEW.projection,NEW.projection_hash,
      NEW.created_at,NEW.first_attempt_at,NEW.unknown_since,NEW.external_id)
      IS NOT DISTINCT FROM (OLD.outbox_id,OLD.organization_id,OLD.shop_id,OLD.task_id,OLD.item_id,
      OLD.target_key,OLD.client_token,OLD.version,OLD.verification_mode,OLD.projection,
      OLD.projection_hash,OLD.created_at,OLD.first_attempt_at,OLD.unknown_since,OLD.external_id)
      THEN
        SELECT count(*)=1 INTO first_create
        FROM business.audit_events c
        JOIN business.p4_sdk_windows w ON w.id=c.id
        JOIN business.audit_events g ON g.id::text=c.after_state->>'gateway_window_id'
        JOIN business.business_tasks t ON t.id=OLD.task_id
        JOIN business.outbox o ON o.id=OLD.outbox_id
        JOIN business.replenishment_items i ON i.id=OLD.item_id
        JOIN business.executions x ON x.id=i.execution_id AND x.task_id=t.id
        JOIN business.approvals a ON a.id=x.approval_id AND a.task_id=t.id
        JOIN business.organizations org ON org.id=OLD.organization_id
        JOIN business.p4_sender_state sender ON sender.organization_id=OLD.organization_id
        AND sender.shop_id=OLD.shop_id AND sender.destination_alias='Base'
        JOIN business.audit_events worker ON worker.organization_id=OLD.organization_id
        AND worker.source='worker' AND worker.entity_type='worker_runtime'
        AND worker.action='started' AND worker.entity_id=NEW.claimed_by
        WHERE c.organization_id=OLD.organization_id AND c.task_id=OLD.task_id
        AND c.source='feishu_recovery' AND c.action='approved_workflow_claimed'
        AND c.entity_type='sdk_window' AND c.entity_id=c.id::text AND c.trace_id=c.id
        AND c.after_state->>'schema_version'='p4-worker-v1'
        AND c.after_state->>'profile'='approved_first_create'
        AND c.after_state->'enabled'='true'::jsonb
        AND c.after_state->>'window_id'=c.id::text
        AND c.after_state->>'organization_id'=OLD.organization_id::text
        AND c.after_state->>'shop_id'=OLD.shop_id::text
        AND c.after_state->'task_ids'=jsonb_build_array(OLD.task_id::text)
        AND c.after_state->'first_create'=jsonb_build_object(
          'outbox_id',OLD.outbox_id::text,'item_id',OLD.item_id::text,
          'client_token',OLD.client_token::text,'version',1,
          'projection_hash',OLD.projection_hash,'request_hash',o.request_hash)
        AND c.after_state#>>'{workflow_recovery,task_id}'=OLD.task_id::text
        AND c.after_state#>>'{workflow_recovery,task_version}'=t.version::text
        AND c.after_state#>>'{workflow_recovery,worker_window_id}'=c.id::text
        AND c.after_state#>>'{workflow_recovery,gateway_window_id}'=g.id::text
        AND c.after_state#>>'{workflow_recovery,expires_at}'=c.after_state->>'expires_at'
        AND c.after_state#>>'{workflow_recovery,target_key}'=OLD.target_key
        AND c.after_state#>>'{workflow_recovery,approval_id}'=a.id::text
        AND c.after_state#>>'{workflow_recovery,decision_id}'=a.decision_id::text
        AND c.after_state#>>'{workflow_recovery,decision_payload_hash}'=a.decision_payload_hash
        AND c.after_state#>>'{workflow_recovery,execution_id}'=x.id::text
        AND c.after_state#>>'{workflow_recovery,original_gateway_id}'<>g.id::text
        AND t.organization_id=OLD.organization_id AND t.shop_id=OLD.shop_id
        AND t.state='completed' AND t.kind='inventory_replenishment'
        AND i.organization_id=OLD.organization_id AND i.shop_id=OLD.shop_id
        AND i.task_id=OLD.task_id AND i.version=1 AND i.status='open'
        AND x.status='completed' AND x.item_ids=ARRAY[OLD.item_id]
        AND business.valid_p3_execution(x.id)
        AND a.status='approved' AND a.consumed_at IS NOT NULL
        AND a.decision_action IN ('approve','approve_with_assumptions')
        AND t.active_plan_id=a.plan_id AND i.approved_plan_id=a.plan_id
        AND o.organization_id=OLD.organization_id AND o.shop_id=OLD.shop_id
        AND o.task_id=OLD.task_id AND o.aggregate_id=OLD.item_id AND o.aggregate_version=1
        AND o.provider_idempotency_key
          =OLD.client_token
        AND o.destination='bitable' AND o.operation='item_projection'
        AND o.source_mode='mock' AND NOT o.sender_enabled
        AND business.lock_p3_permission(t.requester_id,OLD.organization_id,OLD.shop_id,
          (t.normalized_request->>'identity_id')::uuid,
          (c.after_state#>>'{workflow_recovery,operator_auth_version}')::bigint,'operator')
        AND business.lock_p3_permission(a.decided_by,OLD.organization_id,OLD.shop_id,
          a.decided_identity_id,a.decided_auth_version,'approver')
        AND w.organization_id=OLD.organization_id AND w.shop_id=OLD.shop_id
        AND w.configured_enabled AND w.verification_mode='controlled_sdk'
        AND w.expires_at=(c.after_state->>'expires_at')::timestamptz
        AND w.expires_at>clock_timestamp()
        AND w.expires_at<=c.occurred_at+interval '300 seconds'
        AND EXISTS(SELECT 1 FROM business.p4_sdk_calls auth
          WHERE auth.window_id=w.id AND auth.subject_id=w.id AND auth.task_id IS NULL
          AND auth.scope_kind='preflight' AND auth.method=
          'auth.v3.tenant_access_token.internal'
          AND auth.status='returned' AND auth.http_status=200 AND auth.provider_code=0
          AND auth.started_at>=w.created_at AND auth.completed_at<=clock_timestamp())
        AND w.method_caps=c.after_state->'caps'
        AND w.method_caps-'auth.v3.tenant_access_token.internal'-'bot.v3.info'
          -'bitable.v1.app_table.list'-'bitable.v1.app_table_field.list'
          -'bitable.v1.app_table_record.list'-'bitable.v1.app_table_record.create'
          -'bitable.v1.app_table_record.update'='{}'::jsonb
        AND w.method_caps->'auth.v3.tenant_access_token.internal'='1'::jsonb
        AND w.method_caps->'bot.v3.info'='1'::jsonb
        AND w.method_caps->'bitable.v1.app_table_record.create'='1'::jsonb
        AND w.method_caps->'bitable.v1.app_table_record.list' IN ('2'::jsonb,'3'::jsonb,'4'::jsonb)
        AND w.method_caps->'bitable.v1.app_table_field.list' IN ('1'::jsonb,'2'::jsonb)
        AND (NOT w.method_caps ? 'bitable.v1.app_table.list'
          OR w.method_caps->'bitable.v1.app_table.list' IN ('1'::jsonb,'2'::jsonb))
        AND (NOT w.method_caps ? 'bitable.v1.app_table_record.update'
          OR w.method_caps->'bitable.v1.app_table_record.update'='1'::jsonb)
        AND g.organization_id=OLD.organization_id AND g.source='feishu_gateway'
        AND g.action='gateway_start_claimed' AND g.entity_type='gateway_window'
        AND g.entity_id=g.id::text AND g.after_state->'enabled'='true'::jsonb
        AND g.after_state->>'organization_id'=OLD.organization_id::text
        AND g.after_state->>'shop_id'=OLD.shop_id::text
        AND g.after_state->'max_workflows'='0'::jsonb
        AND (g.after_state->>'expires_at')::timestamptz>=w.expires_at
        AND (g.after_state->>'expires_at')::timestamptz<=g.occurred_at+interval '300 seconds'
        AND g.occurred_at<=c.occurred_at AND c.occurred_at<=w.created_at
        AND g.occurred_at<=worker.occurred_at AND worker.occurred_at<=w.created_at
        AND sender.worker_owner=NEW.claimed_by AND sender.configured_enabled
        AND sender.verification_mode='controlled_sdk' AND sender.expires_at=w.expires_at
        AND sender.checked_at>=worker.occurred_at
        AND EXISTS(SELECT 1 FROM pg_locks lock WHERE lock.locktype='advisory' AND lock.granted
          AND lock.mode='ExclusiveLock' AND lock.pid=sender.worker_backend_pid
          AND lock.database=(SELECT oid FROM pg_database WHERE datname=current_database())
          AND lock.objsubid=1 AND lock.classid=(7412438461303::bigint>>32)::oid
          AND lock.objid=(7412438461303::bigint&4294967295)::oid)
        AND EXISTS(SELECT 1 FROM pg_locks lock WHERE lock.locktype='advisory' AND lock.granted
          AND lock.mode='ExclusiveLock'
          AND lock.database=(SELECT oid FROM pg_database WHERE datname=current_database())
          AND lock.objsubid=1 AND lock.classid=((hashtextextended(
            'p4-gateway:'||org.feishu_app_id,0)>>32)&4294967295)::oid
          AND lock.objid=(hashtextextended('p4-gateway:'||org.feishu_app_id,0)&4294967295)::oid)
        AND (SELECT count(*) FROM business.audit_events same_worker
          WHERE same_worker.organization_id=OLD.organization_id AND same_worker.source='worker'
          AND same_worker.entity_type='worker_runtime' AND same_worker.action='started'
          AND same_worker.entity_id=NEW.claimed_by)=1
        AND (SELECT count(*) FROM business.audit_events gateway_start
          WHERE gateway_start.organization_id=OLD.organization_id
          AND gateway_start.source='feishu_gateway' AND gateway_start.entity_type='gateway_runtime'
          AND gateway_start.action='started' AND gateway_start.entity_id=g.id::text)=1
        AND NOT EXISTS(SELECT 1 FROM business.audit_events ended
          WHERE ended.organization_id=OLD.organization_id
          AND ((ended.source='worker' AND ended.entity_type='worker_runtime'
            AND ended.entity_id=NEW.claimed_by
            AND ended.action IN ('stopped','termination_confirmed'))
          OR (ended.source='feishu_gateway' AND ended.entity_type='gateway_runtime'
            AND ended.entity_id=g.id::text AND ended.action='termination_confirmed')))
        AND NOT EXISTS(SELECT 1 FROM business.p4_base_links link
          WHERE link.organization_id=OLD.organization_id AND link.shop_id=OLD.shop_id
          AND link.target_key
          =OLD.target_key AND link.item_id=OLD.item_id)
        AND NOT EXISTS(SELECT 1 FROM business.p4_sdk_calls call
          WHERE call.subject_id=OLD.outbox_id AND call.method='bitable.v1.app_table_record.create')
        AND NOT EXISTS(SELECT 1 FROM business.p4_sdk_windows prior
          WHERE prior.organization_id=OLD.organization_id AND prior.shop_id=OLD.shop_id
          AND prior.id<>w.id AND prior.configured_enabled AND prior.expires_at>clock_timestamp())
        AND NOT EXISTS(SELECT 1 FROM business.audit_events prior
          WHERE prior.organization_id=OLD.organization_id AND prior.action='started'
          AND ((prior.source='worker' AND prior.entity_type='worker_runtime'
            AND prior.entity_id<>NEW.claimed_by)
          OR (prior.source='feishu_gateway' AND prior.entity_type='gateway_runtime'
            AND prior.entity_id<>g.id::text))
          AND ((SELECT count(*) FROM business.audit_events duplicate
            WHERE duplicate.organization_id=prior.organization_id AND duplicate.source=prior.source
            AND duplicate.entity_type=prior.entity_type AND duplicate.entity_id=prior.entity_id
            AND duplicate.action='started')<>1
          OR jsonb_typeof(prior.after_state) IS DISTINCT FROM 'object'
          OR prior.after_state-ARRAY['pid','host','pid_namespace']::text[]<>'{}'::jsonb
          OR jsonb_typeof(prior.after_state->'pid') IS DISTINCT FROM 'number'
          OR NOT (COALESCE(prior.after_state->>'pid','') ~ '^[1-9][0-9]*$')
          OR jsonb_typeof(prior.after_state->'host') IS DISTINCT FROM 'string'
          OR COALESCE(prior.after_state->>'host','')=''
          OR jsonb_typeof(prior.after_state->'pid_namespace') IS DISTINCT FROM 'string'
          OR COALESCE(prior.after_state->>'pid_namespace','')=''
          OR NOT EXISTS(SELECT 1 FROM business.audit_events term
            WHERE term.organization_id=prior.organization_id AND term.source=prior.source
            AND term.entity_type=prior.entity_type AND term.entity_id=prior.entity_id
            AND term.action='termination_confirmed'
            AND prior.occurred_at<=term.occurred_at AND term.occurred_at<g.occurred_at
            AND (SELECT count(*) FROM business.audit_events duplicate_term
              WHERE duplicate_term.organization_id=prior.organization_id
              AND duplicate_term.source=prior.source
              AND duplicate_term.entity_type=prior.entity_type
              AND duplicate_term.entity_id=prior.entity_id
              AND duplicate_term.action='termination_confirmed')=1
            AND ((prior.source='feishu_gateway' AND term.after_state->'process'=prior.after_state
              AND term.after_state->'child_reaped'='true'::jsonb
              AND jsonb_typeof(term.after_state->'child_exit')='number'
              AND COALESCE(term.after_state->>'child_exit','') ~ '^-?[0-9]+$')
            OR (prior.source='worker' AND length(trim(COALESCE(term.reason,'')))>0
              AND term.after_state-ARRAY['pid','host','pid_namespace']::text[]='{}'::jsonb
              AND jsonb_typeof(term.after_state->'pid')='number'
              AND COALESCE(term.after_state->>'pid','') ~ '^[1-9][0-9]*$'
              AND term.after_state->'host'=prior.after_state->'host'
              AND term.after_state->'pid_namespace'=prior.after_state->'pid_namespace'
              AND (SELECT count(*) FROM business.audit_events stop
                WHERE stop.organization_id=prior.organization_id AND stop.source='worker'
                AND stop.entity_type='worker_runtime' AND stop.entity_id=prior.entity_id
                AND stop.action='stopped')<=1
              AND NOT EXISTS(SELECT 1 FROM business.audit_events stop
                WHERE stop.organization_id=prior.organization_id AND stop.source='worker'
                AND stop.entity_type='worker_runtime' AND stop.entity_id=prior.entity_id
                AND stop.action='stopped' AND (stop.after_state IS DISTINCT FROM prior.after_state
                  OR stop.occurred_at<prior.occurred_at OR stop.occurred_at>term.occurred_at)))))));
      END IF;
      -- End P4 explicit C0 persisted claim
      IF (NEW.outbox_id,NEW.organization_id,NEW.shop_id,NEW.task_id,NEW.item_id,NEW.target_key,
      NEW.client_token,NEW.version,NEW.verification_mode,NEW.projection,NEW.projection_hash,NEW.created_at)
      IS DISTINCT FROM (OLD.outbox_id,OLD.organization_id,OLD.shop_id,OLD.task_id,OLD.item_id,
      OLD.target_key,OLD.client_token,OLD.version,OLD.verification_mode,
      OLD.projection,OLD.projection_hash,OLD.created_at)
      OR NEW.attempts<OLD.attempts
      OR (OLD.status IN ('verified','conflict','fatal','stale') AND NEW IS DISTINCT FROM OLD)
      OR (OLD.status='unknown' AND NEW.status NOT IN
      ('unknown','sending','verified','conflict','fatal','stale'))
      OR (OLD.status='unknown' AND NEW.status='sending' AND NEW.last_operation<>'reconcile'
      AND NOT first_create)
      OR (OLD.external_id IS NOT NULL AND NEW.external_id IS DISTINCT FROM OLD.external_id)
      OR (OLD.first_attempt_at IS NOT NULL
      AND NEW.first_attempt_at IS DISTINCT FROM OLD.first_attempt_at)
      OR (OLD.unknown_since IS NOT NULL AND
      (NEW.unknown_since IS DISTINCT FROM OLD.unknown_since OR NEW.status='pending'
      OR (NEW.status='sending' AND NEW.last_operation<>'reconcile' AND NOT first_create)))
      THEN RAISE EXCEPTION 'P4 projection snapshot or unknown write is immutable'
      USING ERRCODE='23514'; END IF;
    END IF;
    IF NEW.status='unknown' AND NEW.unknown_since IS NULL THEN
      NEW.unknown_since:=clock_timestamp();
    END IF; RETURN NEW; END $$"""


def upgrade() -> None:
    op.execute(TRIGGER_SQL)


def downgrade() -> None:
    raise RuntimeError("P4 first-create authorization history cannot be reset by downgrade")
