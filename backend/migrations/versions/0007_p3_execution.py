"""P3不可变重观测/双来源计划、永久T4回执与T6单项终态；仅内部工作项。"""

from alembic import op

revision = "0007_p3_execution"
down_revision = "0006_p3_decisions"
branch_labels = None
depends_on = None

DDL = """
ALTER TABLE business.replenishment_plans ADD UNIQUE(organization_id,shop_id,task_id,
 id,version);
CREATE TABLE business.p3_observations (
 id uuid PRIMARY KEY,report_id uuid NOT NULL UNIQUE,
 organization_id uuid NOT NULL,shop_id uuid NOT NULL,task_id uuid NOT NULL,
 source_task_id uuid NOT NULL,original_report_id uuid NOT NULL,original_snapshot_id
 uuid NOT NULL,
 original_facts_hash text NOT NULL,
 generation_plan_id uuid NOT NULL,generation_plan_version integer NOT NULL
 CHECK(generation_plan_version>0),
 generation_config_version text NOT NULL CHECK(length(generation_config_version)>0),
 schema_version text NOT NULL CHECK(schema_version='p3-observation-v1'),
 hash_version text NOT NULL CHECK(hash_version='canonical-facts-v1'),
 parameters jsonb NOT NULL,input jsonb NOT NULL,canonical_input text NOT NULL,
 input_hash text
 NOT NULL,
 report jsonb NOT NULL,canonical_report text NOT NULL,report_hash text NOT NULL,
 facts_hash text
 NOT NULL,
 canonical_facts text NOT NULL,
 material_hash text NOT NULL CHECK(material_hash ~ '^[a-f0-9]{64}$'),
 collection_started_at timestamptz NOT NULL,collected_at timestamptz NOT NULL,
 consistency text NOT NULL CHECK(consistency='observational'),
 CHECK(id<>report_id AND collected_at>=collection_started_at),
 CHECK(canonical_input::jsonb=input AND canonical_report::jsonb=report),
 CHECK(input_hash=encode(sha256(convert_to(canonical_input,'UTF8')),'hex')),
 CHECK(report_hash=encode(sha256(convert_to(canonical_report,'UTF8')),'hex')),
 CHECK(report->>'facts_hash'=facts_hash AND facts_hash ~ '^[a-f0-9]{64}$'),
 CHECK(report->>'input_hash'=input_hash),
 CHECK(canonical_facts::jsonb=business.p3_report_facts(report)),
 CHECK(facts_hash=encode(sha256(convert_to(canonical_facts,'UTF8')),'hex')),
 UNIQUE(organization_id,shop_id,task_id,id),
 FOREIGN KEY(organization_id,shop_id,task_id)
 REFERENCES business.p3_task_sources(organization_id,shop_id,task_id),
 FOREIGN KEY(organization_id,shop_id,source_task_id,original_report_id)
 REFERENCES business.analysis_reports(organization_id,shop_id,task_id,id),
 FOREIGN KEY(organization_id,shop_id,source_task_id,original_snapshot_id)
 REFERENCES business.commerce_snapshots(organization_id,shop_id,task_id,id),
 FOREIGN KEY(organization_id,shop_id,task_id,generation_plan_id,generation_plan_version)
 REFERENCES business.replenishment_plans(organization_id,shop_id,task_id,id,version)
 DEFERRABLE INITIALLY DEFERRED
);
ALTER TABLE business.replenishment_plans ADD COLUMN evidence_kind text NOT NULL DEFAULT
 'p2_original';
ALTER TABLE business.replenishment_plans ADD COLUMN p2_report_id uuid;
ALTER TABLE business.replenishment_plans ADD COLUMN p2_snapshot_id uuid;
ALTER TABLE business.replenishment_plans ADD COLUMN p3_observation_id uuid;
UPDATE business.replenishment_plans SET p2_report_id=report_id,
 p2_snapshot_id=snapshot_id;
ALTER TABLE business.replenishment_plans ADD CONSTRAINT p3_evidence_exclusive CHECK(
 (evidence_kind='p2_original' AND p2_report_id IS NOT NULL AND p2_snapshot_id IS NOT
 NULL
 AND p3_observation_id IS NULL AND version=1) OR
 (evidence_kind='p3_observation' AND p2_report_id IS NULL AND p2_snapshot_id IS NULL
 AND p3_observation_id IS NOT NULL AND version>1));
ALTER TABLE business.replenishment_plans ADD FOREIGN KEY
 (organization_id,shop_id,source_task_id,p2_report_id)
 REFERENCES business.analysis_reports(organization_id,shop_id,task_id,id);
ALTER TABLE business.replenishment_plans ADD FOREIGN KEY
 (organization_id,shop_id,source_task_id,p2_snapshot_id)
 REFERENCES business.commerce_snapshots(organization_id,shop_id,task_id,id);
ALTER TABLE business.replenishment_plans ADD FOREIGN
 KEY(organization_id,shop_id,task_id,p3_observation_id)
 REFERENCES business.p3_observations(organization_id,shop_id,task_id,id);
CREATE TABLE business.p3_revalidation_transitions (
 decision_id uuid PRIMARY KEY,organization_id uuid NOT NULL,shop_id uuid NOT NULL,
 task_id uuid
 NOT NULL,
 old_plan_id uuid NOT NULL,old_approval_id uuid NOT NULL,old_plan_version integer NOT
 NULL,
 old_plan_hash text NOT NULL,observation_id uuid NOT NULL,
 next_plan_id uuid NOT NULL UNIQUE,next_approval_id uuid NOT NULL UNIQUE,
 next_plan_version integer NOT NULL,cause_job_id uuid NOT NULL REFERENCES
 business.jobs(id),
 transition_hash text NOT NULL CHECK(transition_hash ~ '^[a-f0-9]{64}$'),
 applied_checkpoint_id text,applied_at timestamptz,
 CHECK((applied_at IS NULL)=(applied_checkpoint_id IS NULL)),
 CHECK(next_plan_version=old_plan_version+1),
 FOREIGN KEY(organization_id,shop_id,task_id,old_approval_id,decision_id)
 REFERENCES business.approvals(organization_id,shop_id,task_id,id,decision_id),
 FOREIGN KEY(organization_id,shop_id,task_id,old_plan_id,old_plan_version)
 REFERENCES business.replenishment_plans(organization_id,shop_id,task_id,id,version),
 FOREIGN KEY(organization_id,shop_id,task_id,next_plan_id,next_plan_version)
 REFERENCES business.replenishment_plans(organization_id,shop_id,task_id,id,version),
 FOREIGN KEY(organization_id,shop_id,task_id,next_approval_id)
 REFERENCES business.approvals(organization_id,shop_id,task_id,id),
 FOREIGN KEY(organization_id,shop_id,task_id,observation_id)
 REFERENCES business.p3_observations(organization_id,shop_id,task_id,id)
);
CREATE TABLE business.p3_revalidation_failures (
 decision_id uuid PRIMARY KEY,organization_id uuid NOT NULL,shop_id uuid NOT NULL,
 task_id uuid NOT NULL,
 approval_id uuid NOT NULL,plan_id uuid NOT NULL,observation_id uuid,
 reason_code text NOT NULL CHECK(length(reason_code) BETWEEN 1 AND 100),
 occurred_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 FOREIGN KEY(organization_id,shop_id,task_id,approval_id,decision_id)
 REFERENCES business.approvals(organization_id,shop_id,task_id,id,decision_id),
 FOREIGN KEY(organization_id,shop_id,task_id,plan_id)
 REFERENCES business.replenishment_plans(organization_id,shop_id,task_id,id),
 FOREIGN KEY(organization_id,shop_id,task_id,observation_id)
 REFERENCES business.p3_observations(organization_id,shop_id,task_id,id)
);
CREATE TABLE business.executions (
 id uuid PRIMARY KEY,organization_id uuid NOT NULL,shop_id uuid NOT NULL,task_id uuid
 NOT NULL
 UNIQUE,
 plan_id uuid NOT NULL UNIQUE,approval_id uuid NOT NULL UNIQUE,
 operation_key text NOT NULL UNIQUE,request_hash text NOT NULL CHECK(request_hash ~
 '^[a-f0-9]{64}$'),
 revalidation_snapshot_id uuid NOT NULL,actor_id uuid NOT NULL,identity_id uuid NOT
 NULL,
 auth_version bigint NOT NULL,plan_version integer NOT NULL,plan_hash text NOT NULL,
 freshness_seconds integer NOT NULL CHECK(freshness_seconds BETWEEN 1 AND 3600),
 status text NOT NULL CHECK(status IN ('building','completed')),
 item_ids uuid[] NOT NULL DEFAULT '{}',started_at timestamptz NOT NULL,
 completed_at timestamptz,error_code text CHECK(error_code IS NULL),
 CHECK((status='completed')=(completed_at IS NOT NULL)),
 UNIQUE(organization_id,shop_id,task_id,id),
 FOREIGN KEY(organization_id,shop_id,task_id,plan_id)
 REFERENCES business.replenishment_plans(organization_id,shop_id,task_id,id),
 FOREIGN KEY(organization_id,shop_id,task_id,approval_id)
 REFERENCES business.approvals(organization_id,shop_id,task_id,id),
 FOREIGN KEY(organization_id,shop_id,task_id,revalidation_snapshot_id)
 REFERENCES business.p3_observations(organization_id,shop_id,task_id,id),
 FOREIGN KEY(organization_id,identity_id,actor_id)
 REFERENCES business.identities(organization_id,id,principal_id)
);
CREATE TABLE business.replenishment_items (
 id uuid PRIMARY KEY,organization_id uuid NOT NULL,shop_id uuid NOT NULL,task_id uuid
 NOT NULL,
 execution_id uuid NOT NULL,sku_key text NOT NULL CHECK(length(sku_key) BETWEEN 1 AND
 256),
 stock_pool_key text NOT NULL CHECK(length(stock_pool_key) BETWEEN 1 AND 256),
 quantity numeric NOT NULL CHECK(quantity>0 AND quantity=trunc(quantity)),
 status text NOT NULL CHECK(status IN ('open','completed','closed')),version integer
 NOT NULL
 DEFAULT 1,
 source_snapshot_id uuid NOT NULL,approved_plan_id uuid NOT NULL,approved_by uuid NOT
 NULL,
 created_at timestamptz NOT NULL,updated_at timestamptz NOT NULL,
 resolution_id uuid UNIQUE,resolved_by uuid,resolved_identity_id uuid,
 resolved_auth_version bigint,
 resolved_at timestamptz,resolution_reason text,resolution_request_key
 uuid,resolution_payload_hash text,
 CHECK((status='open' AND version=1 AND resolution_id IS NULL AND resolved_by IS NULL
 AND resolved_identity_id IS NULL AND resolved_auth_version IS NULL AND resolved_at
 IS NULL
 AND resolution_reason IS NULL AND resolution_request_key IS NULL AND
 resolution_payload_hash
 IS NULL)
 OR (status<>'open' AND version=2 AND resolution_id IS NOT NULL AND resolved_by IS
 NOT NULL
 AND resolved_identity_id IS NOT NULL AND resolved_auth_version>0 AND resolved_at IS
 NOT NULL
 AND length(btrim(resolution_reason)) BETWEEN 1 AND 1000 AND
 resolution_reason=btrim(resolution_reason)
 AND resolution_request_key IS NOT NULL AND resolution_payload_hash ~
 '^[a-f0-9]{64}$')),
 UNIQUE(execution_id,sku_key),
 FOREIGN KEY(organization_id,shop_id,task_id,execution_id)
 REFERENCES business.executions(organization_id,shop_id,task_id,id),
 FOREIGN KEY(organization_id,shop_id,task_id,source_snapshot_id)
 REFERENCES business.p3_observations(organization_id,shop_id,task_id,id),
 FOREIGN KEY(organization_id,shop_id,task_id,approved_plan_id)
 REFERENCES business.replenishment_plans(organization_id,shop_id,task_id,id),
 FOREIGN KEY(organization_id,approved_by) REFERENCES
 business.principals(organization_id,id),
 FOREIGN KEY(organization_id,resolved_identity_id,resolved_by)
 REFERENCES business.identities(organization_id,id,principal_id)
);
CREATE UNIQUE INDEX p3_one_open_pool ON business.replenishment_items(shop_id,
 stock_pool_key)
 WHERE status='open';
ALTER TABLE business.outbox ADD COLUMN source_mode text NOT NULL DEFAULT 'mock'
 CHECK(source_mode IN ('mock','controlled_stub'));
ALTER TABLE business.outbox ADD CONSTRAINT p3_sender_disabled_receipt
 CHECK(NOT sender_enabled AND external_id IS NULL AND status NOT IN ('sent','sending'));
CREATE TABLE business.outbox_reconciliations (
 outbox_id uuid NOT NULL REFERENCES business.outbox(id),observed_version integer NOT
 NULL,
 outcome text NOT NULL CHECK(outcome IN ('missing','stale','unknown_held')),
 source_mode text NOT NULL CHECK(source_mode='controlled_stub'),
 occurred_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(outbox_id,observed_version,outcome)
);
ALTER TABLE business.approvals DROP CONSTRAINT a02_no_t4_consumption;"""


