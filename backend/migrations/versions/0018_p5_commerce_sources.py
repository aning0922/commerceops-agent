"""Owner-only Woo source registration; bind existing task/snapshot/observation JSON lineage."""

from alembic import op

revision = "0018_p5_commerce_sources"
down_revision = "0017_p4_verified_history"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE business.p5_commerce_source_bindings (
 id uuid PRIMARY KEY,
 organization_id uuid NOT NULL,
 shop_id uuid NOT NULL,
 config_ref text NOT NULL CHECK(length(config_ref) BETWEEN 1 AND 256),
 source_config_version text NOT NULL CHECK(length(source_config_version) BETWEEN 1 AND 256),
 config_digest text NOT NULL CHECK(config_digest ~ '^[0-9a-f]{64}$'),
 projection jsonb NOT NULL,
 canonical_projection text NOT NULL,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 FOREIGN KEY(organization_id,shop_id) REFERENCES business.shops(organization_id,id),
 UNIQUE(organization_id,shop_id,config_ref,source_config_version),
 CHECK(jsonb_typeof(projection)='object'),
 CHECK(projection ?& ARRAY['schema_version','organization_id','shop_id','config_ref',
 'source_config_version','adapter_kind','environment','origin','external_shop_key',
 'currency','timezone','profile','anchor_day','consumer_key_file', -- immutable file references only
 'consumer_secret_file',
 'ca_file','private_pin_ref','per_page','max_pages','max_requests','timeout_seconds',
 'max_elapsed_seconds','max_response_bytes','max_retries']::text[]),
 CHECK(jsonb_strip_nulls(projection)=projection),
 CHECK(canonical_projection::jsonb=projection),
 CHECK(config_digest=encode(sha256(convert_to(canonical_projection,'UTF8')),'hex')),
 CHECK(projection->>'schema_version'='p5-woo-source-v1'),
 CHECK(projection->>'organization_id'=organization_id::text),
 CHECK(projection->>'shop_id'=shop_id::text),
 CHECK(projection->>'config_ref'=config_ref),
 CHECK(projection->>'source_config_version'=source_config_version),
 CHECK(projection->>'adapter_kind'='woocommerce_test' AND projection->>'environment'='test'),
 CHECK(projection - ARRAY['schema_version','organization_id','shop_id','config_ref',
 'source_config_version','adapter_kind','environment','origin','external_shop_key',
 'currency','timezone','profile','anchor_day','consumer_key_file', -- immutable file references only
 'consumer_secret_file',
 'ca_file','private_pin_ref','per_page','max_pages','max_requests','timeout_seconds',
 'max_elapsed_seconds','max_response_bytes','max_retries']::text[]='{}'::jsonb)
)""")
    op.execute("""CREATE TRIGGER p5_source_immutable BEFORE UPDATE OR DELETE
 ON business.p5_commerce_source_bindings FOR EACH ROW
 EXECUTE FUNCTION business.reject_inventory_mutation()""")
    op.execute("""CREATE TRIGGER p5_source_no_truncate BEFORE TRUNCATE
 ON business.p5_commerce_source_bindings FOR EACH STATEMENT
 EXECUTE FUNCTION business.reject_inventory_mutation()""")
    op.execute("REVOKE ALL ON business.p5_commerce_source_bindings FROM PUBLIC")
    op.execute("""CREATE FUNCTION business.p5_source_matches(
 binding text, org uuid, shop uuid, body jsonb, parameters jsonb) RETURNS boolean
 LANGUAGE sql STABLE SET search_path=pg_catalog,business AS $$
 SELECT COALESCE(EXISTS(SELECT 1 FROM business.shops s
 WHERE s.id=shop AND s.organization_id=org
 AND body#>>'{source,shop_id}'=s.external_shop_key
 AND body#>>'{source,currency}'=s.currency AND body#>>'{source,timezone}'=s.timezone
 AND (
 (binding IS NULL AND parameters->>'source_binding_id' IS NULL
  AND COALESCE(parameters->>'source_mode','mock')='mock'
  AND s.adapter_kind='mock' AND s.environment IN ('mock','test')
  AND body#>>'{source,provenance,source_kind}'='mock')
 OR
 (binding IS NOT NULL AND parameters->>'source_binding_id'=binding
  AND parameters->>'source_mode'='woocommerce_test'
  AND parameters->>'organization_id'=org::text AND parameters->>'shop_id'=shop::text
  AND s.adapter_kind='woocommerce_test' AND s.environment='test'
  AND body#>>'{source,provenance,source_kind}'='woocommerce_test'
  AND body#>>'{source,provenance,fixture_version}' IS NULL
  AND EXISTS(SELECT 1 FROM business.p5_commerce_source_bindings b
   WHERE b.id::text=binding AND b.organization_id=org AND b.shop_id=shop
   AND b.config_ref=s.config_ref
   AND b.source_config_version=parameters->>'source_config_version'
   AND s.external_shop_key=b.projection->>'external_shop_key'
   AND b.projection->>'currency'=s.currency AND b.projection->>'timezone'=s.timezone
   AND (body->>'now')::timestamptz=
    ((b.projection->>'anchor_day')::date::timestamp AT TIME ZONE s.timezone)
   AND (body#>>'{window,end}')::timestamptz=
    ((b.projection->>'anchor_day')::date::timestamp AT TIME ZONE s.timezone)
   AND (body#>>'{window,start}')::timestamptz=
    (((b.projection->>'anchor_day')::date-7)::timestamp AT TIME ZONE s.timezone)))
 )),false)
 $$""")
    op.execute(
        "REVOKE ALL ON FUNCTION business.p5_source_matches(text,uuid,uuid,jsonb,jsonb) FROM PUBLIC"
    )
    op.execute("""CREATE FUNCTION business.p5_task_binding_guard() RETURNS trigger
 LANGUAGE plpgsql SET search_path=pg_catalog,business AS $$
 DECLARE binding text; version text;
 BEGIN
 binding:=NEW.normalized_request->>'source_binding_id';
 version:=NEW.normalized_request->>'source_config_version';
 IF TG_OP='UPDATE' AND (
  OLD.normalized_request->>'source_binding_id' IS DISTINCT FROM binding OR
  OLD.normalized_request->>'source_config_version' IS DISTINCT FROM version) THEN
  RAISE EXCEPTION 'commerce task source is immutable' USING ERRCODE='23514';
 END IF;
 IF binding IS NULL THEN
  IF NEW.normalized_request->>'source_mode'='woocommerce_test' OR
   NEW.normalized_request#>>'{request,parameters,source_mode}'='woocommerce_test' THEN
   RAISE EXCEPTION 'commerce source registration required' USING ERRCODE='23514';
  END IF;
 ELSE
  IF NEW.kind='inventory_analysis_only' AND (
   NEW.normalized_request->>'source_mode' IS DISTINCT FROM 'woocommerce_test' OR
   NEW.normalized_request->>'organization_id' IS DISTINCT FROM NEW.organization_id::text OR
   NEW.normalized_request->>'shop_id' IS DISTINCT FROM NEW.shop_id::text) THEN
   RAISE EXCEPTION 'commerce task scope mismatch' USING ERRCODE='23514';
  END IF;
  IF NOT EXISTS(SELECT 1 FROM business.p5_commerce_source_bindings b
   JOIN business.shops s ON s.id=b.shop_id AND s.organization_id=b.organization_id
   WHERE b.id::text=binding AND b.organization_id=NEW.organization_id AND b.shop_id=NEW.shop_id
   AND b.source_config_version=version AND b.config_ref=s.config_ref
   AND s.adapter_kind='woocommerce_test' AND s.environment='test'
   AND s.external_shop_key=b.projection->>'external_shop_key'
   AND b.projection->>'currency'=s.currency AND b.projection->>'timezone'=s.timezone) THEN
   RAISE EXCEPTION 'commerce task source mismatch' USING ERRCODE='23514';
  END IF;
 END IF;
 RETURN NEW;
 END $$""")
    op.execute("""CREATE TRIGGER p5_task_binding BEFORE INSERT OR UPDATE OF normalized_request
 ON business.business_tasks FOR EACH ROW EXECUTE FUNCTION business.p5_task_binding_guard()""")
    op.execute("""CREATE FUNCTION business.p5_p3_source_guard() RETURNS trigger
 LANGUAGE plpgsql SET search_path=pg_catalog,business AS $$
 DECLARE original text; current_binding text;
 BEGIN
 SELECT normalized_request->>'source_binding_id' INTO original FROM business.business_tasks
 WHERE id=NEW.source_task_id AND organization_id=NEW.organization_id AND shop_id=NEW.shop_id;
 SELECT normalized_request->>'source_binding_id' INTO current_binding FROM business.business_tasks
 WHERE id=NEW.task_id AND organization_id=NEW.organization_id AND shop_id=NEW.shop_id;
 IF original IS DISTINCT FROM current_binding OR
  original IS DISTINCT FROM NEW.parameters->>'source_binding_id' THEN
  RAISE EXCEPTION 'commerce workflow source mismatch' USING ERRCODE='23514';
 END IF;
 IF original IS NOT NULL AND NOT EXISTS(SELECT 1 FROM business.p5_commerce_source_bindings b
 WHERE b.id::text=original AND b.organization_id=NEW.organization_id AND b.shop_id=NEW.shop_id
 AND b.source_config_version=NEW.parameters->>'source_config_version'
 AND NEW.parameters->>'source_mode'='woocommerce_test'
 AND NEW.parameters->>'organization_id'=NEW.organization_id::text
 AND NEW.parameters->>'shop_id'=NEW.shop_id::text) THEN
  RAISE EXCEPTION 'commerce parameters scope mismatch' USING ERRCODE='23514';
 END IF;
 RETURN NEW;
 END $$""")
    op.execute("""CREATE TRIGGER p5_p3_source_binding BEFORE INSERT OR UPDATE
 ON business.p3_task_sources FOR EACH ROW EXECUTE FUNCTION business.p5_p3_source_guard()""")
    op.execute("""CREATE OR REPLACE FUNCTION business.bind_inventory_request() RETURNS trigger
 LANGUAGE plpgsql AS $$ BEGIN
 IF NOT EXISTS(SELECT 1 FROM business.business_tasks t WHERE t.id=NEW.task_id
  AND t.organization_id=NEW.organization_id AND t.shop_id=NEW.shop_id
  AND t.kind='inventory_analysis_only' AND t.workflow_version='p203-inventory-analysis-v1'
  AND NEW.logical_key='analysis:'||t.id::text||':'||t.workflow_version
  AND NEW.request_content::jsonb=t.normalized_request
  AND business.p5_source_matches(t.normalized_request->>'source_binding_id',
   t.organization_id,t.shop_id,NEW.content,t.normalized_request)
  AND NEW.source_kind=NEW.content#>>'{source,provenance,source_kind}') THEN
  RAISE EXCEPTION 'snapshot task request mismatch' USING ERRCODE='23514';
 END IF;
 RETURN NEW; END $$""")
    op.execute("""CREATE OR REPLACE FUNCTION business.lock_inventory_permission(
 actor uuid,org uuid,shop uuid,identity uuid,auth bigint) RETURNS boolean
 LANGUAGE sql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,business AS $$
 SELECT EXISTS(SELECT 1 FROM business.principals p
 JOIN business.principal_shop_scopes g
 ON g.principal_id=p.id AND g.organization_id=p.organization_id
 JOIN business.shops s ON s.id=g.shop_id AND s.organization_id=g.organization_id
 WHERE p.id=actor AND p.organization_id=org AND g.shop_id=shop
 AND p.enabled AND 'operator'=ANY(p.roles) AND g.enabled
 AND (identity IS NOT NULL OR (s.environment IN ('test','mock') AND s.adapter_kind='mock')
  OR (s.environment='test' AND s.adapter_kind='woocommerce_test' AND EXISTS(
   SELECT 1 FROM business.p5_commerce_source_bindings b WHERE b.organization_id=org
   AND b.shop_id=shop AND b.config_ref=s.config_ref)))
 AND (identity IS NULL OR (p.auth_version=auth AND EXISTS(SELECT 1 FROM business.identities i
 WHERE i.id=identity AND i.principal_id=p.id AND i.organization_id=p.organization_id)))
 FOR SHARE OF p,g,s)
 $$""")
    op.execute("""CREATE OR REPLACE FUNCTION business.p3_observation_lineage() RETURNS trigger
 LANGUAGE plpgsql AS $$ BEGIN
 IF NOT EXISTS(SELECT 1 FROM business.p3_task_sources b WHERE b.task_id=NEW.task_id
 AND b.organization_id=NEW.organization_id AND b.shop_id=NEW.shop_id
 AND b.source_task_id=NEW.source_task_id AND b.source_report_id=NEW.original_report_id
 AND b.snapshot_id=NEW.original_snapshot_id AND b.facts_hash=NEW.original_facts_hash
 AND b.parameters=NEW.parameters)
 OR NOT business.p5_source_matches(NEW.parameters->>'source_binding_id',
  NEW.organization_id,NEW.shop_id,NEW.input,NEW.parameters)
 OR NEW.report->'source' IS DISTINCT FROM NEW.input->'source'
 OR (NEW.report->'L',NEW.report->'R',NEW.report->'S') IS DISTINCT FROM
 (NEW.parameters->'L',NEW.parameters->'R',NEW.parameters->'S')
 OR EXISTS(SELECT 1 FROM business.analysis_reports r WHERE r.id IN (NEW.report_id,NEW.id))
 OR EXISTS(SELECT 1 FROM business.commerce_snapshots s WHERE s.id IN (NEW.report_id,NEW.id))
 OR EXISTS(SELECT 1 FROM business.p3_observations o
 WHERE o.id=NEW.report_id OR o.report_id=NEW.id) THEN
 RAISE EXCEPTION 'P3 observation lineage or identity mismatch' USING ERRCODE='23514';
 END IF;
 RETURN NEW; END $$""")


def downgrade() -> None:
    raise RuntimeError("destructive downgrade disabled; restore from reviewed backup")
