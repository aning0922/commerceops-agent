"""M3同Worker调度、冻结追问与仅Fake投递；无旧约束放宽。"""

from alembic import op

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None

TABLES = r"""
CREATE TABLE business.p6_daily_destinations (
id uuid PRIMARY KEY,organization_id uuid NOT NULL,shop_id uuid NOT NULL,owner_id uuid
NOT NULL,
binding_version integer NOT NULL CHECK(binding_version>0),
transport text NOT NULL CHECK(transport='fake'),enabled boolean NOT NULL DEFAULT
false,
created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
UNIQUE(organization_id,shop_id,id),
FOREIGN KEY(organization_id,shop_id) REFERENCES business.shops(organization_id,id),
FOREIGN KEY(organization_id,owner_id) REFERENCES
business.principals(organization_id,id)
);
CREATE TABLE business.p6_daily_schedules (
id uuid PRIMARY KEY,schedule_id uuid NOT NULL,schedule_version integer NOT NULL
CHECK(schedule_version>0),
organization_id uuid NOT NULL,shop_id uuid NOT NULL,owner_id uuid NOT NULL,
canonical_config text NOT NULL,config jsonb NOT NULL,config_hash text NOT NULL,
enabled boolean NOT NULL,pause_reason text,last_created_day date,
created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
UNIQUE(schedule_id,schedule_version),UNIQUE(organization_id,shop_id,id),
FOREIGN KEY(organization_id,shop_id) REFERENCES business.shops(organization_id,id),
FOREIGN KEY(organization_id,owner_id) REFERENCES
business.principals(organization_id,id),
CHECK(business.p6_json_hash(canonical_config,config,config_hash)),
CHECK((config->>'schema_version'='p6-daily-schedule-v1'
AND config->>'schedule_id'=schedule_id::text
AND config->>'schedule_version'=schedule_version::text
AND config->>'organization_id'=organization_id::text AND
config->>'shop_id'=shop_id::text
AND config->>'owner_id'=owner_id::text) IS TRUE)
);
CREATE UNIQUE INDEX p6_one_active_schedule ON
business.p6_daily_schedules(schedule_id) WHERE enabled;
CREATE TABLE business.p6_daily_schedule_runs (
id uuid PRIMARY KEY,organization_id uuid NOT NULL,shop_id uuid NOT NULL,
schedule_row_id uuid NOT NULL,schedule_id uuid NOT NULL,schedule_version integer NOT
NULL,
business_day date NOT NULL,due_at timestamptz NOT NULL,task_id uuid NOT NULL UNIQUE,
missed_periods integer NOT NULL CHECK(missed_periods>=0),skipped_first_day
date,skipped_last_day date,
created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
UNIQUE(schedule_id,due_at),UNIQUE(organization_id,shop_id,id),
FOREIGN KEY(organization_id,shop_id,schedule_row_id)
REFERENCES business.p6_daily_schedules(organization_id,shop_id,id),
FOREIGN KEY(organization_id,shop_id,task_id)
REFERENCES business.business_tasks(organization_id,shop_id,id),
CHECK((missed_periods=0 AND skipped_first_day IS NULL AND skipped_last_day IS NULL)
OR (missed_periods>0 AND skipped_first_day IS NOT NULL AND skipped_last_day IS NOT
NULL
AND skipped_last_day-skipped_first_day+1=missed_periods AND
skipped_last_day<business_day))
);
CREATE TABLE business.p6_daily_questions (
task_id uuid PRIMARY KEY,organization_id uuid NOT NULL,shop_id uuid NOT NULL,
parent_task_id uuid NOT NULL,report_id uuid NOT NULL,snapshot_id uuid NOT NULL,
content_hash text NOT NULL,facts_hash text NOT NULL,
result jsonb NOT NULL,canonical_result text NOT NULL,result_hash text NOT NULL,
created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
FOREIGN KEY(organization_id,shop_id,task_id)
REFERENCES business.business_tasks(organization_id,shop_id,id),
FOREIGN KEY(organization_id,shop_id,parent_task_id,report_id)
REFERENCES business.p6_daily_reports(organization_id,shop_id,task_id,id),
CHECK(business.p6_json_hash(canonical_result,result,result_hash)),
CHECK((result#>>'{answer,schema_version}'='p6-daily-answer-v1'
AND result#>>'{answer,report_id}'=report_id::text
AND result#>>'{answer,snapshot_id}'=snapshot_id::text
AND result#>>'{answer,content_hash}'=content_hash AND
result#>>'{answer,facts_hash}'=facts_hash
AND result#>'{answer,model_requests_enabled}'='false'::jsonb
AND result#>'{answer,external_sender_enabled}'='false'::jsonb
AND jsonb_typeof(result->'citations')='array') IS TRUE)
);
CREATE TABLE business.p6_daily_deliveries (
id uuid PRIMARY KEY,organization_id uuid NOT NULL,shop_id uuid NOT NULL,task_id uuid
NOT NULL,
report_id uuid NOT NULL,destination_binding_id uuid NOT NULL,outbox_id uuid NOT NULL
UNIQUE
REFERENCES business.outbox(id),schedule_run_id uuid NOT NULL,
payload jsonb NOT NULL,canonical_payload text NOT NULL,payload_hash text NOT NULL,
provider_key uuid NOT NULL UNIQUE,status text NOT NULL DEFAULT 'pending'
CHECK(status IN ('pending','sending','sent','failed','unknown','disabled')),
attempts integer NOT NULL DEFAULT 0 CHECK(attempts BETWEEN 0 AND 1),
external_id text,failure_code text,claimed_by text,
created_at timestamptz NOT NULL DEFAULT clock_timestamp(),updated_at timestamptz NOT
NULL DEFAULT clock_timestamp(),
UNIQUE(report_id,destination_binding_id),
FOREIGN KEY(organization_id,shop_id,task_id,report_id)
REFERENCES business.p6_daily_reports(organization_id,shop_id,task_id,id),
FOREIGN KEY(organization_id,shop_id,destination_binding_id)
REFERENCES business.p6_daily_destinations(organization_id,shop_id,id),
FOREIGN KEY(organization_id,shop_id,schedule_run_id)
REFERENCES business.p6_daily_schedule_runs(organization_id,shop_id,id),
CHECK(business.p6_json_hash(canonical_payload,payload,payload_hash)),
CHECK((status='sent')=(external_id IS NOT NULL)),
CHECK((status IN ('sending','sent','unknown') AND attempts=1) OR
(status IN ('pending','failed','disabled') AND attempts IN (0,1)))
);
CREATE TABLE business.p6_daily_fake_receipts (
provider_key uuid PRIMARY KEY,destination_binding_id uuid NOT NULL
REFERENCES business.p6_daily_destinations(id),payload_hash text NOT NULL,
external_id text NOT NULL UNIQUE,created_at timestamptz NOT NULL DEFAULT
clock_timestamp(),
CHECK(payload_hash ~ '^[a-f0-9]{64}$')
);
CREATE UNIQUE INDEX p6_question_request_key ON business.business_tasks
(organization_id,requester_id,(normalized_request#>>'{input,request_key}')) WHERE
kind='daily_question';"""

