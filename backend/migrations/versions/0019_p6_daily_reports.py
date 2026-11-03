"""独立日报三表、严格来源谱系与封存；不修改旧迁移或来源约束。"""

from alembic import op

revision = "0019_p6_daily_reports"
down_revision = "0018_p5_commerce_sources"
branch_labels = None
depends_on = None

DDL = """
CREATE FUNCTION business.p6_json_hash(text_value text,body jsonb,digest text)
RETURNS boolean LANGUAGE sql IMMUTABLE SET search_path=pg_catalog AS $$
 SELECT (jsonb_typeof(body)='object' AND text_value::jsonb=body
 AND digest ~ '^[a-f0-9]{64}$'
 AND digest=encode(sha256(convert_to(text_value,'UTF8')),'hex')) IS TRUE
$$;
CREATE FUNCTION business.p6_keys(body jsonb,expected text[]) RETURNS boolean
LANGUAGE sql IMMUTABLE SET search_path=pg_catalog AS $$
 SELECT (jsonb_typeof(body)='object' AND body ?& expected
 AND body - expected='{}'::jsonb) IS TRUE
$$;
CREATE TABLE business.p6_daily_source_bindings (
 id uuid PRIMARY KEY,organization_id uuid NOT NULL,shop_id uuid NOT NULL,
 config_ref text NOT NULL,source_config_version text NOT NULL,
 canonical_projection text NOT NULL,projection jsonb NOT NULL,config_digest text NOT NULL,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 FOREIGN KEY(organization_id,shop_id) REFERENCES business.shops(organization_id,id),
 UNIQUE(organization_id,shop_id,id),UNIQUE(organization_id,shop_id,config_ref),
 UNIQUE(organization_id,shop_id,source_config_version),
 CHECK(business.p6_json_hash(canonical_projection,projection,config_digest)),
 CHECK((projection->>'schema_version'='p6-daily-binding-v1'
 AND projection->>'organization_id'=organization_id::text
 AND projection->>'shop_id'=shop_id::text AND projection->>'config_ref'=config_ref
 AND projection->>'source_config_version'=source_config_version
 AND length(config_ref) BETWEEN 1 AND 256 AND length(source_config_version) BETWEEN 1 AND 256
 AND projection->>'metric_version'='daily-metrics-v1'
 AND projection->>'status_mapping_version'='daily-status-v1'
 AND projection->>'currency' IN ('CNY','USD','EUR','JPY','GBP','AUD','CAD','HKD','CHF','SGD')
 AND jsonb_typeof(projection->'limits')='object'
 AND projection->>'source_kind' IN ('mock','woocommerce_test')) IS TRUE)
);
CREATE TABLE business.p6_daily_snapshots (
 id uuid PRIMARY KEY,organization_id uuid NOT NULL,shop_id uuid NOT NULL,task_id uuid NOT NULL,
 source_binding_id uuid NOT NULL,request_content text NOT NULL,request_hash text NOT NULL,
 schema_version text NOT NULL CHECK(schema_version='p6-daily-snapshot-v1'),
 business_day date NOT NULL,timezone text NOT NULL,currency text NOT NULL,
 window_start timestamptz NOT NULL,window_end timestamptz NOT NULL,
 collection_started_at timestamptz NOT NULL,collected_at timestamptz NOT NULL,
 complete boolean NOT NULL,content jsonb NOT NULL,canonical_content text NOT NULL,
 content_hash text NOT NULL,receipt jsonb NOT NULL,canonical_receipt text NOT NULL,
 receipt_hash text NOT NULL,created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 UNIQUE(task_id),UNIQUE(organization_id,shop_id,task_id,id),
 UNIQUE(organization_id,shop_id,task_id,id,source_binding_id),
 FOREIGN KEY(organization_id,shop_id,task_id)
 REFERENCES business.business_tasks(organization_id,shop_id,id),
 FOREIGN KEY(organization_id,shop_id,source_binding_id)
 REFERENCES business.p6_daily_source_bindings(organization_id,shop_id,id),
 CHECK(window_end>window_start AND collection_started_at>=window_end
 AND collected_at>=collection_started_at),
 CHECK(window_start=(business_day::timestamp AT TIME ZONE timezone)
 AND window_end=((business_day+1)::timestamp AT TIME ZONE timezone)),
 CHECK((NOT complete OR (content#>>'{coverage,orders_complete}'='true'
 AND content#>>'{coverage,order_lines_complete}'='true'
 AND content#>>'{coverage,refunds_complete}'='true'
 AND content#>'{coverage,quality_flags}'='[]'::jsonb
 AND receipt->>'expected_set_hash'=receipt->>'observed_set_hash')) IS TRUE),
 CHECK(business.p6_json_hash(request_content,request_content::jsonb,request_hash)),
 CHECK(business.p6_json_hash(canonical_content,content,content_hash)),
 CHECK(business.p6_json_hash(canonical_receipt,receipt,receipt_hash)),
 CHECK((content->>'schema_version'=schema_version AND content->>'snapshot_id'=id::text
 AND content->>'business_day'=business_day::text
 AND content#>>'{source,organization_id}'=organization_id::text
 AND content#>>'{source,shop_id}'=shop_id::text
 AND content#>>'{source,source_binding_id}'=source_binding_id::text
 AND content#>>'{source,timezone}'=timezone AND content#>>'{source,currency}'=currency
 AND content#>>'{coverage,collection_started_at}' IS NOT NULL
 AND (content#>>'{coverage,collection_started_at}')::timestamptz=collection_started_at
 AND (content#>>'{coverage,collected_at}')::timestamptz=collected_at
 AND jsonb_typeof(content->'orders')='array' AND jsonb_typeof(content->'order_lines')='array'
 AND jsonb_typeof(content->'refunds')='array'
 AND receipt->>'schema_version'='p6-daily-collection-v1'
 AND receipt->>'source_binding_id'=source_binding_id::text
 AND receipt->>'snapshot_content_hash'=content_hash) IS TRUE)
);
CREATE TABLE business.p6_daily_reports (
 id uuid PRIMARY KEY,organization_id uuid NOT NULL,shop_id uuid NOT NULL,task_id uuid NOT NULL,
 snapshot_id uuid NOT NULL,source_binding_id uuid NOT NULL,
 schema_version text NOT NULL CHECK(schema_version='p6-daily-report-v1'),
 metric_version text NOT NULL CHECK(metric_version='daily-metrics-v1'),
 report jsonb NOT NULL,canonical_report text NOT NULL,report_hash text NOT NULL,
 canonical_facts text NOT NULL,facts_hash text NOT NULL,complete boolean NOT NULL,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 UNIQUE(task_id),UNIQUE(organization_id,shop_id,task_id,id),
 FOREIGN KEY(organization_id,shop_id,task_id,snapshot_id,source_binding_id)
 REFERENCES business.p6_daily_snapshots(organization_id,shop_id,task_id,id,source_binding_id),
 CHECK(business.p6_json_hash(canonical_report,report,report_hash)),
 CHECK(business.p6_json_hash(canonical_facts,report-'facts_hash'-'display',facts_hash)),
 CHECK((report->>'schema_version'=schema_version AND report->>'metric_version'=metric_version
 AND report->>'snapshot_id'=snapshot_id::text AND report->>'facts_hash'=facts_hash
 AND report#>>'{source,organization_id}'=organization_id::text
 AND report#>>'{source,shop_id}'=shop_id::text
 AND report#>>'{source,source_binding_id}'=source_binding_id::text
 AND report->>'analysis_only'='true' AND report->>'execution_available'='false'
 AND jsonb_typeof(report->'complete')='boolean' AND (report->>'complete')::boolean=complete
 AND ((complete AND jsonb_typeof(report->'metrics')='object') OR
 (NOT complete AND report->'metrics'='null'::jsonb AND report->'display'='[]'::jsonb))) IS TRUE)
);
"""

