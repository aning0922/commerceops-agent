"""P204最小说明子任务与全阶段持久admission，非通用调度/审批。"""

from alembic import op

revision = "0003_inventory_explanations"
down_revision = "0002_inventory_analysis"
branch_labels = None
depends_on = None

DDL = """
ALTER TABLE business.analysis_reports ADD UNIQUE(organization_id,shop_id,task_id,id);
CREATE TABLE business.explanation_links (
 child_task_id uuid PRIMARY KEY,organization_id uuid NOT NULL,shop_id uuid NOT NULL,
 parent_task_id uuid NOT NULL,snapshot_id uuid NOT NULL,report_id uuid NOT NULL,
 requester_id uuid NOT NULL,identity_id uuid NOT NULL,auth_version bigint NOT NULL
 CHECK(auth_version>0),
 logical_key text NOT NULL,body_hash text NOT NULL,facts_hash text NOT NULL,
 evidence_mode text NOT NULL
 CHECK(evidence_mode IN ('template','offline_stub','actual_provider','local_fault')),
 UNIQUE(organization_id,shop_id,child_task_id),
 FOREIGN KEY(organization_id,shop_id,child_task_id)
 REFERENCES business.business_tasks(organization_id,shop_id,id),
 FOREIGN KEY(organization_id,shop_id,parent_task_id,report_id)
 REFERENCES business.analysis_reports(organization_id,shop_id,task_id,id),
 FOREIGN KEY(organization_id,shop_id,parent_task_id,snapshot_id)
 REFERENCES business.commerce_snapshots(organization_id,shop_id,task_id,id),
 FOREIGN KEY(organization_id,requester_id) REFERENCES business.principals(organization_id,id)
);
CREATE TABLE business.model_stage_budgets (
 stage_key text PRIMARY KEY
 CHECK(stage_key IN ('phase2-deepseek-20261010:actual','phase2-deepseek-20261010:offline')),
 reserved_count integer NOT NULL DEFAULT 0 CHECK(reserved_count BETWEEN 0 AND 10),
 reserved_nanos bigint NOT NULL DEFAULT 0 CHECK(reserved_nanos BETWEEN 0 AND 100000000),
 halted boolean NOT NULL DEFAULT false,
 updated_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE TABLE business.inventory_intent_requests (
 task_id uuid PRIMARY KEY,organization_id uuid NOT NULL,shop_id uuid NOT
 NULL,requester_id uuid NOT NULL,
 identity_id uuid NOT NULL,auth_version bigint NOT NULL CHECK(auth_version>0),logical_key
 text NOT NULL,
 body_hash text NOT NULL,input_hash text NOT NULL,evidence_mode text NOT NULL
 CHECK(evidence_mode IN ('template','offline_stub','actual_provider','local_fault')),
 UNIQUE(organization_id,shop_id,task_id),
 FOREIGN KEY(organization_id,shop_id,task_id) REFERENCES
 business.business_tasks(organization_id,shop_id,id),
 FOREIGN KEY(organization_id,requester_id) REFERENCES business.principals(organization_id,id)
);
CREATE TABLE business.inventory_intent_results (
 task_id uuid PRIMARY KEY,organization_id uuid NOT NULL,shop_id uuid NOT NULL,logical_key
 text NOT NULL,
 body_hash text NOT NULL,input_hash text NOT NULL,result jsonb NOT NULL,canonical_result
 text NOT NULL,
 result_hash text NOT NULL,created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 FOREIGN KEY(organization_id,shop_id,task_id) REFERENCES
 business.inventory_intent_requests(organization_id,shop_id,task_id),
 CHECK(canonical_result::jsonb=result),
 CHECK(result_hash=encode(sha256(convert_to(canonical_result,'UTF8')),'hex'))
);
CREATE INDEX inventory_intent_cache ON business.inventory_intent_results(logical_key,created_at);
CREATE TABLE business.model_calls (
 id uuid PRIMARY KEY,organization_id uuid NOT NULL,shop_id uuid NOT NULL,
 child_task_id uuid, intent_task_id uuid,
 stage_key text NOT NULL REFERENCES business.model_stage_budgets(stage_key),
 logical_key text NOT NULL UNIQUE,request_id uuid NOT NULL UNIQUE,request_hash text NOT NULL,
 facts_hash text NOT NULL,evidence_mode text NOT NULL
 CHECK(evidence_mode IN ('offline_stub','actual_provider')),
 preflight_input_bound integer NOT NULL CHECK(preflight_input_bound BETWEEN 1 AND 8000),
 reserved_input integer NOT NULL CHECK(reserved_input=8000),
 reserved_output integer NOT NULL CHECK(reserved_output=800),
 reserved_nanos bigint NOT NULL CHECK(reserved_nanos=3360000),
 pricing_version text NOT NULL CHECK(pricing_version='ds-v41-peak-20261010'),
 prompt_version text NOT NULL
 CHECK(prompt_version IN ('inventory-explanation-v1','inventory-routing-v1')),
 tokenizer_version text NOT NULL,created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 FOREIGN KEY(organization_id,shop_id,child_task_id)
 REFERENCES business.explanation_links(organization_id,shop_id,child_task_id),
 FOREIGN KEY(organization_id,shop_id,intent_task_id)
 REFERENCES business.inventory_intent_requests(organization_id,shop_id,task_id),
 CHECK((child_task_id IS NULL) <> (intent_task_id IS NULL)),
 CHECK(request_hash ~ '^[a-f0-9]{64}$' AND facts_hash ~ '^[a-f0-9]{64}$')
);
CREATE TABLE business.model_call_observations (
 call_id uuid PRIMARY KEY REFERENCES business.model_calls(id),
 outcome text NOT NULL CHECK(outcome IN ('observed','uncertain')),
 input_tokens integer CHECK(input_tokens>=0),output_tokens integer CHECK(output_tokens>=0),
 total_tokens integer CHECK(total_tokens>=0),estimate_nanos bigint CHECK(estimate_nanos>=0),
 actual_cost_usd numeric CHECK(actual_cost_usd IS NULL),
 safe_error text,stop_required boolean NOT NULL,latency_ms bigint CHECK(latency_ms>=0),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 CHECK((input_tokens IS NULL AND output_tokens IS NULL AND total_tokens IS NULL)
 OR (input_tokens IS NOT NULL AND output_tokens IS NOT NULL
 AND total_tokens=input_tokens+output_tokens))
);
CREATE TABLE business.model_explanations (
 id uuid PRIMARY KEY,organization_id uuid NOT NULL,shop_id uuid NOT NULL,
 child_task_id uuid NOT NULL,
 parent_task_id uuid NOT NULL,report_id uuid NOT NULL,snapshot_id uuid NOT NULL,
 logical_key text NOT NULL UNIQUE,facts_hash text NOT NULL,body_hash text NOT NULL,
 result jsonb NOT NULL,canonical_result text NOT NULL,result_hash text NOT NULL,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 FOREIGN KEY(organization_id,shop_id,child_task_id)
 REFERENCES business.explanation_links(organization_id,shop_id,child_task_id),
 FOREIGN KEY(organization_id,shop_id,parent_task_id,report_id)
 REFERENCES business.analysis_reports(organization_id,shop_id,task_id,id),
 CHECK(canonical_result::jsonb=result),
 CHECK(result_hash=encode(sha256(convert_to(canonical_result,'UTF8')),'hex')),
 CHECK(result->>'facts_hash'=facts_hash)
);
CREATE TABLE business.explanation_task_results (
 child_task_id uuid PRIMARY KEY REFERENCES business.explanation_links(child_task_id),
 result_id uuid NOT NULL REFERENCES business.model_explanations(id)
);
"""