FUNCTIONS = [
    """
CREATE FUNCTION business.p6_lock_daily_destination(target uuid,org uuid,shop uuid,actor uuid)
RETURNS boolean LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path=pg_catalog,business AS $$
BEGIN
 PERFORM 1 FROM business.p6_daily_schedule_runs r
 JOIN business.p6_daily_schedules s ON s.id=r.schedule_row_id
 AND s.organization_id=r.organization_id AND s.shop_id=r.shop_id
 JOIN business.business_tasks t ON t.id=r.task_id AND t.organization_id=r.organization_id
 AND t.shop_id=r.shop_id AND t.requester_id=s.owner_id
 JOIN business.p6_daily_destinations d ON d.id=(s.config->>'destination_binding_id')::uuid
 AND d.organization_id=s.organization_id AND d.shop_id=s.shop_id AND d.owner_id=s.owner_id
 WHERE t.id=target AND t.organization_id=org AND t.shop_id=shop AND t.requester_id=actor
 AND t.kind='daily_report' AND t.workflow_version='p6-daily-report-v1'
 AND t.normalized_request->'daily_source'=s.config->'daily_source'
 AND (t.normalized_request->>'requester_auth_version')::bigint=
 (s.config->>'owner_auth_version')::bigint
 AND s.enabled AND s.schedule_id=r.schedule_id AND s.schedule_version=r.schedule_version
 AND d.transport='fake'
 AND business.p6_current_permission(actor,org,shop,(s.config->>'owner_auth_version')::bigint)
 AND business.p6_source_valid(org,shop,
 (s.config#>>'{daily_source,source_binding_id}')::uuid,s.config->'daily_source')
 FOR SHARE OF d;
 RETURN FOUND;
END $$
""",
    """
CREATE FUNCTION business.p6_schedule_current(target uuid) RETURNS boolean
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,business AS $$
DECLARE s business.p6_daily_schedules; r business.p6_daily_schedule_runs;
BEGIN
 SELECT * INTO r FROM business.p6_daily_schedule_runs WHERE task_id=target;
 IF NOT FOUND THEN RETURN true; END IF;
 SELECT * INTO s FROM business.p6_daily_schedules WHERE id=r.schedule_row_id FOR SHARE;
 IF (s.enabled AND s.schedule_id=r.schedule_id AND s.schedule_version=r.schedule_version
 AND business.p6_current_permission(s.owner_id,s.organization_id,s.shop_id,
 (s.config->>'owner_auth_version')::bigint)
 AND business.p6_source_valid(s.organization_id,s.shop_id,
 (s.config#>>'{daily_source,source_binding_id}')::uuid,s.config->'daily_source')) IS NOT TRUE THEN
 RETURN false; END IF;
 IF s.config->'destination_binding_id'='null'::jsonb THEN RETURN true; END IF;
 RETURN business.p6_lock_daily_destination(target,s.organization_id,s.shop_id,s.owner_id);
END $$
""",
    """
CREATE FUNCTION business.p6_schedule_guard() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog,business AS $$
BEGIN
 IF TG_OP='DELETE' THEN RAISE EXCEPTION 'schedule audit retained' USING ERRCODE='23514'; END IF;
 IF (NEW.id,NEW.schedule_id,NEW.schedule_version,NEW.organization_id,NEW.shop_id,NEW.owner_id,
 NEW.config,NEW.canonical_config,NEW.config_hash,NEW.created_at) IS DISTINCT FROM
 (OLD.id,OLD.schedule_id,OLD.schedule_version,OLD.organization_id,OLD.shop_id,OLD.owner_id,
 OLD.config,OLD.canonical_config,OLD.config_hash,OLD.created_at) THEN
 RAISE EXCEPTION 'schedule version immutable' USING ERRCODE='23514'; END IF;
 IF (NOT OLD.enabled AND NEW.enabled) AND current_user<>(SELECT pg_get_userbyid(relowner)
 FROM pg_class WHERE oid='business.p6_daily_schedules'::regclass) THEN
 RAISE EXCEPTION 'schedule enable owner only' USING ERRCODE='23514'; END IF;
 IF NEW.last_created_day<OLD.last_created_day OR
 (OLD.last_created_day IS NOT NULL AND NEW.last_created_day IS NULL) THEN
 RAISE EXCEPTION 'schedule cursor monotonic' USING ERRCODE='23514'; END IF;
 IF NEW.last_created_day IS DISTINCT FROM OLD.last_created_day AND NOT EXISTS(
 SELECT 1 FROM business.p6_daily_schedule_runs r WHERE r.schedule_row_id=NEW.id
 AND r.business_day=NEW.last_created_day) THEN
 RAISE EXCEPTION 'schedule cursor requires run' USING ERRCODE='23514'; END IF;
 RETURN NEW;
END $$
""",
    """
CREATE FUNCTION business.p6_run_guard() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog,business AS $$
DECLARE s business.p6_daily_schedules; t business.business_tasks;
BEGIN
 SELECT * INTO s FROM business.p6_daily_schedules WHERE id=NEW.schedule_row_id FOR UPDATE;
 SELECT * INTO t FROM business.business_tasks WHERE id=NEW.task_id FOR SHARE;
 IF (s.enabled AND s.schedule_id=NEW.schedule_id AND s.schedule_version=NEW.schedule_version
 AND s.organization_id=NEW.organization_id AND s.shop_id=NEW.shop_id
 AND NEW.due_at=(((NEW.business_day+1)::timestamp AT TIME ZONE
 (s.config#>>'{daily_source,timezone}'))+make_interval(mins=>(s.config->>'delay_minutes')::int))
 AND NEW.due_at<clock_timestamp() AND NEW.due_at>=(s.config->>'first_due_at')::timestamptz
 AND (((NEW.business_day+2)::timestamp AT TIME ZONE (s.config#>>'{daily_source,timezone}'))
 +make_interval(mins=>(s.config->>'delay_minutes')::int))>clock_timestamp()
 AND t.organization_id=s.organization_id AND t.shop_id=s.shop_id AND t.requester_id=s.owner_id
 AND t.kind='daily_report' AND t.normalized_request->'daily_source'=s.config->'daily_source'
 AND t.normalized_request->'rules'=s.config->'rules'
 AND t.normalized_request->>'business_day'=NEW.business_day::text
 AND t.normalized_request->>'conversation_id'=s.config->>'conversation_id') IS NOT TRUE THEN
 RAISE EXCEPTION 'schedule run binding invalid' USING ERRCODE='23514'; END IF;
 RETURN NEW;
END $$
""",
    r"""
CREATE FUNCTION business.p6_question_guard() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog,business AS $$
DECLARE r jsonb; t business.business_tasks; p business.p6_daily_reports;
BEGIN
IF TG_TABLE_NAME='business_tasks' THEN
IF TG_OP='UPDATE' AND (OLD.kind='daily_question' OR NEW.kind='daily_question')
AND OLD.kind IS DISTINCT FROM NEW.kind THEN
RAISE EXCEPTION 'question kind immutable' USING ERRCODE='23514'; END IF;
IF NEW.kind<>'daily_question' THEN RETURN NEW; END IF;
r:=NEW.normalized_request;
IF NEW.workflow_version<>'p6-daily-question-v1' OR NOT business.p6_keys(r,
ARRAY['schema_version','parent_task_id','input','request_hash','requester_auth_version']) OR
NOT business.p6_keys(r->'input',ARRAY['schema_version','request_key','report_id','snapshot_id',
'content_hash','facts_hash','question']) OR NOT business.p6_keys(r#>'{input,question}',
ARRAY['kind','metric_key','finding_id']) OR
(r->>'schema_version'='p6-daily-question-task-v1' AND
jsonb_typeof(r->'input')='object'
AND r#>>'{input,schema_version}'='p6-daily-question-v1'
AND jsonb_typeof(r#>'{input,request_key}')='string'
AND r#>>'{input,content_hash}' ~ '^[a-f0-9]{64}$'
AND r#>>'{input,facts_hash}' ~ '^[a-f0-9]{64}$'
AND ((r#>>'{input,question,kind}' IN ('metric_definition','metric_evidence')
AND jsonb_typeof(r#>'{input,question,metric_key}')='string'
AND r#>'{input,question,finding_id}'='null'::jsonb)
OR (r#>>'{input,question,kind}'='finding_reason'
AND jsonb_typeof(r#>'{input,question,finding_id}')='string'
AND r#>'{input,question,metric_key}'='null'::jsonb)
OR (r#>>'{input,question,kind}'='data_quality'
AND r#>'{input,question,finding_id}'='null'::jsonb
AND r#>'{input,question,metric_key}'='null'::jsonb))
AND jsonb_typeof(r->'requester_auth_version')='number'
AND (r->>'requester_auth_version')::numeric>0
AND (r->>'requester_auth_version')::numeric=trunc((r->>'requester_auth_version')::numeric)
AND r->>'request_hash' ~ '^[a-f0-9]{64}$'
AND ((TG_OP='UPDATE' AND NEW.state IN ('failed','needs_attention')) OR
business.p6_current_permission(NEW.requester_id,NEW.organization_id,NEW.shop_id,
(r->>'requester_auth_version')::bigint))) IS NOT TRUE THEN
RAISE EXCEPTION 'question task invalid' USING ERRCODE='23514'; END IF;
PERFORM (r#>>'{input,request_key}')::uuid;
IF TG_OP='UPDATE' THEN
IF OLD.normalized_request IS DISTINCT FROM NEW.normalized_request THEN
RAISE EXCEPTION 'question request immutable' USING ERRCODE='23514'; END IF;
IF OLD.state='completed' AND NEW IS DISTINCT FROM OLD THEN
RAISE EXCEPTION 'question complete immutable' USING ERRCODE='23514'; END IF;
END IF;
SELECT * INTO p FROM business.p6_daily_reports WHERE
id=(r#>>'{input,report_id}')::uuid;
SELECT * INTO t FROM business.business_tasks WHERE id=p.task_id;
IF (p.organization_id=NEW.organization_id AND p.shop_id=NEW.shop_id
AND p.task_id=(r->>'parent_task_id')::uuid AND t.requester_id=NEW.requester_id
AND t.conversation_id=NEW.conversation_id
AND p.snapshot_id=(r#>>'{input,snapshot_id}')::uuid
AND p.facts_hash=r#>>'{input,facts_hash}' AND
p.report->>'content_hash'=r#>>'{input,content_hash}')
IS NOT TRUE THEN RAISE EXCEPTION 'question report invalid' USING ERRCODE='23514'; END
IF;
IF NEW.state='completed' AND NOT EXISTS(SELECT 1 FROM business.p6_daily_questions
WHERE task_id=NEW.id) THEN RAISE EXCEPTION 'question receipt missing' USING
ERRCODE='23514'; END IF;
ELSE
SELECT * INTO t FROM business.business_tasks WHERE id=NEW.task_id FOR UPDATE;
r:=t.normalized_request;
IF (t.kind='daily_question' AND t.organization_id=NEW.organization_id AND
t.shop_id=NEW.shop_id
AND t.state='analyzing' AND (r->>'parent_task_id')::uuid=NEW.parent_task_id
AND (r#>>'{input,report_id}')::uuid=NEW.report_id
AND (r#>>'{input,snapshot_id}')::uuid=NEW.snapshot_id
AND r#>>'{input,content_hash}'=NEW.content_hash AND
r#>>'{input,facts_hash}'=NEW.facts_hash
AND business.p6_current_permission(t.requester_id,t.organization_id,t.shop_id,
(r->>'requester_auth_version')::bigint)
AND EXISTS(SELECT 1 FROM business.jobs WHERE task_id=t.id AND status='running')) IS
NOT TRUE THEN
RAISE EXCEPTION 'question receipt invalid' USING ERRCODE='23514'; END IF;
END IF;
RETURN NEW;
END $$""",
    """
CREATE FUNCTION business.p6_schedule_snapshot_guard() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog,business AS $$ BEGIN
 IF NOT business.p6_schedule_current(NEW.task_id) THEN
 RAISE EXCEPTION 'schedule no longer current' USING ERRCODE='23514'; END IF;
 RETURN NEW;
END $$
""",
    r"""
CREATE FUNCTION business.p6_delivery_guard() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog,business AS $$ BEGIN
 IF TG_OP='INSERT' THEN
  IF NOT EXISTS(SELECT 1 FROM business.outbox o JOIN business.p6_daily_reports p
  ON p.id=NEW.report_id AND p.organization_id=NEW.organization_id AND p.shop_id=NEW.shop_id
  AND p.task_id=NEW.task_id AND p.complete
  JOIN business.p6_daily_schedule_runs r ON r.id=NEW.schedule_run_id AND r.task_id=p.task_id
  JOIN business.p6_daily_schedules s ON s.id=r.schedule_row_id
  WHERE o.id=NEW.outbox_id AND o.organization_id=NEW.organization_id AND o.shop_id=NEW.shop_id
  AND o.task_id=NEW.task_id AND o.aggregate_id=NEW.report_id AND o.aggregate_version=1
  AND o.destination='daily_fake' AND o.operation='daily_report_fake' AND o.status='blocked'
  AND NOT o.sender_enabled AND o.payload=NEW.payload AND o.request_hash=NEW.payload_hash
  AND o.provider_idempotency_key IS NOT DISTINCT FROM NEW.provider_key AND s.enabled
  AND (s.config->>'destination_binding_id')::uuid=NEW.destination_binding_id
  AND NEW.status IN ('pending','disabled') AND NEW.attempts=0
  AND NEW.payload->>'transport'='fake' AND NEW.payload->>'report_id'=NEW.report_id::text
  AND NEW.payload->>'facts_hash'=p.facts_hash
  AND NEW.payload->>'content_hash'=p.report->>'content_hash') THEN
   RAISE EXCEPTION 'delivery intent invalid' USING ERRCODE='23514'; END IF;
  RETURN NEW;
 END IF;
IF
(NEW.id,NEW.organization_id,NEW.shop_id,NEW.task_id,NEW.report_id,NEW.destination_binding_id,
NEW.outbox_id,NEW.schedule_run_id,NEW.payload,NEW.canonical_payload,NEW.payload_hash,NEW.provider_key,
NEW.created_at) IS DISTINCT FROM
(OLD.id,OLD.organization_id,OLD.shop_id,OLD.task_id,OLD.report_id,OLD.destination_binding_id,
OLD.outbox_id,OLD.schedule_run_id,OLD.payload,OLD.canonical_payload,OLD.payload_hash,OLD.provider_key,
OLD.created_at) OR NOT ((OLD.status='pending' AND NEW.status IN
('sending','disabled','failed')) OR
(OLD.status='sending' AND NEW.status IN ('sent','unknown')) OR NEW=OLD) THEN
RAISE EXCEPTION 'delivery transition invalid' USING ERRCODE='23514'; END IF;
RETURN NEW;
END $$""",
]