FUNCTIONS = [
    """
CREATE FUNCTION business.p6_reject_mutation() RETURNS trigger LANGUAGE plpgsql
SET search_path=pg_catalog,business AS $$ BEGIN
 RAISE EXCEPTION 'daily evidence is immutable' USING ERRCODE='23514'; END $$
""",
    """
CREATE FUNCTION business.p6_source_valid(org uuid,shop uuid,binding uuid,source jsonb)
RETURNS boolean LANGUAGE sql STABLE SET search_path=pg_catalog,business AS $$
 SELECT EXISTS(SELECT 1 FROM business.p6_daily_source_bindings b
 JOIN business.shops s ON s.organization_id=b.organization_id AND s.id=b.shop_id
 WHERE b.id=binding AND b.organization_id=org AND b.shop_id=shop AND b.config_ref=s.config_ref
 AND s.external_shop_key=b.projection->>'external_shop_key'
 AND b.projection->>'environment'=s.environment AND b.projection->>'source_kind'=s.adapter_kind
 AND b.projection->>'timezone'=s.timezone AND b.projection->>'currency'=s.currency
 AND source->>'schema_version'='p6-daily-source-v1' AND source->>'organization_id'=org::text
 AND source->>'shop_id'=shop::text AND source->>'source_binding_id'=binding::text
 AND source->>'source_config_version'=b.source_config_version
 AND source->>'config_digest'=b.config_digest
 AND source->>'source_kind'=s.adapter_kind AND source->>'timezone'=s.timezone
 AND source->>'currency'=s.currency
 AND source->>'status_mapping_version'='daily-status-v1'
 AND business.p6_keys(source,ARRAY['schema_version','organization_id','shop_id','source_binding_id',
 'source_config_version','config_digest','source_kind','fixture_version','currency','timezone','status_mapping_version'])
 AND ((s.adapter_kind='mock' AND jsonb_typeof(source->'fixture_version')='string'
 AND source->>'fixture_version'=b.projection->>'fixture_version') OR
 (s.adapter_kind='woocommerce_test' AND source->'fixture_version'='null'::jsonb)))
$$
""",
    """
CREATE FUNCTION business.p6_current_permission(actor uuid,org uuid,shop uuid,auth bigint)
RETURNS boolean LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,business AS $$
BEGIN
 PERFORM 1 FROM business.principals p WHERE p.id=actor AND p.organization_id=org
 AND p.enabled AND p.auth_version=auth AND 'operator'=ANY(p.roles) FOR SHARE;
 IF NOT FOUND THEN RETURN false; END IF;
 RETURN EXISTS(SELECT 1 FROM business.principal_shop_scopes g
 JOIN business.principal_role_shop_grants r ON r.organization_id=g.organization_id
 AND r.shop_id=g.shop_id AND r.principal_id=g.principal_id
 JOIN business.shops s ON s.organization_id=g.organization_id AND s.id=g.shop_id
 WHERE g.organization_id=org AND g.shop_id=shop AND g.principal_id=actor
 AND g.enabled AND r.enabled AND r.role='operator' FOR SHARE OF g,r,s);
END $$
""",
    """
CREATE FUNCTION business.p6_task_guard() RETURNS trigger LANGUAGE plpgsql
SET search_path=pg_catalog,business AS $$
DECLARE source jsonb; bound uuid; BEGIN
 IF NEW.kind<>'daily_report' THEN
  IF NEW.normalized_request ? 'daily_source' OR (TG_OP='UPDATE' AND OLD.kind='daily_report') THEN
   RAISE EXCEPTION 'daily task kind cannot change' USING ERRCODE='23514';
  END IF; RETURN NEW;
 END IF;
 IF NEW.workflow_version<>'p6-daily-report-v1' OR NOT business.p6_keys(NEW.normalized_request,
 ARRAY['schema_version','daily_source','business_day','snapshot_id','rules','request_key',
 'request_hash','conversation_id','requester_auth_version']) OR
 (NEW.normalized_request->>'schema_version'='p6-daily-task-v1'
 AND NEW.normalized_request->>'conversation_id'=NEW.conversation_id::text
 AND jsonb_typeof(NEW.normalized_request->'daily_source')='object'
 AND jsonb_typeof(NEW.normalized_request->'requester_auth_version')='number'
 AND (NEW.normalized_request->>'requester_auth_version')::numeric>0
 AND (NEW.normalized_request->>'requester_auth_version')::numeric=
 trunc((NEW.normalized_request->>'requester_auth_version')::numeric)
 AND jsonb_typeof(NEW.normalized_request->'request_key')='string'
 AND jsonb_typeof(NEW.normalized_request->'snapshot_id')='string'
 AND jsonb_typeof(NEW.normalized_request->'business_day')='string'
 AND jsonb_typeof(NEW.normalized_request->'rules')='object'
 AND NEW.normalized_request->>'request_hash' ~ '^[a-f0-9]{64}$') IS NOT TRUE THEN
  RAISE EXCEPTION 'invalid daily task' USING ERRCODE='23514'; END IF;
 source:=NEW.normalized_request->'daily_source';
 bound:=(source->>'source_binding_id')::uuid;
 IF TG_OP='INSERT' AND (NEW.state<>'queued' OR NOT business.p6_source_valid(
 NEW.organization_id,NEW.shop_id,bound,source)) THEN
  RAISE EXCEPTION 'daily source unavailable' USING ERRCODE='23514'; END IF;
 PERFORM (NEW.normalized_request->>'request_key')::uuid,
 (NEW.normalized_request->>'snapshot_id')::uuid,(NEW.normalized_request->>'business_day')::date;
 IF TG_OP='UPDATE' AND (OLD.id,OLD.kind,OLD.organization_id,OLD.shop_id,OLD.conversation_id,
 OLD.requester_id,OLD.thread_id,OLD.workflow_version,OLD.normalized_request) IS DISTINCT FROM
 (NEW.id,NEW.kind,NEW.organization_id,NEW.shop_id,NEW.conversation_id,NEW.requester_id,
 NEW.thread_id,NEW.workflow_version,NEW.normalized_request) THEN
  RAISE EXCEPTION 'daily request immutable' USING ERRCODE='23514'; END IF;
 IF TG_OP='UPDATE' AND OLD.state='completed'
 AND (NEW.state,NEW.failure_code) IS DISTINCT FROM (OLD.state,OLD.failure_code) THEN
  RAISE EXCEPTION 'daily completed immutable' USING ERRCODE='23514'; END IF;
 IF NEW.state='completed' AND NEW.failure_code IS NOT NULL THEN
  RAISE EXCEPTION 'daily completed cannot have failure' USING ERRCODE='23514'; END IF;
 IF NEW.state NOT IN ('queued','analyzing','completed','failed','needs_attention') THEN
  RAISE EXCEPTION 'invalid daily state' USING ERRCODE='23514'; END IF;
 IF NEW.state='completed' AND NOT EXISTS(SELECT 1 FROM business.p6_daily_reports r
 WHERE r.task_id=NEW.id AND r.organization_id=NEW.organization_id
 AND r.shop_id=NEW.shop_id AND r.complete) THEN
  RAISE EXCEPTION 'daily completion needs report' USING ERRCODE='23514'; END IF;
 RETURN NEW;
END $$
""",
    """
CREATE FUNCTION business.p6_snapshot_guard() RETURNS trigger LANGUAGE plpgsql
SET search_path=pg_catalog,business AS $$ DECLARE task business.business_tasks; BEGIN
 SELECT * INTO task FROM business.business_tasks WHERE id=NEW.task_id
 AND organization_id=NEW.organization_id AND shop_id=NEW.shop_id FOR UPDATE;
 IF task.id IS NULL OR task.kind<>'daily_report' OR task.state<>'analyzing'
 OR NEW.request_content::jsonb IS DISTINCT FROM task.normalized_request
 OR NEW.content->'source' IS DISTINCT FROM task.normalized_request->'daily_source'
 OR NEW.content->'rules' IS DISTINCT FROM task.normalized_request->'rules'
 OR NEW.id::text IS DISTINCT FROM task.normalized_request->>'snapshot_id'
 OR NEW.business_day::text IS DISTINCT FROM task.normalized_request->>'business_day'
 OR NOT business.p6_source_valid(NEW.organization_id,NEW.shop_id,
 NEW.source_binding_id,NEW.content->'source')
 OR NOT business.p6_current_permission(task.requester_id,NEW.organization_id,NEW.shop_id,
 (task.normalized_request->>'requester_auth_version')::bigint)
 OR NOT EXISTS(SELECT 1 FROM business.jobs j WHERE j.task_id=NEW.task_id AND j.status='running'
 AND j.organization_id=NEW.organization_id AND j.shop_id=NEW.shop_id AND j.lease_owner IS NOT NULL)
 OR EXISTS(SELECT 1 FROM business.p6_daily_reports r WHERE r.task_id=NEW.task_id) THEN
  RAISE EXCEPTION 'daily snapshot lineage invalid' USING ERRCODE='23514'; END IF;
 IF (jsonb_typeof(NEW.receipt->'all_queries_revalidated')='boolean'
 AND NEW.receipt->>'all_queries_revalidated'='true'
 AND NEW.receipt->>'config_digest'=NEW.content#>>'{source,config_digest}'
 AND NEW.receipt->>'manifest_digest'=(SELECT projection->>'manifest_digest'
 FROM business.p6_daily_source_bindings WHERE id=NEW.source_binding_id)) IS NOT TRUE THEN
  RAISE EXCEPTION 'daily receipt invalid' USING ERRCODE='23514'; END IF;
 RETURN NEW;
END $$
""",
    """
CREATE FUNCTION business.p6_report_guard() RETURNS trigger LANGUAGE plpgsql
SET search_path=pg_catalog,business AS $$ DECLARE snap business.p6_daily_snapshots; BEGIN
 SELECT * INTO snap FROM business.p6_daily_snapshots WHERE id=NEW.snapshot_id
 AND organization_id=NEW.organization_id AND shop_id=NEW.shop_id AND task_id=NEW.task_id;
 IF snap.id IS NULL OR NEW.report->>'content_hash' IS DISTINCT FROM snap.content_hash
 OR NEW.report->'source' IS DISTINCT FROM snap.content->'source'
 OR NEW.report->'rules' IS DISTINCT FROM snap.content->'rules'
 OR NEW.report->'coverage' IS DISTINCT FROM snap.content->'coverage'
 OR NEW.report->>'business_day' IS DISTINCT FROM snap.content->>'business_day'
 OR (NEW.report#>>'{window,start}')::timestamptz IS DISTINCT FROM snap.window_start
 OR (NEW.report#>>'{window,end}')::timestamptz IS DISTINCT FROM snap.window_end
 OR NEW.complete IS DISTINCT FROM snap.complete THEN
  RAISE EXCEPTION 'daily report lineage invalid' USING ERRCODE='23514'; END IF;
 RETURN NEW;
END $$
""",
    """
CREATE FUNCTION business.p6_shop_owner_guard() RETURNS trigger LANGUAGE plpgsql
SET search_path=pg_catalog,business AS $$ BEGIN
 IF (OLD.organization_id,OLD.id,OLD.config_ref,OLD.adapter_kind,OLD.external_shop_key,
 OLD.environment,OLD.currency,OLD.timezone) IS DISTINCT FROM
 (NEW.organization_id,NEW.id,NEW.config_ref,NEW.adapter_kind,NEW.external_shop_key,
 NEW.environment,NEW.currency,NEW.timezone)
 AND EXISTS(SELECT 1 FROM business.p6_daily_source_bindings WHERE shop_id=OLD.id)
 AND current_user<>(SELECT pg_get_userbyid(relowner) FROM pg_class
 WHERE oid='business.p6_daily_source_bindings'::regclass) THEN
  RAISE EXCEPTION 'daily shop binding owner only' USING ERRCODE='23514'; END IF;
 RETURN NEW;
END $$
""",
]


