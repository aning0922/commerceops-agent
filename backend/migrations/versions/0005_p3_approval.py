"""P3固定角色scope、Web会话、独立Workflow与T2不可变审批意图。"""

from alembic import op

revision = "0005_p3_approval"
down_revision = "0004_model_call_owner"
branch_labels = None
depends_on = None

DDL = """
ALTER TABLE business.identities ADD UNIQUE(organization_id,id,principal_id);
CREATE TABLE business.principal_role_shop_grants (
 organization_id uuid NOT NULL,shop_id uuid NOT NULL,principal_id uuid NOT NULL,
 role text NOT NULL CHECK(role IN ('operator','approver','admin')),enabled boolean NOT NULL,
 PRIMARY KEY(organization_id,shop_id,principal_id,role),
 FOREIGN KEY(organization_id,shop_id,principal_id)
 REFERENCES business.principal_shop_scopes(organization_id,shop_id,principal_id)
);
CREATE TABLE business.web_credentials (
 login text PRIMARY KEY CHECK(login ~ '^[a-z0-9._-]{1,100}$'),
 organization_id uuid NOT NULL,principal_id uuid NOT NULL,identity_id uuid NOT NULL,
 password_hash text NOT NULL CHECK(password_hash ~
 '^scrypt-v1[$]131072[$]8[$]1[$][a-f0-9]{32}[$][a-f0-9]{64}$'),
 enabled boolean NOT NULL DEFAULT true,
 FOREIGN KEY(organization_id,identity_id,principal_id)
 REFERENCES business.identities(organization_id,id,principal_id)
);
CREATE TABLE business.web_sessions (
 id uuid PRIMARY KEY,token_hash text NOT NULL UNIQUE CHECK(token_hash ~ '^[a-f0-9]{64}$'),
 kind text NOT NULL CHECK(kind IN ('anonymous_bootstrap','session')),
 organization_id uuid,principal_id uuid,identity_id uuid,auth_version integer,
 csrf_digest text NOT NULL CHECK(csrf_digest ~ '^[a-f0-9]{64}$'),key_version text NOT NULL,
 created_at timestamptz NOT NULL,last_seen_at timestamptz NOT NULL,
 absolute_expires_at timestamptz NOT NULL,idle_expires_at timestamptz NOT NULL,
 revoked_at timestamptz,
 CHECK(absolute_expires_at>created_at AND idle_expires_at>created_at),
 CHECK((kind='anonymous_bootstrap' AND organization_id IS NULL AND principal_id IS NULL
 AND identity_id IS NULL AND auth_version IS NULL) OR
 (kind='session' AND organization_id IS NOT NULL AND principal_id IS NOT NULL
 AND identity_id IS NOT NULL AND auth_version IS NOT NULL AND auth_version>0)),
 FOREIGN KEY(organization_id,identity_id,principal_id)
 REFERENCES business.identities(organization_id,id,principal_id)
);
CREATE TABLE business.web_login_attempts (
 id uuid PRIMARY KEY,login_digest text NOT NULL,peer_digest text NOT NULL,
 occurred_at timestamptz NOT NULL
);
CREATE INDEX web_login_rate ON business.web_login_attempts(occurred_at);
CREATE TABLE business.web_requests (
 organization_id uuid NOT NULL,principal_id uuid NOT NULL,
 operation text NOT NULL CHECK(operation IN ('create_task','decision','resolve')),
 request_key uuid NOT NULL,request_hash text NOT NULL CHECK(request_hash ~ '^[a-f0-9]{64}$'),
 task_id uuid NOT NULL,result jsonb NOT NULL CHECK(jsonb_typeof(result)='object'),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(principal_id,operation,request_key),
 FOREIGN KEY(organization_id,principal_id) REFERENCES business.principals(organization_id,id),
 FOREIGN KEY(organization_id,task_id) REFERENCES business.business_tasks(organization_id,id)
);
CREATE TABLE business.p3_task_sources (
 organization_id uuid NOT NULL,shop_id uuid NOT NULL,task_id uuid NOT NULL,
 source_task_id uuid NOT NULL,source_report_id uuid,snapshot_id uuid,facts_hash text,
 mode text NOT NULL CHECK(mode IN ('from_report','new_cycle')),
 parameters jsonb NOT NULL CHECK(jsonb_typeof(parameters)='object'),
 config_version text NOT NULL,
 CHECK((source_report_id IS NULL AND snapshot_id IS NULL AND facts_hash IS NULL)
 OR (source_report_id IS NOT NULL AND snapshot_id IS NOT NULL AND facts_hash IS NOT NULL
 AND facts_hash ~ '^[a-f0-9]{64}$')),
 CHECK(mode<>'from_report' OR source_report_id IS NOT NULL),
 PRIMARY KEY(task_id),UNIQUE(organization_id,shop_id,task_id),
 FOREIGN KEY(organization_id,shop_id,task_id)
 REFERENCES business.business_tasks(organization_id,shop_id,id),
 FOREIGN KEY(organization_id,shop_id,source_task_id)
 REFERENCES business.business_tasks(organization_id,shop_id,id),
 FOREIGN KEY(organization_id,shop_id,source_task_id,source_report_id)
 REFERENCES business.analysis_reports(organization_id,shop_id,task_id,id),
 FOREIGN KEY(organization_id,shop_id,source_task_id,snapshot_id)
 REFERENCES business.commerce_snapshots(organization_id,shop_id,task_id,id)
);
CREATE TABLE business.replenishment_plans (
 id uuid PRIMARY KEY,organization_id uuid NOT NULL,shop_id uuid NOT NULL,task_id uuid NOT NULL,
 version integer NOT NULL CHECK(version>0),
 status text NOT NULL DEFAULT 'current'
 CHECK(status IN ('current','superseded','invalidated','executed')),
 source_task_id uuid NOT NULL,report_id uuid NOT NULL,snapshot_id uuid NOT NULL,
 facts_hash text NOT NULL,plan_hash text NOT NULL CHECK(plan_hash ~ '^[a-f0-9]{64}$'),
 content jsonb NOT NULL,canonical_content text NOT NULL,expires_at timestamptz NOT NULL,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 CHECK(canonical_content::jsonb=content),
 CHECK(plan_hash=encode(sha256(convert_to(canonical_content,'UTF8')),'hex')),
 CHECK(content->>'plan_id'=id::text AND (content->>'plan_version')::integer=version),
 CHECK(content->>'task_id'=task_id::text AND content->>'shop_id'=shop_id::text
 AND content->>'organization_id'=organization_id::text),
 CHECK((content->>'expires_at')::timestamptz=expires_at),
 UNIQUE(task_id,version),UNIQUE(organization_id,shop_id,task_id,id),
 FOREIGN KEY(organization_id,shop_id,task_id)
 REFERENCES business.p3_task_sources(organization_id,shop_id,task_id),
 FOREIGN KEY(organization_id,shop_id,source_task_id,report_id)
 REFERENCES business.analysis_reports(organization_id,shop_id,task_id,id),
 FOREIGN KEY(organization_id,shop_id,source_task_id,snapshot_id)
 REFERENCES business.commerce_snapshots(organization_id,shop_id,task_id,id)
);
ALTER TABLE business.business_tasks DROP CONSTRAINT active_plan_reserved;
ALTER TABLE business.business_tasks ADD CONSTRAINT p3_active_plan_only
 CHECK(active_plan_id IS NULL OR (kind='inventory_replenishment'
 AND workflow_version='p3-inventory-replenishment-v1'));
ALTER TABLE business.business_tasks ADD FOREIGN KEY(organization_id,shop_id,id,active_plan_id)
 REFERENCES business.replenishment_plans(organization_id,shop_id,task_id,id);
CREATE TABLE business.approvals (
 id uuid PRIMARY KEY,organization_id uuid NOT NULL,shop_id uuid NOT NULL,task_id uuid NOT NULL,
 plan_id uuid NOT NULL UNIQUE,plan_version integer NOT NULL,plan_hash text NOT NULL,
 status text NOT NULL DEFAULT 'pending'
 CHECK(status IN ('pending','approved','rejected','expired','superseded')),
 eligible_principal_ids uuid[] NOT NULL,nonce_hash text NOT NULL
 CHECK(nonce_hash ~ '^[a-f0-9]{64}$'),nonce_key_version text NOT NULL,
 expires_at timestamptz NOT NULL,ready_at timestamptz,
 decision_id uuid UNIQUE,decision_action text,decision_payload_hash text,
 acknowledged_assumption_keys text[] NOT NULL DEFAULT '{}',
 decided_by uuid,decided_at timestamptz,decision_source text,decision_request_key uuid,
 reason_code text,consumed_at timestamptz,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 UNIQUE(organization_id,shop_id,task_id,id),
 FOREIGN KEY(organization_id,shop_id,task_id,plan_id)
 REFERENCES business.replenishment_plans(organization_id,shop_id,task_id,id),
 FOREIGN KEY(organization_id,decided_by) REFERENCES business.principals(organization_id,id),
 CHECK((status IN ('approved','rejected'))=(decision_id IS NOT NULL)),
 CHECK(decision_id IS NULL OR (decision_action IN
 ('approve','reject','approve_with_assumptions','reject_assumptions')
 AND decision_payload_hash ~ '^[a-f0-9]{64}$' AND decided_by IS NOT NULL
 AND decided_at IS NOT NULL AND decision_source='web' AND decision_request_key IS NOT NULL))
);
CREATE TABLE business.outbox (
 id uuid PRIMARY KEY,organization_id uuid NOT NULL,shop_id uuid NOT NULL,task_id uuid NOT NULL,
 destination text NOT NULL,aggregate_id uuid NOT NULL,aggregate_version integer NOT NULL,
 operation text NOT NULL,dedupe_key text NOT NULL UNIQUE,request_hash text NOT NULL,
 payload jsonb NOT NULL,provider_idempotency_key uuid NOT NULL,
 status text NOT NULL
 CHECK(status IN ('blocked','pending','sending','sent','retry_wait','unknown','dead')),
 attempts integer NOT NULL DEFAULT 0,next_attempt_at timestamptz,
 external_id text,last_error text,
 sender_enabled boolean NOT NULL DEFAULT false CHECK(NOT sender_enabled),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 FOREIGN KEY(organization_id,shop_id,task_id)
 REFERENCES business.business_tasks(organization_id,shop_id,id)
);
"""