def upgrade() -> None:
    op.execute("""CREATE FUNCTION business.p3_report_facts(r jsonb) RETURNS jsonb
 LANGUAGE sql IMMUTABLE STRICT AS $$ SELECT
 (r-'facts_hash')||jsonb_build_object('items',
 COALESCE((SELECT jsonb_agg(x-'display' ORDER BY ord)
 FROM jsonb_array_elements(r->'items') WITH ORDINALITY e(x,ord)),'[]'::jsonb)) $$""")
    # FK替换只作用P3 plan的原两组来源；保留原P2表、内容和初始task_source。
    op.execute("""DO $$ DECLARE c record; BEGIN
 FOR c IN SELECT conname FROM pg_constraint WHERE
 conrelid='business.replenishment_plans'::regclass
 AND confrelid IN ('business.analysis_reports'::regclass,
 'business.commerce_snapshots'::regclass)
 LOOP EXECUTE format('ALTER TABLE business.replenishment_plans DROP CONSTRAINT %I',
 c.conname);
 END LOOP; END $$""")
    for statement in DDL.split(";"):
        if statement.strip():
            op.execute(statement)
    op.execute("""CREATE FUNCTION business.p3_observation_lineage() RETURNS trigger
 LANGUAGE plpgsql AS $$ BEGIN
 IF NOT EXISTS(SELECT 1 FROM business.p3_task_sources b WHERE b.task_id=NEW.task_id
 AND b.organization_id=NEW.organization_id AND b.shop_id=NEW.shop_id
 AND b.source_task_id=NEW.source_task_id AND b.source_report_id=NEW.original_report_id
 AND b.snapshot_id=NEW.original_snapshot_id AND b.facts_hash=NEW.original_facts_hash
 AND b.parameters=NEW.parameters)
 OR NOT EXISTS(SELECT 1 FROM business.shops s WHERE s.id=NEW.shop_id
 AND s.organization_id=NEW.organization_id AND s.environment IN ('test','mock')
 AND s.adapter_kind='mock' AND NEW.input->'source'->>'shop_id'=s.external_shop_key
 AND NEW.input->'source'->>'currency'=s.currency
 AND NEW.input->'source'->>'timezone'=s.timezone
 AND NEW.input->'source'->'provenance'->>'source_kind'='mock')
 OR NEW.report->'source' IS DISTINCT FROM NEW.input->'source'
 OR (NEW.report->'L',NEW.report->'R',NEW.report->'S') IS DISTINCT FROM
 (NEW.parameters->'L',NEW.parameters->'R',NEW.parameters->'S')
 OR EXISTS(SELECT 1 FROM business.analysis_reports r WHERE r.id IN (NEW.report_id,
 NEW.id))
 OR EXISTS(SELECT 1 FROM business.commerce_snapshots s WHERE s.id IN (NEW.report_id,
 NEW.id))
 OR EXISTS(SELECT 1 FROM business.p3_observations o
 WHERE o.id=NEW.report_id OR o.report_id=NEW.id) THEN
 RAISE EXCEPTION 'P3 observation lineage or identity mismatch' USING ERRCODE='23514';
 END IF;
 RETURN NEW; END $$""")
    op.execute("""CREATE TRIGGER p3_observation_lineage BEFORE INSERT ON business.p3_observations
 FOR EACH ROW EXECUTE FUNCTION business.p3_observation_lineage()""")
    for table in ("p3_observations", "outbox_reconciliations", "p3_revalidation_failures"):
        op.execute(f"""CREATE TRIGGER p3_no_mutation BEFORE UPDATE OR DELETE ON business.{table}
 FOR EACH ROW EXECUTE FUNCTION business.reject_inventory_mutation()""")
        op.execute(f"""CREATE TRIGGER p3_no_truncate BEFORE TRUNCATE ON business.{table}
 FOR EACH STATEMENT EXECUTE FUNCTION business.reject_inventory_mutation()""")
    op.execute("""CREATE FUNCTION business.p3_projection_identity() RETURNS trigger
 LANGUAGE plpgsql AS $$ BEGIN
 IF (NEW.id,NEW.organization_id,NEW.shop_id,NEW.task_id,NEW.destination,
 NEW.aggregate_id,NEW.aggregate_version,NEW.operation,NEW.dedupe_key,NEW.request_hash,
 NEW.payload,NEW.provider_idempotency_key,NEW.created_at)
 IS DISTINCT FROM (OLD.id,OLD.organization_id,OLD.shop_id,OLD.task_id,OLD.destination,
 OLD.aggregate_id,OLD.aggregate_version,OLD.operation,OLD.dedupe_key,OLD.request_hash,
 OLD.payload,OLD.provider_idempotency_key,OLD.created_at)
 OR (OLD.source_mode='controlled_stub' AND NEW.source_mode<>'controlled_stub')
 OR NEW.attempts<OLD.attempts OR NEW.attempts<0
 OR (OLD.status='unknown' AND NEW.status NOT IN ('unknown','dead')) THEN
 RAISE EXCEPTION 'P3 projection identity or unknown receipt is immutable'
 USING ERRCODE='23514'; END IF; RETURN NEW; END $$""")
    op.execute("""CREATE TRIGGER p3_projection_identity BEFORE UPDATE ON business.outbox
 FOR EACH ROW EXECUTE FUNCTION business.p3_projection_identity()""")
    op.execute("""CREATE TRIGGER p3_no_delete BEFORE DELETE ON business.outbox
 FOR EACH ROW EXECUTE FUNCTION business.reject_inventory_mutation()""")
    op.execute("""CREATE TRIGGER p3_no_truncate BEFORE TRUNCATE ON business.outbox
 FOR EACH STATEMENT EXECUTE FUNCTION business.reject_inventory_mutation()""")
    op.execute("""CREATE FUNCTION business.p3_plan_evidence() RETURNS trigger LANGUAGE plpgsql AS $$
 BEGIN
 IF TG_OP='INSERT' AND NEW.evidence_kind='p2_original' AND NEW.p2_report_id IS NULL
 AND NEW.p2_snapshot_id IS NULL AND NEW.p3_observation_id IS NULL THEN
 NEW.p2_report_id:=NEW.report_id; NEW.p2_snapshot_id:=NEW.snapshot_id; END IF;
 IF TG_OP='UPDATE' AND OLD.status<>'current' AND NEW.status<>OLD.status THEN
 RAISE EXCEPTION 'P3 plan terminal status is immutable' USING ERRCODE='23514'; END IF;
 IF TG_OP='UPDATE' AND (NEW.evidence_kind,NEW.p2_report_id,NEW.p2_snapshot_id,
 NEW.p3_observation_id)
 IS DISTINCT FROM (OLD.evidence_kind,OLD.p2_report_id,OLD.p2_snapshot_id,
 OLD.p3_observation_id) THEN
 RAISE EXCEPTION 'P3 evidence discriminator is immutable' USING ERRCODE='23514'; END IF;
 IF NOT EXISTS(SELECT 1 FROM business.p3_task_sources b WHERE b.task_id=NEW.task_id
 AND b.organization_id=NEW.organization_id AND b.shop_id=NEW.shop_id
 AND b.source_task_id=NEW.source_task_id AND (
 (NEW.evidence_kind='p2_original' AND NEW.report_id=b.source_report_id
 AND NEW.snapshot_id=b.snapshot_id AND NEW.facts_hash=b.facts_hash
 AND NEW.p2_report_id=NEW.report_id AND NEW.p2_snapshot_id=NEW.snapshot_id) OR
 (NEW.evidence_kind='p3_observation' AND EXISTS(SELECT 1 FROM business.p3_observations o
 WHERE o.id=NEW.p3_observation_id AND o.organization_id=NEW.organization_id AND
 o.shop_id=NEW.shop_id
 AND o.task_id=NEW.task_id AND o.source_task_id=NEW.source_task_id AND
 o.report_id=NEW.report_id
 AND o.id=NEW.snapshot_id AND o.facts_hash=NEW.facts_hash AND
 o.generation_plan_id=NEW.id
 AND o.generation_plan_version=NEW.version))))
 OR (NEW.content->'source'->>'source_task_id',NEW.content->'source'->>'report_id',
 NEW.content->'source'->>'snapshot_id',NEW.content->'source'->>'facts_hash') IS
 DISTINCT FROM
 (NEW.source_task_id::text,NEW.report_id::text,NEW.snapshot_id::text,NEW.facts_hash)
 THEN
 RAISE EXCEPTION 'P3 plan source must be its exact typed evidence' USING
 ERRCODE='23514'; END IF;
 RETURN NEW; END $$""")
    op.execute("""CREATE TRIGGER p3_plan_evidence BEFORE INSERT OR UPDATE ON
 business.replenishment_plans
 FOR EACH ROW EXECUTE FUNCTION business.p3_plan_evidence()""")
    op.execute("""CREATE FUNCTION business.p3_transition_binding() RETURNS trigger LANGUAGE
 plpgsql AS $$
 BEGIN
 IF TG_OP='UPDATE' AND (to_jsonb(NEW)-'applied_at'-'applied_checkpoint_id') IS
 DISTINCT FROM
 (to_jsonb(OLD)-'applied_at'-'applied_checkpoint_id') OR
 (TG_OP='UPDATE' AND OLD.applied_at IS NOT NULL AND NEW IS DISTINCT FROM OLD) THEN
 RAISE EXCEPTION 'P3 replacement is immutable' USING ERRCODE='23514'; END IF;
 IF NOT EXISTS(SELECT 1 FROM business.approvals a
 JOIN business.replenishment_plans p ON p.id=a.plan_id
 JOIN business.approval_resumes r ON r.decision_id=a.decision_id
 JOIN business.replenishment_plans n ON n.id=NEW.next_plan_id
 JOIN business.approvals na ON na.plan_id=n.id AND na.id=NEW.next_approval_id
 WHERE a.id=NEW.old_approval_id AND a.plan_id=NEW.old_plan_id AND
 a.plan_version=NEW.old_plan_version
 AND a.plan_hash=NEW.old_plan_hash AND a.decision_id=NEW.decision_id AND
 a.status='approved'
 AND a.consumed_at IS NULL AND p.status='superseded'
 AND a.organization_id=NEW.organization_id AND a.shop_id=NEW.shop_id AND
 a.task_id=NEW.task_id
 AND n.task_id=a.task_id AND n.organization_id=a.organization_id AND n.shop_id=a.shop_id
 AND n.version=a.plan_version+1 AND n.evidence_kind='p3_observation'
 AND n.p3_observation_id=NEW.observation_id AND NEW.cause_job_id IN
 (r.job_id,r.continuation_job_id)) THEN
 RAISE EXCEPTION 'P3 replacement decision/version/job binding mismatch' USING
 ERRCODE='23514';
 END IF;
 RETURN NEW; END $$""")
    op.execute("""CREATE TRIGGER p3_transition_binding BEFORE INSERT OR UPDATE
 ON business.p3_revalidation_transitions FOR EACH ROW EXECUTE FUNCTION
 business.p3_transition_binding()""")
    # 永久执行/consumed/task完成及items终态约束在同一个后续函数组安装。
    install_execution_constraints()