def upgrade() -> None:
    op.execute(TABLES)
    for statement in FUNCTIONS:
        op.execute(statement)
    for table in (
        "p6_daily_destinations",
        "p6_daily_schedules",
        "p6_daily_schedule_runs",
        "p6_daily_questions",
        "p6_daily_deliveries",
        "p6_daily_fake_receipts",
    ):
        op.execute(f"REVOKE ALL ON business.{table} FROM PUBLIC")
        op.execute(f"""CREATE TRIGGER p6_no_truncate BEFORE TRUNCATE ON business.{table}
        FOR EACH STATEMENT EXECUTE FUNCTION business.p6_reject_mutation()""")
        if table not in ("p6_daily_schedules", "p6_daily_deliveries"):
            op.execute(f"""CREATE TRIGGER p6_immutable BEFORE UPDATE OR DELETE ON business.{table}
            FOR EACH ROW EXECUTE FUNCTION business.p6_reject_mutation()""")
        elif table == "p6_daily_deliveries":
            op.execute(f"""CREATE TRIGGER p6_no_delete BEFORE DELETE ON business.{table}
            FOR EACH ROW EXECUTE FUNCTION business.p6_reject_mutation()""")
    op.execute("REVOKE ALL ON FUNCTION business.p6_schedule_current(uuid) FROM PUBLIC")
    op.execute("""REVOKE ALL ON FUNCTION
    business.p6_lock_daily_destination(uuid,uuid,uuid,uuid) FROM PUBLIC""")
    op.execute(r"""CREATE TRIGGER p6_schedule_update BEFORE UPDATE OR DELETE ON
business.p6_daily_schedules
FOR EACH ROW EXECUTE FUNCTION business.p6_schedule_guard()""")
    op.execute("""CREATE TRIGGER p6_run_insert BEFORE INSERT ON business.p6_daily_schedule_runs
    FOR EACH ROW EXECUTE FUNCTION business.p6_run_guard()""")
    op.execute("""CREATE TRIGGER p6_question_task BEFORE INSERT OR UPDATE ON business.business_tasks
    FOR EACH ROW EXECUTE FUNCTION business.p6_question_guard()""")
    op.execute("""CREATE TRIGGER p6_question_result BEFORE INSERT ON business.p6_daily_questions
    FOR EACH ROW EXECUTE FUNCTION business.p6_question_guard()""")
    op.execute("""CREATE TRIGGER p6_schedule_snapshot BEFORE INSERT ON business.p6_daily_snapshots
    FOR EACH ROW EXECUTE FUNCTION business.p6_schedule_snapshot_guard()""")
    op.execute("""CREATE TRIGGER p6_delivery_update BEFORE INSERT OR UPDATE
    ON business.p6_daily_deliveries
    FOR EACH ROW EXECUTE FUNCTION business.p6_delivery_guard()""")


def downgrade() -> None:
    raise RuntimeError("daily operation ledgers require explicit archival")
