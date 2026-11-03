"""Dedicated inquiry request/result storage; awaits reviewed 0020 parent integration."""

from alembic import op

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE business.readonly_inquiries (
 task_id uuid PRIMARY KEY,
 organization_id uuid NOT NULL, shop_id uuid NOT NULL, principal_id uuid NOT NULL,
 session_id uuid NOT NULL REFERENCES business.web_sessions(id),
 identity_id uuid NOT NULL, auth_version bigint NOT NULL CHECK(auth_version>0),
 request_key uuid NOT NULL, request_hash text NOT NULL CHECK(request_hash ~ '^[a-f0-9]{64}$'),
 request jsonb NOT NULL CHECK(jsonb_typeof(request)='object'),
 source_binding text NOT NULL CHECK(source_binding ~ '^[a-f0-9]{64}$'),
 source_domain jsonb NOT NULL CHECK(jsonb_typeof(source_domain)='object'),
 evidence_mode text NOT NULL CHECK(evidence_mode='offline_stub'),
 workflow_version text NOT NULL CHECK(workflow_version='p6-readonly-inquiry-v1'),
 context_report_id uuid,
 state text NOT NULL DEFAULT 'queued' CHECK(state IN ('queued','analyzing','completed','failed')),
 result jsonb, result_canonical text, result_hash text,
 version integer NOT NULL DEFAULT 1 CHECK(version>0),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 UNIQUE(principal_id,request_key),
 FOREIGN KEY(organization_id,shop_id,task_id)
  REFERENCES business.business_tasks(organization_id,shop_id,id),
 FOREIGN KEY(organization_id,principal_id) REFERENCES business.principals(organization_id,id),
 FOREIGN KEY(organization_id,identity_id,principal_id)
  REFERENCES business.identities(organization_id,id,principal_id),
 CHECK(request->>'schema_version'='p6-inquiry-web-v1'),
 CHECK(request->>'shop_id'=shop_id::text AND request->>'request_key'=request_key::text),
 CHECK((request->>'context_report_id') IS NOT DISTINCT FROM context_report_id::text),
 CHECK((state IN ('completed','failed'))=(result IS NOT NULL)),
 CHECK((result IS NULL)=(result_canonical IS NULL) AND (result IS NULL)=(result_hash IS NULL)),
 CHECK(result IS NULL OR (jsonb_typeof(result)='object'
  AND octet_length(result_canonical)<=1048576
  AND result_canonical::jsonb=result
  AND result_hash=encode(sha256(convert_to(result_canonical,'UTF8')),'hex')
  AND result->>'schema_version'='p6-inquiry-result-v1'
  AND result->>'evidence_mode'='offline_stub'
  AND result->>'workflow_version'=workflow_version))
)""")
    op.execute("""CREATE FUNCTION business.guard_readonly_inquiry() RETURNS trigger
 LANGUAGE plpgsql SET search_path=pg_catalog,business AS $$ BEGIN
 IF TG_OP IN ('DELETE','TRUNCATE') THEN
  RAISE EXCEPTION 'inquiry history is immutable' USING ERRCODE='23514';
 END IF;
 IF TG_OP='UPDATE' AND (
  (to_jsonb(OLD)-ARRAY['state','result','result_canonical','result_hash','version','updated_at'])
  IS DISTINCT FROM
  (to_jsonb(NEW)-ARRAY['state','result','result_canonical','result_hash','version','updated_at'])
  OR OLD.result IS NOT NULL OR NEW.version<>OLD.version+1
  OR NOT ((OLD.state='queued' AND NEW.state IN ('analyzing','failed'))
    OR (OLD.state='analyzing' AND NEW.state IN ('analyzing','completed','failed')))) THEN
  RAISE EXCEPTION 'inquiry update is invalid' USING ERRCODE='23514';
 END IF;
 IF NOT EXISTS(SELECT 1 FROM business.business_tasks t WHERE t.id=NEW.task_id
  AND t.organization_id=NEW.organization_id AND t.shop_id=NEW.shop_id
  AND t.requester_id=NEW.principal_id AND t.kind='readonly_inquiry'
  AND t.workflow_version=NEW.workflow_version AND t.normalized_request=NEW.request) THEN
  RAISE EXCEPTION 'inquiry task binding is invalid' USING ERRCODE='23514';
 END IF;
 IF NOT business.lock_p3_permission(NEW.principal_id,NEW.organization_id,NEW.shop_id,
  NEW.identity_id,NEW.auth_version,'operator') OR NOT EXISTS(
  SELECT 1 FROM business.web_sessions s WHERE s.id=NEW.session_id AND s.kind='session'
   AND s.organization_id=NEW.organization_id AND s.principal_id=NEW.principal_id
   AND s.identity_id=NEW.identity_id AND s.auth_version=NEW.auth_version
   AND s.revoked_at IS NULL AND s.absolute_expires_at>clock_timestamp()
   AND s.idle_expires_at>clock_timestamp()) THEN
  RAISE EXCEPTION 'inquiry permission is invalid' USING ERRCODE='23514';
 END IF;
 RETURN NEW; END $$""")
    op.execute("""CREATE TRIGGER readonly_inquiry_guard BEFORE INSERT OR UPDATE OR DELETE
 ON business.readonly_inquiries FOR EACH ROW EXECUTE FUNCTION business.guard_readonly_inquiry()""")
    op.execute("""CREATE TRIGGER readonly_inquiry_no_truncate BEFORE TRUNCATE
 ON business.readonly_inquiries FOR EACH STATEMENT
 EXECUTE FUNCTION business.guard_readonly_inquiry()""")
    op.execute("""CREATE FUNCTION business.valid_readonly_inquiry_result(
 task uuid,org uuid,shop uuid,workflow text) RETURNS boolean LANGUAGE sql STABLE AS $$
 SELECT EXISTS(SELECT 1 FROM business.readonly_inquiries i
 JOIN business.business_tasks t ON t.id=i.task_id AND t.organization_id=i.organization_id
 AND t.shop_id=i.shop_id WHERE i.task_id=$1 AND i.organization_id=$2 AND i.shop_id=$3
 AND i.workflow_version=$4 AND t.workflow_version=$4 AND t.kind='readonly_inquiry'
 AND t.requester_id=i.principal_id AND t.normalized_request=i.request
 AND i.state IN ('completed','failed') AND i.result IS NOT NULL
 AND i.result_canonical::jsonb=i.result
 AND i.result_hash=encode(sha256(convert_to(i.result_canonical,'UTF8')),'hex'))
 $$""")
    op.execute("""CREATE FUNCTION business.guard_readonly_inquiry_task() RETURNS trigger
 LANGUAGE plpgsql SET search_path=pg_catalog,business AS $$ BEGIN
 IF TG_OP='INSERT' THEN
  IF NEW.kind='readonly_inquiry' AND (NEW.state<>'queued'
   OR NEW.workflow_version<>'p6-readonly-inquiry-v1') THEN
   RAISE EXCEPTION 'inquiry must start queued with pinned workflow' USING ERRCODE='23514';
  END IF;
  RETURN NEW;
 END IF;
 IF OLD.kind='readonly_inquiry' OR NEW.kind='readonly_inquiry' THEN
  IF (NEW.kind,NEW.normalized_request) IS DISTINCT FROM (OLD.kind,OLD.normalized_request)
   OR (OLD.state IN ('completed','failed') AND NEW.state<>OLD.state)
   OR NEW.state NOT IN ('queued','analyzing','completed','failed','needs_attention') THEN
   RAISE EXCEPTION 'inquiry task update is invalid' USING ERRCODE='23514';
  END IF;
  IF NEW.state IN ('completed','failed') AND (
   NOT business.valid_readonly_inquiry_result(
    NEW.id,NEW.organization_id,NEW.shop_id,NEW.workflow_version)
   OR NOT EXISTS(SELECT 1 FROM business.readonly_inquiries i
    WHERE i.task_id=NEW.id AND i.state=NEW.state)) THEN
   RAISE EXCEPTION 'inquiry completion requires durable result' USING ERRCODE='23514';
  END IF;
 END IF;
 RETURN NEW; END $$""")
    op.execute("""CREATE TRIGGER readonly_inquiry_task_guard BEFORE INSERT OR UPDATE
 ON business.business_tasks FOR EACH ROW
 EXECUTE FUNCTION business.guard_readonly_inquiry_task()""")
    op.execute("REVOKE ALL ON business.readonly_inquiries FROM PUBLIC")
    op.execute("""DO $$ BEGIN IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='commerceops_app') THEN
 GRANT SELECT,INSERT ON business.readonly_inquiries TO commerceops_app;
 GRANT UPDATE(state,result,result_canonical,result_hash,version,updated_at)
 ON business.readonly_inquiries TO commerceops_app;
 REVOKE DELETE,TRUNCATE ON business.readonly_inquiries FROM commerceops_app;
 END IF; END $$""")


def downgrade() -> None:
    raise RuntimeError("destructive downgrade disabled; restore reviewed backup")