def install_execution_constraints() -> None:
    op.execute("""CREATE FUNCTION business.valid_p3_execution(ref uuid) RETURNS boolean
 LANGUAGE sql STABLE AS $$ SELECT EXISTS(
 SELECT 1 FROM business.executions e JOIN business.replenishment_plans p ON
 p.id=e.plan_id
 JOIN business.approvals a ON a.id=e.approval_id AND a.plan_id=p.id
 JOIN business.p3_observations o ON o.id=e.revalidation_snapshot_id
 WHERE e.id=ref AND e.status='completed' AND e.completed_at IS NOT NULL
 AND p.organization_id=e.organization_id AND p.shop_id=e.shop_id AND p.task_id=e.task_id
 AND a.organization_id=e.organization_id AND a.shop_id=e.shop_id AND a.task_id=e.task_id
 AND a.status='approved' AND a.decided_by=e.actor_id AND
 a.decided_identity_id=e.identity_id
 AND (a.decided_auth_version)=(e.auth_version) AND p.version=e.plan_version AND
 p.plan_hash=e.plan_hash
 AND a.plan_version=p.version AND a.plan_hash=p.plan_hash AND p.status IN ('current',
 'executed')
 AND e.operation_key='restock:'||e.shop_id::text||':'||p.id::text||':'||p.version::text
 AND o.task_id=e.task_id AND o.organization_id=e.organization_id AND o.shop_id=e.shop_id
 AND o.generation_plan_id=p.id AND o.generation_plan_version=p.version
 AND e.completed_at<a.expires_at AND e.completed_at>=o.collected_at
 AND e.completed_at-o.collected_at<=e.freshness_seconds*interval '1 second'
 AND jsonb_array_length(p.content->'items') BETWEEN 1 AND 20
 AND cardinality(e.item_ids)=jsonb_array_length(p.content->'items')
 AND e.item_ids=(SELECT array_agg(i.id ORDER BY i.id) FROM
 business.replenishment_items i
 WHERE i.execution_id=e.id)
 AND NOT EXISTS(SELECT 1 FROM jsonb_array_elements(p.content->'items') x WHERE NOT
 EXISTS(
 SELECT 1 FROM business.replenishment_items i WHERE i.execution_id=e.id
 AND i.organization_id=e.organization_id AND i.shop_id=e.shop_id AND i.task_id=e.task_id
 AND i.sku_key=x->>'sku_key' AND i.stock_pool_key=x->>'stock_pool_key'
 AND i.quantity=(x->>'quantity')::numeric AND i.approved_plan_id=p.id
 AND i.approved_by=a.decided_by AND i.source_snapshot_id=o.id))
 ) $$""")
    op.execute("""CREATE FUNCTION business.p3_execution_guard() RETURNS trigger LANGUAGE
 plpgsql AS $$
 BEGIN
 IF TG_OP='INSERT' AND NEW.status<>'building' THEN
 RAISE EXCEPTION 'P3 execution must begin as transactional building' USING
 ERRCODE='23514'; END IF;
 IF TG_OP='UPDATE' AND ((OLD.status='completed' AND NEW IS DISTINCT FROM OLD)
 OR (to_jsonb(NEW)-'status'-'completed_at'-'item_ids') IS DISTINCT FROM
 (to_jsonb(OLD)-'status'-'completed_at'-'item_ids')) THEN
 RAISE EXCEPTION 'P3 execution receipt is permanent' USING ERRCODE='23514'; END IF;
 RETURN NEW; END $$""")
    op.execute("""CREATE TRIGGER p3_execution_guard BEFORE INSERT OR UPDATE ON business.executions
 FOR EACH ROW EXECUTE FUNCTION business.p3_execution_guard()""")
    op.execute("""CREATE FUNCTION business.p3_execution_seal() RETURNS trigger LANGUAGE plpgsql
 AS $$
 BEGIN
 IF NEW.status='completed' AND (OLD.status<>'completed' OR TG_OP='INSERT') THEN
 IF NOT business.valid_p3_execution(NEW.id) OR NOT business.lock_p3_permission(
 NEW.actor_id,NEW.organization_id,NEW.shop_id,NEW.identity_id,NEW.auth_version,
 'approver') THEN
 RAISE EXCEPTION 'P3 execution seal requires all items and current authority' USING
 ERRCODE='23514';
 END IF; END IF; RETURN NEW; END $$""")
    op.execute("""CREATE TRIGGER p3_execution_seal AFTER UPDATE ON business.executions
 FOR EACH ROW EXECUTE FUNCTION business.p3_execution_seal()""")
    op.execute("""CREATE FUNCTION business.p3_consumption_guard() RETURNS trigger LANGUAGE
 plpgsql AS $$
 BEGIN
 IF OLD.consumed_at IS NOT NULL AND NEW.consumed_at IS DISTINCT FROM OLD.consumed_at
 THEN
 RAISE EXCEPTION 'P3 consumed approval is immutable' USING ERRCODE='23514'; END IF;
 IF OLD.consumed_at IS NULL AND NEW.consumed_at IS NOT NULL AND NOT EXISTS(
 SELECT 1 FROM business.executions e WHERE e.approval_id=NEW.id AND
 e.plan_id=NEW.plan_id
 AND e.task_id=NEW.task_id AND e.organization_id=NEW.organization_id AND
 e.shop_id=NEW.shop_id
 AND e.completed_at=NEW.consumed_at AND business.valid_p3_execution(e.id)) THEN
 RAISE EXCEPTION 'P3 consume requires permanent all-plan execution' USING
 ERRCODE='23514'; END IF;
 RETURN NEW; END $$""")
    op.execute("""CREATE TRIGGER p3_consumption_guard BEFORE UPDATE ON business.approvals
 FOR EACH ROW EXECUTE FUNCTION business.p3_consumption_guard()""")
    op.execute("""CREATE OR REPLACE FUNCTION business.preserve_p3_task() RETURNS trigger
 LANGUAGE plpgsql AS $$ BEGIN
 IF TG_OP='INSERT' THEN
 IF NEW.kind='inventory_replenishment' AND
 (NEW.workflow_version<>'p3-inventory-replenishment-v1' OR NEW.state<>'queued') THEN
 RAISE EXCEPTION 'P3 must begin queued at pinned workflow' USING ERRCODE='23514'; END
 IF;
 RETURN NEW; END IF;
 IF OLD.kind='inventory_replenishment' OR NEW.kind='inventory_replenishment' THEN
 IF (NEW.kind,NEW.normalized_request) IS DISTINCT FROM (OLD.kind,OLD.normalized_request)
 OR (OLD.state IN ('completed','rejected','expired') AND NEW.state<>OLD.state) THEN
 RAISE EXCEPTION 'P3 identity or terminal state is immutable' USING ERRCODE='23514';
 END IF;
 IF NEW.state='completed' AND OLD.state<>'completed' AND NOT (
 (NEW.active_plan_id IS NULL AND EXISTS(
 SELECT 1 FROM business.p3_task_sources b JOIN business.analysis_reports r
 ON r.id=b.source_report_id AND r.task_id=b.source_task_id AND
 r.snapshot_id=b.snapshot_id
 AND r.facts_hash=b.facts_hash AND r.organization_id=b.organization_id AND
 r.shop_id=b.shop_id
 JOIN business.business_tasks s ON s.id=b.source_task_id AND s.state='completed'
 WHERE b.task_id=NEW.id AND b.organization_id=NEW.organization_id AND
 b.shop_id=NEW.shop_id
 AND r.report->'candidate_count'='0'::jsonb AND r.report->'complete'='true'::jsonb
 AND r.report->'source_complete'='true'::jsonb AND
 r.report->'requires_review'='false'::jsonb)) OR
 (NEW.active_plan_id IS NOT NULL AND EXISTS(SELECT 1 FROM business.executions e
 JOIN business.approvals a ON a.id=e.approval_id
 JOIN business.replenishment_plans p ON p.id=e.plan_id AND p.status='executed'
 WHERE e.task_id=NEW.id AND e.organization_id=NEW.organization_id AND
 e.shop_id=NEW.shop_id
 AND e.plan_id=NEW.active_plan_id AND a.consumed_at=e.completed_at
 AND business.valid_p3_execution(e.id)))) THEN
 RAISE EXCEPTION 'P3 completion requires no-action or permanent execution' USING
 ERRCODE='23514';
 END IF; END IF; RETURN NEW; END $$""")
    op.execute("""CREATE FUNCTION business.p3_execution_committed() RETURNS trigger LANGUAGE
 plpgsql AS $$
 DECLARE e business.executions; BEGIN
 SELECT * INTO e FROM business.executions WHERE id=NEW.id;
 IF NOT business.valid_p3_execution(e.id) OR NOT EXISTS(
 SELECT 1 FROM business.business_tasks t JOIN business.approvals a ON a.id=e.approval_id
 JOIN business.replenishment_plans p ON p.id=e.plan_id AND p.status='executed'
 WHERE t.id=e.task_id AND t.state='completed' AND t.active_plan_id=e.plan_id
 AND a.consumed_at=e.completed_at AND clock_timestamp()<a.expires_at
 AND clock_timestamp()-(SELECT collected_at FROM business.p3_observations
 WHERE id=e.revalidation_snapshot_id)<=e.freshness_seconds*interval '1 second') OR
 NOT EXISTS(
 SELECT 1 FROM business.audit_events a WHERE a.task_id=e.task_id AND
 a.actor_id=e.actor_id
 AND a.action='execution_committed' AND a.entity_type='execution' AND
 a.entity_id=e.id::text)
 OR EXISTS(SELECT 1 FROM business.replenishment_items i WHERE i.execution_id=e.id AND
 NOT EXISTS(
 SELECT 1 FROM business.outbox o WHERE o.task_id=i.task_id AND o.aggregate_id=i.id
 AND o.aggregate_version=1 AND o.operation='item_projection' AND NOT
 o.sender_enabled)) THEN
 RAISE EXCEPTION
 'P3 T4 must commit execution/items/consume/task/audit/outbox atomically'
 USING ERRCODE='23514'; END IF; RETURN NULL; END $$""")
    op.execute("""CREATE CONSTRAINT TRIGGER p3_execution_committed AFTER INSERT OR UPDATE
 ON business.executions DEFERRABLE INITIALLY DEFERRED FOR EACH ROW
 EXECUTE FUNCTION business.p3_execution_committed()""")
    op.execute("""CREATE FUNCTION business.p3_item_guard() RETURNS trigger LANGUAGE plpgsql AS $$
 BEGIN
 IF TG_OP='INSERT' THEN
 IF NEW.status<>'open' OR NOT EXISTS(SELECT 1 FROM business.executions e
 JOIN business.replenishment_plans p ON p.id=e.plan_id
 JOIN business.approvals a ON a.id=e.approval_id
 CROSS JOIN LATERAL jsonb_array_elements(p.content->'items') x
 WHERE e.id=NEW.execution_id AND e.status='building' AND e.task_id=NEW.task_id
 AND e.organization_id=NEW.organization_id AND e.shop_id=NEW.shop_id
 AND e.revalidation_snapshot_id=NEW.source_snapshot_id AND
 e.plan_id=NEW.approved_plan_id
 AND a.decided_by=NEW.approved_by AND x->>'sku_key'=NEW.sku_key
 AND (x->>'stock_pool_key')=(NEW.stock_pool_key) AND
 (x->>'quantity')::numeric=NEW.quantity) THEN
 RAISE EXCEPTION 'P3 item requires its exact transactional execution plan' USING
 ERRCODE='23514';
 END IF; RETURN NEW; END IF;
 IF (NEW.id,NEW.organization_id,NEW.shop_id,NEW.task_id,NEW.execution_id,NEW.sku_key,
 NEW.stock_pool_key,NEW.quantity,NEW.source_snapshot_id,NEW.approved_plan_id,
 NEW.approved_by,
 NEW.created_at) IS DISTINCT FROM (OLD.id,OLD.organization_id,OLD.shop_id,OLD.task_id,
 OLD.execution_id,OLD.sku_key,OLD.stock_pool_key,OLD.quantity,OLD.source_snapshot_id,
 OLD.approved_plan_id,OLD.approved_by,OLD.created_at) OR
 (OLD.status<>'open' AND NEW IS DISTINCT FROM OLD) OR
 (NEW IS DISTINCT FROM OLD AND NOT (OLD.status='open' AND NEW.status IN ('completed',
 'closed')
 AND NEW.version=OLD.version+1 AND NEW.resolved_at=NEW.updated_at)) THEN
 RAISE EXCEPTION 'P3 item immutable identity or terminal state' USING
 ERRCODE='23514'; END IF;
 IF NEW.status<>OLD.status AND NOT business.lock_p3_permission(NEW.resolved_by,
 NEW.organization_id,NEW.shop_id,NEW.resolved_identity_id,NEW.resolved_auth_version,
 'approver') THEN
 RAISE EXCEPTION 'P3 item resolution requires current same-shop approver' USING
 ERRCODE='23514';
 END IF; RETURN NEW; END $$""")
    op.execute("""CREATE TRIGGER p3_item_guard BEFORE INSERT OR UPDATE ON
 business.replenishment_items
 FOR EACH ROW EXECUTE FUNCTION business.p3_item_guard()""")
    op.execute("""CREATE FUNCTION business.p3_item_resolution_committed() RETURNS trigger
 LANGUAGE plpgsql AS $$ DECLARE i business.replenishment_items; BEGIN
 SELECT * INTO i FROM business.replenishment_items WHERE id=NEW.id;
 IF i.status<>'open' AND (NOT EXISTS(SELECT 1 FROM business.web_requests w
 WHERE w.principal_id=i.resolved_by AND w.operation='resolve'
 AND (w.request_key)=(i.resolution_request_key)
 AND (w.request_hash)=(i.resolution_payload_hash)
 AND w.task_id=i.task_id AND w.result->'item'->>'item_id'=i.id::text
 AND w.result->'item'->>'state'=i.status
 AND w.result->'resolution'->>'resolution_id'=i.resolution_id::text)
 OR NOT EXISTS(SELECT 1 FROM business.audit_events a WHERE a.task_id=i.task_id
 AND a.actor_id=i.resolved_by AND a.entity_id=i.id::text AND a.action='item_'||i.status)
 OR NOT EXISTS(SELECT 1 FROM business.outbox o WHERE o.task_id=i.task_id
 AND o.aggregate_id=i.id AND o.aggregate_version=i.version AND
 o.operation='item_projection'
 AND NOT o.sender_enabled)) THEN
 RAISE EXCEPTION 'P3 T6 must commit item/receipt/audit/outbox atomically' USING
 ERRCODE='23514';
 END IF; RETURN NULL; END $$""")
    op.execute("""CREATE CONSTRAINT TRIGGER p3_item_resolution_committed AFTER UPDATE
 ON business.replenishment_items DEFERRABLE INITIALLY DEFERRED FOR EACH ROW
 EXECUTE FUNCTION business.p3_item_resolution_committed()""")
    for table in ("executions", "replenishment_items", "p3_revalidation_transitions"):
        op.execute(f"""CREATE TRIGGER p3_no_delete BEFORE DELETE ON business.{table}
 FOR EACH ROW EXECUTE FUNCTION business.reject_inventory_mutation()""")
        op.execute(f"""CREATE TRIGGER p3_no_truncate BEFORE TRUNCATE ON business.{table}
 FOR EACH STATEMENT EXECUTE FUNCTION business.reject_inventory_mutation()""")


def downgrade() -> None:
    raise RuntimeError("destructive downgrade disabled; restore a verified backup")
