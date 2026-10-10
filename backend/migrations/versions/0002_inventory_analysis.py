"""任务级analysis-only快照/报告；无审批、执行或通用仓库。"""

from alembic import op

revision = "0002_inventory_analysis"
down_revision = "0001_task_foundation"
branch_labels = None
depends_on = None

DDL = """
CREATE TABLE business.principal_shop_scopes (
 organization_id uuid NOT NULL, shop_id uuid NOT NULL, principal_id uuid NOT NULL,
 enabled boolean NOT NULL DEFAULT true,
 PRIMARY KEY (organization_id,shop_id,principal_id),
 FOREIGN KEY (organization_id,shop_id) REFERENCES business.shops(organization_id,id),
 FOREIGN KEY (organization_id,principal_id) REFERENCES business.principals(organization_id,id)
);
CREATE TABLE business.commerce_snapshots (
 id uuid PRIMARY KEY, organization_id uuid NOT NULL, shop_id uuid NOT NULL, task_id uuid NOT NULL,
 logical_key text NOT NULL, request_content text NOT NULL,
 request_hash text NOT NULL
 CHECK(request_hash=encode(sha256(convert_to(request_content,'UTF8')),'hex')),
 schema_version text NOT NULL CHECK(schema_version='inventory-analysis-v1'),
 source_kind text NOT NULL CHECK(source_kind IN ('mock','woocommerce_test')),
 fixture_version text, shop_timezone text NOT NULL, currency text NOT NULL,
 window_start timestamptz NOT NULL, window_end timestamptz NOT NULL CHECK(window_end>window_start),
 collection_started_at timestamptz NOT NULL, collected_at timestamptz NOT NULL
 CHECK(collected_at>=collection_started_at), complete boolean NOT NULL,
 warnings jsonb NOT NULL CHECK(jsonb_typeof(warnings)='array'),
 consistency text NOT NULL CHECK(consistency='observational'),
 content jsonb NOT NULL CHECK(jsonb_typeof(content)='object'), canonical_content text NOT NULL,
 content_hash text NOT NULL CHECK(content_hash ~ '^[a-f0-9]{64}$'),
 CHECK(canonical_content::jsonb=content),
 CHECK(content_hash=encode(sha256(convert_to(canonical_content,'UTF8')),'hex')),
 UNIQUE(task_id), UNIQUE(organization_id,shop_id,logical_key),
 UNIQUE(organization_id,shop_id,task_id,id),
 FOREIGN KEY(organization_id,shop_id,task_id)
 REFERENCES business.business_tasks(organization_id,shop_id,id)
);
CREATE TABLE business.snapshot_products (
 snapshot_id uuid NOT NULL, organization_id uuid NOT NULL,
 shop_id uuid NOT NULL, task_id uuid NOT NULL,
 sku_key text NOT NULL, stock_pool_key text NOT NULL, payload jsonb NOT NULL,
 available_stock numeric, inbound_units numeric,
 CHECK(available_stock IS NULL OR available_stock=trunc(available_stock)),
 CHECK(inbound_units IS NULL OR (inbound_units>=0 AND inbound_units=trunc(inbound_units))),
 CHECK(available_stock IS NOT DISTINCT FROM (payload->'inventory'->>'available_stock')::numeric),
 CHECK(inbound_units IS NOT DISTINCT FROM (payload->'inventory'->>'inbound_units')::numeric),
 PRIMARY KEY(snapshot_id,sku_key),
 FOREIGN KEY(organization_id,shop_id,task_id,snapshot_id)
 REFERENCES business.commerce_snapshots(organization_id,shop_id,task_id,id)
);
CREATE TABLE business.snapshot_order_lines (
 snapshot_id uuid NOT NULL, organization_id uuid NOT NULL,
 shop_id uuid NOT NULL, task_id uuid NOT NULL,
 order_id text NOT NULL, line_id text NOT NULL, sku_key text NOT NULL, status text NOT NULL,
 created_at_source timestamptz NOT NULL, paid_at timestamptz, completed_at timestamptz,
 quantity numeric NOT NULL CHECK(quantity>0 AND quantity=trunc(quantity)),
 net_amount numeric(20,6) NOT NULL, tax_amount numeric(20,6) NOT NULL,
 currency text NOT NULL, payload jsonb NOT NULL,
 CHECK(jsonb_typeof(payload->'quantity')='number' AND quantity=(payload->>'quantity')::numeric),
 CHECK(net_amount=(payload->>'net_amount')::numeric
 AND tax_amount=(payload->>'tax_amount')::numeric),
 CHECK(jsonb_typeof(payload->'net_amount')='string'
 AND jsonb_typeof(payload->'tax_amount')='string'),
 PRIMARY KEY(snapshot_id,order_id,line_id),
 FOREIGN KEY(organization_id,shop_id,task_id,snapshot_id)
 REFERENCES business.commerce_snapshots(organization_id,shop_id,task_id,id)
);
CREATE TABLE business.snapshot_refunds (
 snapshot_id uuid NOT NULL, organization_id uuid NOT NULL,
 shop_id uuid NOT NULL, task_id uuid NOT NULL,
 refund_id text NOT NULL, order_id text NOT NULL, occurred_at timestamptz NOT NULL,
 refund_amount numeric(20,6) NOT NULL CHECK(refund_amount>=0), currency text NOT NULL,
 payload jsonb NOT NULL,
 CHECK(jsonb_typeof(payload->'refund_amount')='string'
 AND refund_amount=(payload->>'refund_amount')::numeric),
 PRIMARY KEY(snapshot_id,refund_id),
 FOREIGN KEY(organization_id,shop_id,task_id,snapshot_id)
 REFERENCES business.commerce_snapshots(organization_id,shop_id,task_id,id)
);
CREATE TABLE business.analysis_reports (
 id uuid PRIMARY KEY, organization_id uuid NOT NULL, shop_id uuid NOT NULL, task_id uuid NOT NULL,
 snapshot_id uuid NOT NULL, logical_key text NOT NULL,
 rule_version text NOT NULL CHECK(rule_version='inventory-rule-v1'),
 schema_version text NOT NULL CHECK(schema_version='inventory-analysis-v1'),
 facts jsonb NOT NULL, canonical_facts text NOT NULL,
 facts_hash text NOT NULL CHECK(facts_hash ~ '^[a-f0-9]{64}$'), report jsonb NOT NULL,
 outcome text NOT NULL CHECK(outcome IN ('report_ready','no_action')),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 CHECK(canonical_facts::jsonb=facts),
 CHECK(facts_hash=encode(sha256(convert_to(canonical_facts,'UTF8')),'hex')),
 CHECK(report->>'facts_hash'=facts_hash AND report->>'analysis_only'='true'
 AND report->>'execution_available'='false'),
 CHECK(outcome<>'no_action' OR (report->>'complete'='true'
 AND (report->>'candidate_count')::numeric=0 AND report->>'requires_review'='false')),
 UNIQUE(task_id), UNIQUE(organization_id,shop_id,logical_key),
 FOREIGN KEY(organization_id,shop_id,task_id,snapshot_id)
 REFERENCES business.commerce_snapshots(organization_id,shop_id,task_id,id),
 FOREIGN KEY(organization_id,shop_id,task_id)
 REFERENCES business.business_tasks(organization_id,shop_id,id)
);
"""