def upgrade() -> None:
    for statement in DDL.split(";"):
        if statement.strip():
            op.execute(statement)
    for table in (
        "explanation_links",
        "inventory_intent_requests",
        "inventory_intent_results",
        "model_calls",
        "model_call_observations",
        "model_explanations",
        "explanation_task_results",
    ):
        op.execute(f"""CREATE TRIGGER immutable_p204 BEFORE UPDATE OR DELETE ON business.{table}
        FOR EACH ROW EXECUTE FUNCTION business.reject_inventory_mutation()""")
        op.execute(f"""CREATE TRIGGER immutable_p204_truncate BEFORE TRUNCATE ON business.{table}
        FOR EACH STATEMENT EXECUTE FUNCTION business.reject_inventory_mutation()""")
    op.execute("""
CREATE FUNCTION business.bind_inventory_intent() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE t business.business_tasks; i business.inventory_intent_requests; tid uuid;
BEGIN
 tid=CASE WHEN TG_TABLE_NAME='model_calls' THEN (to_jsonb(NEW)->>'intent_task_id')::uuid ELSE
 (to_jsonb(NEW)->>'task_id')::uuid END;
 SELECT * INTO t FROM business.business_tasks WHERE id=tid FOR UPDATE;
 IF t.id IS NULL OR t.kind<>'inventory_intent_only'
 OR t.workflow_version<>'p204-inventory-routing-v1' OR t.thread_id<>t.id::text THEN
  RAISE EXCEPTION 'pinned inventory intent required' USING ERRCODE='23514';
 END IF;
 IF TG_TABLE_NAME='inventory_intent_requests' THEN
  IF t.state<>'queued' OR (t.organization_id,t.shop_id,t.requester_id) IS DISTINCT FROM
   (NEW.organization_id,NEW.shop_id,NEW.requester_id)
   OR t.normalized_request->>'logical_key' IS DISTINCT FROM NEW.logical_key
   OR t.normalized_request->>'body_hash' IS DISTINCT FROM NEW.body_hash
   OR t.normalized_request->>'facts_hash' IS DISTINCT FROM NEW.input_hash
   OR t.normalized_request->>'identity_id' IS DISTINCT FROM NEW.identity_id::text
   OR t.normalized_request->>'auth_version' IS DISTINCT FROM NEW.auth_version::text
   OR t.normalized_request->>'evidence_mode' IS DISTINCT FROM NEW.evidence_mode THEN
   RAISE EXCEPTION 'intent request binding required' USING ERRCODE='23514';
  END IF;
 ELSE
  SELECT * INTO i FROM business.inventory_intent_requests WHERE task_id=tid;
  IF t.state<>'analyzing' OR i.task_id IS NULL
   OR (NEW.organization_id,NEW.shop_id,NEW.logical_key) IS DISTINCT FROM
      (i.organization_id,i.shop_id,i.logical_key)
   OR (TG_TABLE_NAME='model_calls' AND
      (to_jsonb(NEW)->>'request_hash' IS DISTINCT FROM i.body_hash
       OR to_jsonb(NEW)->>'facts_hash' IS DISTINCT FROM i.input_hash
       OR to_jsonb(NEW)->>'stage_key' IS DISTINCT FROM CASE WHEN i.evidence_mode='actual_provider'
         THEN 'phase2-deepseek-20261010:actual' ELSE 'phase2-deepseek-20261010:offline' END))
   OR (TG_TABLE_NAME='inventory_intent_results' AND
      (to_jsonb(NEW)->>'body_hash' IS DISTINCT FROM i.body_hash
       OR to_jsonb(NEW)->>'input_hash' IS DISTINCT FROM i.input_hash)) THEN
   RAISE EXCEPTION 'intent evidence binding required' USING ERRCODE='23514';
  END IF;
 END IF;
 RETURN NEW;
END $$
""")
    for table in ("inventory_intent_requests", "inventory_intent_results"):
        op.execute(f"""CREATE TRIGGER bind_inventory_intent BEFORE INSERT ON business.{table}
        FOR EACH ROW EXECUTE FUNCTION business.bind_inventory_intent()""")
    op.execute("""CREATE TRIGGER bind_intent_call BEFORE INSERT ON business.model_calls
     FOR EACH ROW WHEN (NEW.intent_task_id IS NOT NULL)
     EXECUTE FUNCTION business.bind_inventory_intent()""")
    op.execute("""
CREATE FUNCTION business.bind_explanation_evidence() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE t business.business_tasks; l business.explanation_links;
BEGIN
 IF TG_TABLE_NAME='model_calls' AND (to_jsonb(NEW)->>'intent_task_id') IS NOT NULL THEN
  RETURN NEW;
 END IF;
 IF TG_TABLE_NAME='explanation_links' THEN
  SELECT * INTO t FROM business.business_tasks WHERE id=NEW.child_task_id FOR UPDATE;
  IF t.id IS NULL OR t.kind<>'report_explanation_only' OR t.state<>'queued'
   OR t.workflow_version<>'p204-report-explanation-v1' OR t.thread_id<>t.id::text
   OR (t.organization_id,t.shop_id,t.requester_id) IS DISTINCT FROM
      (NEW.organization_id,NEW.shop_id,NEW.requester_id)
   OR t.normalized_request->>'parent_task_id' IS DISTINCT FROM NEW.parent_task_id::text
   OR t.normalized_request->>'report_id' IS DISTINCT FROM NEW.report_id::text
   OR t.normalized_request->>'snapshot_id' IS DISTINCT FROM NEW.snapshot_id::text
   OR t.normalized_request->>'identity_id' IS DISTINCT FROM NEW.identity_id::text
   OR t.normalized_request->>'auth_version' IS DISTINCT FROM NEW.auth_version::text
   OR t.normalized_request->>'logical_key' IS DISTINCT FROM NEW.logical_key
   OR t.normalized_request->>'body_hash' IS DISTINCT FROM NEW.body_hash
   OR t.normalized_request->>'facts_hash' IS DISTINCT FROM NEW.facts_hash
   OR t.normalized_request->>'evidence_mode' IS DISTINCT FROM NEW.evidence_mode
   OR NOT EXISTS(SELECT 1 FROM business.analysis_reports a JOIN business.business_tasks p
     ON p.id=a.task_id WHERE a.id=NEW.report_id AND a.snapshot_id=NEW.snapshot_id
     AND a.task_id=NEW.parent_task_id AND a.organization_id=NEW.organization_id
     AND a.shop_id=NEW.shop_id AND a.facts_hash=NEW.facts_hash AND p.state='completed'
     AND p.requester_id=NEW.requester_id AND p.kind='inventory_analysis_only') THEN
   RAISE EXCEPTION 'explanation parent/task binding required' USING ERRCODE='23514';
  END IF;
 ELSIF TG_TABLE_NAME='explanation_task_results' THEN
  SELECT * INTO l FROM business.explanation_links WHERE child_task_id=NEW.child_task_id;
  SELECT * INTO t FROM business.business_tasks WHERE id=NEW.child_task_id FOR UPDATE;
  IF (t.state<>'analyzing' AND NOT (t.state='completed' AND EXISTS(SELECT 1
    FROM business.explanation_task_results r WHERE r.child_task_id=NEW.child_task_id
    AND r.result_id=NEW.result_id))) OR NOT EXISTS(SELECT 1 FROM business.model_explanations e
    WHERE e.id=NEW.result_id AND (e.organization_id,e.shop_id,e.parent_task_id,
     e.report_id,e.snapshot_id,e.logical_key,e.facts_hash,e.body_hash) IS NOT DISTINCT FROM
    (l.organization_id,l.shop_id,l.parent_task_id,l.report_id,l.snapshot_id,l.logical_key,
     l.facts_hash,l.body_hash)) THEN
   RAISE EXCEPTION 'explanation result binding required' USING ERRCODE='23514';
  END IF;
 ELSE
  SELECT * INTO l FROM business.explanation_links WHERE child_task_id=NEW.child_task_id;
  SELECT * INTO t FROM business.business_tasks WHERE id=NEW.child_task_id FOR UPDATE;
  IF t.state<>'analyzing' OR (NEW.organization_id,NEW.shop_id,NEW.logical_key,
      NEW.facts_hash) IS DISTINCT FROM (l.organization_id,l.shop_id,l.logical_key,l.facts_hash)
   OR (TG_TABLE_NAME='model_calls' AND
    (to_jsonb(NEW)->>'request_hash'<>l.body_hash
     OR to_jsonb(NEW)->>'stage_key'<>CASE WHEN l.evidence_mode='actual_provider'
      THEN 'phase2-deepseek-20261010:actual' ELSE 'phase2-deepseek-20261010:offline' END))
   OR (TG_TABLE_NAME='model_explanations' AND
    (to_jsonb(NEW)->>'body_hash'<>l.body_hash
     OR to_jsonb(NEW)->>'parent_task_id'<>l.parent_task_id::text
     OR to_jsonb(NEW)->>'report_id'<>l.report_id::text
     OR to_jsonb(NEW)->>'snapshot_id'<>l.snapshot_id::text)) THEN
   RAISE EXCEPTION 'explanation evidence binding required' USING ERRCODE='23514';
  END IF;
 END IF;
 RETURN NEW;
END $$
""")
    for table in (
        "explanation_links",
        "model_calls",
        "model_explanations",
        "explanation_task_results",
    ):
        op.execute(f"""CREATE TRIGGER bind_explanation BEFORE INSERT ON business.{table}
        FOR EACH ROW EXECUTE FUNCTION business.bind_explanation_evidence()""")
    op.execute("""
CREATE FUNCTION business.preserve_model_stage() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NEW.stage_key<>OLD.stage_key OR NEW.reserved_count<OLD.reserved_count
 OR NEW.reserved_nanos<OLD.reserved_nanos OR (OLD.halted AND NOT NEW.halted) THEN
  RAISE EXCEPTION 'stage budget cannot reset' USING ERRCODE='23514';
 END IF;
 RETURN NEW;
END $$
""")
    op.execute("""CREATE TRIGGER preserve_model_stage BEFORE UPDATE ON business.model_stage_budgets
    FOR EACH ROW EXECUTE FUNCTION business.preserve_model_stage()""")
    for operation in ("DELETE", "TRUNCATE"):
        level = "ROW" if operation == "DELETE" else "STATEMENT"
        op.execute(f"""CREATE TRIGGER immutable_stage_{operation.lower()} BEFORE {operation}
        ON business.model_stage_budgets FOR EACH {level}
        EXECUTE FUNCTION business.reject_inventory_mutation()""")
    op.execute("""
CREATE FUNCTION business.valid_explanation_result(task uuid,org uuid,shop uuid,version text)
 RETURNS boolean LANGUAGE sql STABLE AS $$
 SELECT EXISTS(SELECT 1 FROM business.explanation_task_results x
 JOIN business.explanation_links l ON l.child_task_id=x.child_task_id
 JOIN business.model_explanations e ON e.id=x.result_id
 JOIN business.business_tasks t ON t.id=x.child_task_id
 WHERE x.child_task_id=$1 AND l.organization_id=$2 AND l.shop_id=$3
 AND e.organization_id=l.organization_id AND e.shop_id=l.shop_id
 AND e.parent_task_id=l.parent_task_id AND e.report_id=l.report_id AND e.snapshot_id=l.snapshot_id
 AND e.logical_key=(l.logical_key) AND e.body_hash=l.body_hash AND e.facts_hash=l.facts_hash
 AND e.result->>'facts_hash'=l.facts_hash AND t.workflow_version=$4
 AND t.normalized_request->>'logical_key'=(l.logical_key)
 AND e.result_hash=encode(sha256(convert_to(e.canonical_result,'UTF8')),'hex'))
$$
""")
    op.execute("""
CREATE FUNCTION business.valid_inventory_intent(task uuid,org uuid,shop uuid,version text)
 RETURNS boolean LANGUAGE sql STABLE AS $$
 SELECT EXISTS(SELECT 1 FROM business.inventory_intent_results e
 JOIN business.inventory_intent_requests i ON i.task_id=e.task_id
 JOIN business.business_tasks t ON t.id=e.task_id
 WHERE e.task_id=$1 AND e.organization_id=$2 AND e.shop_id=$3 AND t.workflow_version=$4
 AND (e.organization_id,e.shop_id,e.logical_key,e.body_hash,e.input_hash) IS NOT DISTINCT FROM
 (i.organization_id,i.shop_id,i.logical_key,i.body_hash,i.input_hash)
 AND t.normalized_request->>'logical_key'=i.logical_key
 AND e.result_hash=encode(sha256(convert_to(e.canonical_result,'UTF8')),'hex'))
$$
""")
    op.execute("""
CREATE FUNCTION business.preserve_inventory_intent_task() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF TG_OP='INSERT' THEN
  IF NEW.kind='inventory_intent_only' AND
  (NEW.state<>'queued' OR NEW.workflow_version<>'p204-inventory-routing-v1') THEN
   RAISE EXCEPTION 'intent queued/version required' USING ERRCODE='23514';
  END IF;
  RETURN NEW;
 END IF;
 IF OLD.kind='inventory_intent_only' OR NEW.kind='inventory_intent_only' THEN
  IF (NEW.kind,NEW.normalized_request) IS DISTINCT FROM (OLD.kind,OLD.normalized_request)
   OR NEW.state NOT IN ('queued','analyzing','completed','failed','needs_attention')
   OR (OLD.state='completed' AND NEW.state<>OLD.state)
   OR (NEW.state='completed' AND NOT business.valid_inventory_intent(
     NEW.id,NEW.organization_id,NEW.shop_id,NEW.workflow_version)) THEN
   RAISE EXCEPTION 'intent receipt/immutable terminal required' USING ERRCODE='23514';
  END IF;
 END IF;
 RETURN NEW;
END $$
""")
    op.execute("""CREATE TRIGGER preserve_inventory_intent_task BEFORE INSERT OR UPDATE
    ON business.business_tasks FOR EACH ROW
    EXECUTE FUNCTION business.preserve_inventory_intent_task()""")
    op.execute("""
CREATE FUNCTION business.preserve_explanation_task() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF TG_OP='INSERT' THEN
  IF NEW.kind='report_explanation_only' AND
   (NEW.state<>'queued' OR NEW.workflow_version<>'p204-report-explanation-v1') THEN
   RAISE EXCEPTION 'explanation pinned queued task required' USING ERRCODE='23514';
  END IF;
  RETURN NEW;
 END IF;
 IF OLD.kind='report_explanation_only' OR NEW.kind='report_explanation_only' THEN
  IF (NEW.kind,NEW.normalized_request) IS DISTINCT FROM (OLD.kind,OLD.normalized_request)
   OR NEW.state NOT IN ('queued','analyzing','completed','failed','needs_attention')
   OR (OLD.state='completed' AND NEW.state<>OLD.state) THEN
   RAISE EXCEPTION 'explanation immutable identity/terminal' USING ERRCODE='23514';
  END IF;
  IF NEW.state='completed' AND NOT EXISTS(SELECT 1 FROM business.explanation_task_results r
   JOIN business.model_explanations e ON e.id=r.result_id
   JOIN business.explanation_links l ON l.child_task_id=r.child_task_id
   WHERE r.child_task_id=NEW.id AND l.organization_id=NEW.organization_id
   AND l.shop_id=NEW.shop_id AND e.logical_key=l.logical_key AND e.facts_hash=l.facts_hash) THEN
   RAISE EXCEPTION 'explanation durable result required' USING ERRCODE='23514';
  END IF;
 END IF;
 RETURN NEW;
END $$
""")
    op.execute("""CREATE TRIGGER preserve_explanation_task BEFORE INSERT OR UPDATE
    ON business.business_tasks
 FOR EACH ROW EXECUTE FUNCTION business.preserve_explanation_task()""")


def downgrade() -> None:
    raise RuntimeError("destructive downgrade disabled; restore verified backup")