FUNCTIONS.append(r"""
CREATE FUNCTION business.p6_binding_guard() RETURNS trigger LANGUAGE plpgsql
SET search_path=pg_catalog,business AS $$
DECLARE common_keys text[]:=ARRAY['schema_version','organization_id','shop_id','config_ref',
 'source_config_version','external_shop_key','timezone','currency','earliest_business_day',
 'manifest_ref','manifest_digest','limits','metric_version','status_mapping_version',
 'source_kind','environment','coverage_profile'];
limits_keys text[]:=ARRAY['per_page','max_pages','max_requests','timeout_seconds',
 'max_elapsed_seconds','max_response_bytes','max_orders','max_lines','max_refunds',
 'max_snapshot_bytes','max_retries'];
keys text[]; name text; value numeric; cap numeric;
BEGIN
 keys:=common_keys || CASE WHEN NEW.projection->>'source_kind'='mock' THEN
 ARRAY['fixture_ref','fixture_digest','fixture_version'] ELSE
 ARRAY['origin','ca_file','private_pin_ref']
 || ARRAY['consumer_key_file'] || ARRAY['consumer_secret_file'] END;
 IF NOT business.p6_keys(NEW.projection,keys)
 OR NOT business.p6_keys(NEW.projection->'limits',limits_keys) THEN
  RAISE EXCEPTION 'daily binding keys invalid' USING ERRCODE='23514'; END IF;
 FOREACH name IN ARRAY keys LOOP
  IF name<>'limits' AND jsonb_typeof(NEW.projection->name) IS DISTINCT FROM 'string' THEN
   RAISE EXCEPTION 'daily binding type invalid' USING ERRCODE='23514'; END IF;
 END LOOP;
 FOREACH name IN ARRAY limits_keys LOOP
  IF jsonb_typeof(NEW.projection->'limits'->name) IS DISTINCT FROM 'number' THEN
   RAISE EXCEPTION 'daily limit type invalid' USING ERRCODE='23514'; END IF;
  value:=(NEW.projection->'limits'->>name)::numeric;
  cap:=CASE name WHEN 'per_page' THEN 100 WHEN 'max_pages' THEN 32
   WHEN 'max_requests' THEN 256 WHEN 'timeout_seconds' THEN 10 WHEN 'max_elapsed_seconds' THEN 18
   WHEN 'max_response_bytes' THEN 2097152 WHEN 'max_orders' THEN 1000
   WHEN 'max_lines' THEN 10000 WHEN 'max_refunds' THEN 10000
   WHEN 'max_snapshot_bytes' THEN 8388608 WHEN 'max_retries' THEN 0 END;
  IF value<>trunc(value) OR value>cap OR value<CASE WHEN name='max_retries' THEN 0
 WHEN name IN ('max_snapshot_bytes','max_response_bytes') THEN 128 ELSE 1 END THEN
   RAISE EXCEPTION 'daily limit out of range' USING ERRCODE='23514'; END IF;
 END LOOP;
 IF (NEW.projection->>'manifest_digest' ~ '^[a-f0-9]{64}$'
 AND length(NEW.projection->>'manifest_ref')>0
 AND ((NEW.projection->>'source_kind'='mock'
 AND NEW.projection->>'environment' IN ('test','mock')
 AND NEW.projection->>'coverage_profile'='complete_fixture_v1'
 AND NEW.projection->>'fixture_digest' ~ '^[a-f0-9]{64}$') OR
 (NEW.projection->>'source_kind'='woocommerce_test' AND NEW.projection->>'environment'='test'
 AND NEW.projection->>'coverage_profile'='closed_test_manifest_v1'
 AND NEW.projection->>'origin'
 ~ '^https://(localhost|127[.]0[.]0[.]1|\[::1\]):[0-9]+$'))) IS NOT TRUE THEN
  RAISE EXCEPTION 'daily source profile invalid' USING ERRCODE='23514'; END IF;
 PERFORM (NEW.projection->>'earliest_business_day')::date;
 RETURN NEW;
END $$
""")