def upgrade() -> None:
    for statement in DDL.split(";"):
        if statement.strip():
            op.execute(statement)
    # SELECT-only grant 表不能由 runtime 直接行锁；固定参数 definer 仅锁定当前授权。
    op.execute("""
CREATE FUNCTION business.lock_inventory_permission(
 actor uuid,org uuid,shop uuid,identity uuid,auth bigint) RETURNS boolean
 LANGUAGE sql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,business AS $$
 SELECT EXISTS(SELECT 1 FROM business.principals p
 JOIN business.principal_shop_scopes g
 ON g.principal_id=p.id AND g.organization_id=p.organization_id
 JOIN business.shops s ON s.id=g.shop_id AND s.organization_id=g.organization_id
 WHERE p.id=actor AND p.organization_id=org AND g.shop_id=shop
 AND p.enabled AND 'operator'=ANY(p.roles) AND g.enabled
 AND (identity IS NOT NULL OR (s.environment IN ('test','mock') AND s.adapter_kind='mock'))
 AND (identity IS NULL OR (p.auth_version=auth AND EXISTS(SELECT 1 FROM business.identities i
 WHERE i.id=identity AND i.principal_id=p.id AND i.organization_id=p.organization_id)))
 FOR SHARE OF p,g,s)
$$
""")
    op.execute("""REVOKE ALL ON FUNCTION business.lock_inventory_permission(
 uuid,uuid,uuid,uuid,bigint) FROM PUBLIC""")
    op.execute("""
CREATE FUNCTION business.inventory_facts_of_report(body jsonb) RETURNS jsonb
 LANGUAGE sql IMMUTABLE AS $$
 SELECT (body-'facts_hash'-'items') || jsonb_build_object('items',
 COALESCE((SELECT jsonb_agg(item-'display' ORDER BY ordinal)
 FROM jsonb_array_elements(body->'items') WITH ORDINALITY AS x(item,ordinal)), '[]'::jsonb))
$$
""")
    op.execute("""ALTER TABLE business.analysis_reports ADD CONSTRAINT report_matches_facts
 CHECK(business.inventory_facts_of_report(report)=facts)""")
    op.execute("""
CREATE FUNCTION business.reject_inventory_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'inventory evidence is immutable' USING ERRCODE='23514'; END $$
""")
    for table in (
        "commerce_snapshots",
        "snapshot_products",
        "snapshot_order_lines",
        "snapshot_refunds",
        "analysis_reports",
    ):
        op.execute(f"""CREATE TRIGGER immutable_inventory BEFORE UPDATE OR DELETE
 ON business.{table}
 FOR EACH ROW EXECUTE FUNCTION business.reject_inventory_mutation()""")
        op.execute(f"""CREATE TRIGGER immutable_inventory_truncate BEFORE TRUNCATE
 ON business.{table}
 FOR EACH STATEMENT EXECUTE FUNCTION business.reject_inventory_mutation()""")
    op.execute("""
CREATE FUNCTION business.bind_inventory_request() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NOT EXISTS(SELECT 1 FROM business.business_tasks t WHERE t.id=NEW.task_id
  AND t.organization_id=NEW.organization_id AND t.shop_id=NEW.shop_id
  AND t.kind='inventory_analysis_only' AND t.workflow_version='p203-inventory-analysis-v1'
  AND NEW.logical_key='analysis:'||t.id::text||':'||t.workflow_version
  AND NEW.request_content::jsonb=t.normalized_request) THEN
  RAISE EXCEPTION 'snapshot task request mismatch' USING ERRCODE='23514';
 END IF;
 RETURN NEW;
END $$
""")
    op.execute("""CREATE TRIGGER bind_inventory_request BEFORE INSERT ON business.commerce_snapshots
 FOR EACH ROW EXECUTE FUNCTION business.bind_inventory_request()""")
    op.execute("""
CREATE FUNCTION business.valid_inventory_result(task uuid,org uuid,shop uuid,version text)
 RETURNS boolean LANGUAGE sql STABLE AS $$
 SELECT EXISTS(SELECT 1 FROM business.analysis_reports r
 JOIN business.commerce_snapshots s ON s.id=r.snapshot_id AND s.task_id=r.task_id
 AND s.organization_id=r.organization_id AND s.shop_id=r.shop_id
 JOIN business.business_tasks t ON t.id=r.task_id
 WHERE r.task_id=$1 AND r.organization_id=$2 AND r.shop_id=$3
 AND s.logical_key='analysis:'||$1::text||':'||$4 AND r.logical_key=(s.logical_key)
 AND s.request_content::jsonb=t.normalized_request
 AND r.facts_hash=encode(sha256(convert_to(r.canonical_facts,'UTF8')),'hex')
 AND s.content_hash=encode(sha256(convert_to(s.canonical_content,'UTF8')),'hex'))
$$
""")
    op.execute("""
CREATE FUNCTION business.preserve_inventory_task() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF TG_OP='INSERT' THEN
  IF NEW.kind='inventory_analysis_only' AND
   (NEW.state<>'queued' OR NEW.workflow_version<>'p203-inventory-analysis-v1') THEN
   RAISE EXCEPTION 'analysis must start queued with pinned workflow' USING ERRCODE='23514';
  END IF;
  RETURN NEW;
 END IF;
 IF OLD.kind='inventory_analysis_only' OR NEW.kind='inventory_analysis_only' THEN
  IF (NEW.kind,NEW.normalized_request) IS DISTINCT FROM (OLD.kind,OLD.normalized_request) THEN
   RAISE EXCEPTION 'analysis identity is immutable' USING ERRCODE='23514';
  END IF;
  IF OLD.state='completed' AND NEW.state<>OLD.state THEN
   RAISE EXCEPTION 'analysis terminal state is immutable' USING ERRCODE='23514';
  END IF;
  IF NEW.state='completed' AND NOT business.valid_inventory_result(
   NEW.id,NEW.organization_id,NEW.shop_id,NEW.workflow_version) THEN
   RAISE EXCEPTION 'analysis completion requires durable report' USING ERRCODE='23514';
  END IF;
  IF NEW.state NOT IN ('queued','analyzing','completed','failed','needs_attention') THEN
   RAISE EXCEPTION 'analysis-only state required' USING ERRCODE='23514';
  END IF;
 END IF;
 RETURN NEW;
END $$
""")
    op.execute("""CREATE TRIGGER preserve_inventory_task BEFORE INSERT OR UPDATE
 ON business.business_tasks
 FOR EACH ROW EXECUTE FUNCTION business.preserve_inventory_task()""")


def downgrade() -> None:
    raise RuntimeError("destructive downgrade is disabled; restore a verified backup")