def upgrade() -> None:
    for statement in DDL.split(";"):
        if statement.strip():
            op.execute(statement)
    op.execute("""
CREATE FUNCTION business.p3_revoke_scope() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,business AS $$
DECLARE actor uuid; org uuid;
BEGIN
 IF TG_OP='DELETE' THEN actor:=OLD.principal_id; org:=OLD.organization_id;
 ELSE actor:=NEW.principal_id; org:=NEW.organization_id; END IF;
 PERFORM 1 FROM business.principals WHERE id=actor AND organization_id=org FOR UPDATE;
 IF TG_OP='DELETE' OR (TG_OP='UPDATE' AND NEW IS DISTINCT FROM OLD)
 OR (TG_OP='INSERT' AND TG_TABLE_NAME='principal_role_shop_grants')
 OR (TG_OP='INSERT' AND EXISTS(SELECT 1 FROM business.web_credentials c
 WHERE c.organization_id=org AND c.principal_id=actor)) THEN
  UPDATE business.principals SET auth_version=auth_version+1,
  updated_at=clock_timestamp() WHERE id=actor AND organization_id=org;
 END IF;
 RETURN CASE WHEN TG_OP='DELETE' THEN OLD ELSE NEW END;
END $$
""")
    for table in ("principal_role_shop_grants", "principal_shop_scopes", "web_credentials"):
        op.execute(f"""CREATE TRIGGER p3_scope_principal_lock BEFORE INSERT OR UPDATE OR DELETE
 ON business.{table} FOR EACH ROW EXECUTE FUNCTION business.p3_revoke_scope()""")
    op.execute("""
CREATE FUNCTION business.lock_p3_permission(actor uuid,org uuid,shop uuid,identity uuid,
 auth bigint,requested_role text) RETURNS boolean LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path=pg_catalog,business AS $$
BEGIN
 PERFORM 1 FROM business.principals p WHERE p.id=actor AND p.organization_id=org
 AND p.enabled AND p.auth_version=auth AND requested_role=ANY(p.roles) FOR SHARE;
 IF NOT FOUND THEN RETURN false; END IF;
 RETURN EXISTS(SELECT 1 FROM business.principal_shop_scopes s
 JOIN business.principal_role_shop_grants g ON g.principal_id=s.principal_id
 AND g.organization_id=s.organization_id AND g.shop_id=s.shop_id
 WHERE s.principal_id=actor AND s.organization_id=org AND s.shop_id=shop
 AND s.enabled AND g.enabled AND g.role=requested_role
 AND EXISTS(SELECT 1 FROM business.identities i JOIN business.web_credentials c
 ON c.identity_id=i.id AND c.principal_id=i.principal_id AND c.organization_id=i.organization_id
 WHERE i.id=identity AND i.principal_id=actor AND i.organization_id=org
 AND i.provider='web' AND c.enabled) FOR SHARE OF s,g);
END
$$
""")
    op.execute("""REVOKE ALL ON FUNCTION business.lock_p3_permission(
 uuid,uuid,uuid,uuid,bigint,text) FROM PUBLIC""")
    op.execute("""
CREATE FUNCTION business.p3_immutable_plan() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF TG_OP='DELETE' OR (NEW.id,NEW.organization_id,NEW.shop_id,NEW.task_id,NEW.version,
 NEW.source_task_id,NEW.report_id,NEW.snapshot_id,NEW.facts_hash,NEW.plan_hash,
 NEW.content,NEW.canonical_content,NEW.expires_at,NEW.created_at)
 IS DISTINCT FROM (OLD.id,OLD.organization_id,OLD.shop_id,OLD.task_id,OLD.version,
 OLD.source_task_id,OLD.report_id,OLD.snapshot_id,OLD.facts_hash,OLD.plan_hash,
 OLD.content,OLD.canonical_content,OLD.expires_at,OLD.created_at) THEN
  RAISE EXCEPTION 'P3 plan is immutable' USING ERRCODE='23514';
 END IF;
 RETURN NEW;
END $$
""")
    op.execute("""CREATE TRIGGER p3_immutable_plan BEFORE UPDATE OR DELETE
 ON business.replenishment_plans FOR EACH ROW EXECUTE FUNCTION business.p3_immutable_plan()""")
    op.execute("""CREATE TRIGGER p3_immutable_plan_truncate BEFORE TRUNCATE
 ON business.replenishment_plans FOR EACH STATEMENT
 EXECUTE FUNCTION business.reject_inventory_mutation()""")
    op.execute("""
CREATE FUNCTION business.bind_p3_source() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NOT EXISTS(SELECT 1 FROM business.business_tasks t JOIN business.business_tasks s
 ON s.id=NEW.source_task_id AND s.organization_id=t.organization_id AND s.shop_id=t.shop_id
 AND s.requester_id=t.requester_id WHERE t.id=NEW.task_id AND t.organization_id=NEW.organization_id
 AND t.shop_id=NEW.shop_id AND t.kind='inventory_replenishment'
 AND t.workflow_version='p3-inventory-replenishment-v1' AND s.kind='inventory_analysis_only'
 AND s.workflow_version='p203-inventory-analysis-v1') THEN
  RAISE EXCEPTION 'P3 source binding mismatch' USING ERRCODE='23514';
 END IF;
 IF NEW.source_report_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM business.analysis_reports r
 WHERE r.id=NEW.source_report_id AND r.task_id=NEW.source_task_id AND r.snapshot_id=NEW.snapshot_id
 AND r.organization_id=NEW.organization_id AND r.shop_id=NEW.shop_id
 AND r.facts_hash=NEW.facts_hash) THEN
  RAISE EXCEPTION 'P3 report binding mismatch' USING ERRCODE='23514';
 END IF;
 IF TG_OP='UPDATE' AND ((NEW.organization_id,NEW.shop_id,NEW.task_id,NEW.source_task_id,
 NEW.mode,NEW.parameters,NEW.config_version) IS DISTINCT FROM
 (OLD.organization_id,OLD.shop_id,OLD.task_id,OLD.source_task_id,OLD.mode,OLD.parameters,OLD.config_version)
 OR (OLD.source_report_id IS NOT NULL AND NEW IS DISTINCT FROM OLD)) THEN
  RAISE EXCEPTION 'P3 source is immutable once bound' USING ERRCODE='23514';
 END IF;
 RETURN NEW;
END $$
""")
    op.execute("""CREATE TRIGGER bind_p3_source BEFORE INSERT OR UPDATE
 ON business.p3_task_sources FOR EACH ROW EXECUTE FUNCTION business.bind_p3_source()""")
    op.execute("""
CREATE FUNCTION business.preserve_p3_task() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF TG_OP='INSERT' THEN
  IF NEW.kind='inventory_replenishment' AND
  (NEW.workflow_version<>'p3-inventory-replenishment-v1' OR NEW.state<>'queued') THEN
   RAISE EXCEPTION 'P3 must begin queued at pinned workflow' USING ERRCODE='23514';
  END IF;
  RETURN NEW;
 END IF;
 IF OLD.kind='inventory_replenishment' OR NEW.kind='inventory_replenishment' THEN
  IF (NEW.kind,NEW.normalized_request) IS DISTINCT FROM (OLD.kind,OLD.normalized_request)
  OR (OLD.state IN ('completed','rejected','expired') AND NEW.state<>OLD.state) THEN
   RAISE EXCEPTION 'P3 identity or terminal state is immutable' USING ERRCODE='23514';
  END IF;
  IF NEW.state='completed' AND OLD.state<>'completed' AND
   (NEW.active_plan_id IS NOT NULL OR NOT EXISTS(
    SELECT 1 FROM business.p3_task_sources b JOIN business.analysis_reports r
    ON r.id=b.source_report_id AND r.task_id=b.source_task_id AND r.snapshot_id=b.snapshot_id
    AND r.facts_hash=b.facts_hash AND r.organization_id=b.organization_id AND r.shop_id=b.shop_id
    JOIN business.business_tasks s ON s.id=b.source_task_id AND s.state='completed'
    WHERE b.task_id=NEW.id AND b.organization_id=NEW.organization_id AND b.shop_id=NEW.shop_id
    AND r.report->'candidate_count'='0'::jsonb AND r.report->'complete'='true'::jsonb
    AND r.report->'source_complete'='true'::jsonb AND r.report->'requires_review'='false'::jsonb
   )) THEN
   -- A01仅无动作完成；A03须另迁移加入永久execution回执证明。
   RAISE EXCEPTION 'P3 completed requires bound no-action facts' USING ERRCODE='23514';
  END IF;
 END IF;
 RETURN NEW;
END $$
""")
    op.execute("""CREATE TRIGGER preserve_p3_task BEFORE INSERT OR UPDATE
 ON business.business_tasks FOR EACH ROW EXECUTE FUNCTION business.preserve_p3_task()""")
    op.execute("""
CREATE FUNCTION business.bind_p3_approval() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NOT EXISTS(SELECT 1 FROM business.replenishment_plans p WHERE p.id=NEW.plan_id
 AND p.task_id=NEW.task_id AND p.organization_id=NEW.organization_id AND p.shop_id=NEW.shop_id
 AND p.version=NEW.plan_version AND p.plan_hash=NEW.plan_hash AND p.expires_at=NEW.expires_at) THEN
  RAISE EXCEPTION 'P3 approval binding mismatch' USING ERRCODE='23514';
 END IF;
 IF TG_OP='UPDATE' AND ((NEW.id,NEW.organization_id,NEW.shop_id,NEW.task_id,NEW.plan_id,
 NEW.plan_version,NEW.plan_hash,NEW.eligible_principal_ids,NEW.nonce_hash,NEW.nonce_key_version,
 NEW.expires_at,NEW.created_at) IS DISTINCT FROM
 (OLD.id,OLD.organization_id,OLD.shop_id,OLD.task_id,OLD.plan_id,OLD.plan_version,OLD.plan_hash,
 OLD.eligible_principal_ids,OLD.nonce_hash,OLD.nonce_key_version,OLD.expires_at,OLD.created_at)
 OR (OLD.status<>'pending' AND NEW.status<>OLD.status)
 OR (OLD.decision_id IS NOT NULL AND (NEW.decision_id,NEW.decision_action,
 NEW.decision_payload_hash,NEW.acknowledged_assumption_keys,NEW.decided_by,NEW.decided_at,
 NEW.decision_source,NEW.decision_request_key,NEW.reason_code) IS DISTINCT FROM
 (OLD.decision_id,OLD.decision_action,OLD.decision_payload_hash,OLD.acknowledged_assumption_keys,
 OLD.decided_by,OLD.decided_at,OLD.decision_source,OLD.decision_request_key,OLD.reason_code))) THEN
  RAISE EXCEPTION 'P3 historical approval is immutable' USING ERRCODE='23514';
 END IF;
 RETURN NEW;
END $$
""")
    op.execute("""CREATE TRIGGER bind_p3_approval BEFORE INSERT OR UPDATE
 ON business.approvals FOR EACH ROW EXECUTE FUNCTION business.bind_p3_approval()""")


def downgrade() -> None:
    raise RuntimeError("destructive downgrade disabled; restore a verified backup")