def upgrade() -> None:
    # DDL用分隔标记逐句，函数体含分号，不能用split(';')破坏SQL。
    op.execute(DDL)
    for statement in FUNCTIONS:
        op.execute(statement)
    for name in (
        "p6_json_hash(text,jsonb,text)",
        "p6_keys(jsonb,text[])",
        "p6_source_valid(uuid,uuid,uuid,jsonb)",
        "p6_current_permission(uuid,uuid,uuid,bigint)",
    ):
        op.execute(f"REVOKE ALL ON FUNCTION business.{name} FROM PUBLIC")
    for table in ("p6_daily_source_bindings", "p6_daily_snapshots", "p6_daily_reports"):
        op.execute(f"REVOKE ALL ON business.{table} FROM PUBLIC")
        op.execute(f"""CREATE TRIGGER p6_immutable BEFORE UPDATE OR DELETE ON business.{table}
        FOR EACH ROW EXECUTE FUNCTION business.p6_reject_mutation()""")
        op.execute(f"""CREATE TRIGGER p6_no_truncate BEFORE TRUNCATE ON business.{table}
        FOR EACH STATEMENT EXECUTE FUNCTION business.p6_reject_mutation()""")
    op.execute("""CREATE TRIGGER p6_binding BEFORE INSERT ON business.p6_daily_source_bindings
    FOR EACH ROW EXECUTE FUNCTION business.p6_binding_guard()""")
    op.execute("""CREATE TRIGGER p6_task BEFORE INSERT OR UPDATE ON business.business_tasks
    FOR EACH ROW EXECUTE FUNCTION business.p6_task_guard()""")
    op.execute("""CREATE TRIGGER p6_snapshot BEFORE INSERT ON business.p6_daily_snapshots
    FOR EACH ROW EXECUTE FUNCTION business.p6_snapshot_guard()""")
    op.execute("""CREATE TRIGGER p6_report BEFORE INSERT ON business.p6_daily_reports
    FOR EACH ROW EXECUTE FUNCTION business.p6_report_guard()""")
    op.execute("""CREATE TRIGGER p6_shop_owner BEFORE UPDATE ON business.shops
    FOR EACH ROW EXECUTE FUNCTION business.p6_shop_owner_guard()""")
    op.execute("""CREATE UNIQUE INDEX p6_request_key ON business.business_tasks
    (organization_id,requester_id,(normalized_request->>'request_key'))
    WHERE kind='daily_report'""")


def downgrade() -> None:
    raise RuntimeError("daily evidence requires explicit archival; no destructive downgrade")
