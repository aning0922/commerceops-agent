"""Dedicated inquiry request/result storage; awaits reviewed 0020 parent integration."""

from alembic import op

revision = "0021"
down_revision = "0020_p6_knowledge_copy"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(JSON_VALIDATOR)
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
 CHECK(business.valid_inquiry_request(request,shop_id,request_key,context_report_id) IS TRUE),
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
  AND result->>'workflow_version'=workflow_version) IS TRUE),
 CHECK(result IS NULL OR business.valid_inquiry_payload(
  result,result_canonical,result_hash,state,workflow_version,source_binding) IS TRUE)
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
 IF NOT (TG_OP='UPDATE' AND NEW.state='failed'
  AND business.inquiry_safe_failure(NEW.result) IS TRUE
  AND EXISTS(SELECT 1 FROM business.jobs j WHERE j.task_id=NEW.task_id
   AND j.organization_id=NEW.organization_id AND j.shop_id=NEW.shop_id
   AND j.kind='analyze' AND j.status='running' AND j.lease_owner IS NOT NULL)) AND (
 NOT business.lock_p3_permission(NEW.principal_id,NEW.organization_id,NEW.shop_id,
  NEW.identity_id,NEW.auth_version,'operator') OR NOT EXISTS(
  SELECT 1 FROM business.web_sessions s WHERE s.id=NEW.session_id AND s.kind='session'
   AND s.organization_id=NEW.organization_id AND s.principal_id=NEW.principal_id
   AND s.identity_id=NEW.identity_id AND s.auth_version=NEW.auth_version
   AND s.revoked_at IS NULL AND s.absolute_expires_at>clock_timestamp()
   AND s.idle_expires_at>clock_timestamp())) THEN
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
 AND business.valid_inquiry_request(i.request,i.shop_id,i.request_key,i.context_report_id) IS TRUE
 AND business.valid_inquiry_payload(i.result,i.result_canonical,i.result_hash,
  i.state,i.workflow_version,i.source_binding) IS TRUE)
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


JSON_VALIDATOR = r"""

CREATE FUNCTION business.inquiry_json_valid(v jsonb,s jsonb,root jsonb) RETURNS boolean
LANGUAGE plpgsql IMMUTABLE SET search_path=pg_catalog,business AS $$
DECLARE k text; x jsonb; typ text; ref text;
BEGIN
 IF v IS NULL OR s IS NULL THEN RETURN false; END IF;
 IF s ? '$ref' THEN
  ref := s->>'$ref';
  IF left(ref,8)<>'#/$defs/' THEN RETURN false; END IF;
  RETURN business.inquiry_json_valid(v,root->'$defs'->substr(ref,9),root);
 END IF;
 IF s ? 'anyOf' THEN
  FOR x IN SELECT value FROM jsonb_array_elements(s->'anyOf') LOOP
   IF business.inquiry_json_valid(v,x,root) IS TRUE THEN RETURN true; END IF;
  END LOOP; RETURN false;
 END IF;
 IF s ? 'const' AND v IS DISTINCT FROM s->'const' THEN RETURN false; END IF;
 IF s ? 'enum' AND NOT (s->'enum' @> jsonb_build_array(v)) THEN RETURN false; END IF;
 typ := s->>'type';
 IF typ IS NULL THEN RETURN false; END IF;
 IF typ='integer' THEN
  IF jsonb_typeof(v)<>'number' OR v::text !~ '^-?[0-9]+$' THEN RETURN false; END IF;
 ELSIF jsonb_typeof(v)<>typ THEN RETURN false;
 END IF;
 IF typ='object' THEN
  FOR k IN SELECT jsonb_array_elements_text(COALESCE(s->'required','[]')) LOOP
   IF NOT v ? k THEN RETURN false; END IF;
  END LOOP;
  FOR k,x IN SELECT * FROM jsonb_each(v) LOOP
   IF NOT (s->'properties') ? k THEN
    IF s->'additionalProperties'='false'::jsonb THEN RETURN false; END IF;
   ELSIF business.inquiry_json_valid(x,s->'properties'->k,root) IS NOT TRUE THEN
    RETURN false;
   END IF;
  END LOOP;
 ELSIF typ='array' THEN
  IF (s ? 'minItems' AND jsonb_array_length(v)<(s->>'minItems')::int)
   OR (s ? 'maxItems' AND jsonb_array_length(v)>(s->>'maxItems')::int) THEN RETURN false; END IF;
  FOR x IN SELECT value FROM jsonb_array_elements(v) LOOP
   IF business.inquiry_json_valid(x,s->'items',root) IS NOT TRUE THEN RETURN false; END IF;
  END LOOP;
 ELSIF typ='string' THEN
  k:=v#>>'{}';
  IF (s ? 'minLength' AND length(k)<(s->>'minLength')::int)
   OR (s ? 'maxLength' AND length(k)>(s->>'maxLength')::int)
   OR (s ? 'pattern' AND k !~ (s->>'pattern')) THEN RETURN false; END IF;
  IF s->>'format'='uuid' THEN PERFORM k::uuid;
  ELSIF s->>'format'='date-time' THEN
   IF k !~ '(Z|[+-][0-9]{2}:[0-9]{2})$' THEN RETURN false; END IF;
   PERFORM k::timestamptz;
  END IF;
 ELSIF typ IN ('integer','number') THEN
  IF (s ? 'minimum' AND v::text::numeric<(s->>'minimum')::numeric)
   OR (s ? 'maximum' AND v::text::numeric>(s->>'maximum')::numeric) THEN RETURN false; END IF;
 END IF;
 RETURN true;
EXCEPTION WHEN OTHERS THEN RETURN false;
END $$;
CREATE FUNCTION business.valid_inquiry_request(v jsonb,shop uuid,key uuid,report uuid)
RETURNS boolean LANGUAGE sql IMMUTABLE AS $$ SELECT (
 business.inquiry_json_valid(v,frozen.schema,frozen.schema)
 AND v->>'shop_id'=shop::text AND v->>'request_key'=key::text
 AND (v->>'context_report_id') IS NOT DISTINCT FROM report::text
 AND length(btrim(v->>'question'))>0) IS TRUE
 FROM (SELECT '{
 "additionalProperties": false,
 "properties": {
  "schema_version": {
   "const": "p6-inquiry-web-v1",
   "title": "Schema Version",
   "type": "string"
  },
  "shop_id": {
   "format": "uuid",
   "title": "Shop Id",
   "type": "string"
  },
  "question": {
   "maxLength": 2000,
   "minLength": 1,
   "title": "Question",
   "type": "string"
  },
  "context_report_id": {
   "anyOf": [
    {
     "format": "uuid",
     "type": "string"
    },
    {
     "type": "null"
    }
   ],
   "default": null,
   "title": "Context Report Id"
  },
  "request_key": {
   "format": "uuid",
   "title": "Request Key",
   "type": "string"
  }
 },
 "required": [
  "schema_version",
  "shop_id",
  "question",
  "request_key"
 ],
 "title": "CreateInquiry",
 "type": "object"
}'::jsonb AS schema) frozen $$;
CREATE FUNCTION business.inquiry_safe_failure(v jsonb) RETURNS boolean
LANGUAGE sql IMMUTABLE AS $$ SELECT (v->>'status'='access_denied'
 AND v->'model_calls'='0'::jsonb AND v->'tool_calls'='0'::jsonb
 AND v->'scanned_rows'='0'::jsonb AND v->'traces'='[]'::jsonb
 AND v->'results'='[]'::jsonb AND v->'claims'='[]'::jsonb
 AND v->'evidence_refs'='[]'::jsonb AND v->'clarification_options'='[]'::jsonb) IS TRUE $$;
CREATE FUNCTION business.valid_inquiry_payload(v jsonb,c text,h text,state text,w text,source text)
RETURNS boolean LANGUAGE plpgsql IMMUTABLE AS $$
DECLARE r jsonb; claim jsonb; reference jsonb; fact jsonb; win jsonb;
 schema jsonb := '{
 "$defs": {
  "Claim": {
   "additionalProperties": false,
   "properties": {
    "kind": {
     "enum": [
      "fact",
      "compare"
     ],
     "title": "Kind",
     "type": "string"
    },
    "refs": {
     "items": {
      "maxLength": 128,
      "minLength": 1,
      "type": "string"
     },
     "maxItems": 2,
     "minItems": 1,
     "title": "Refs",
     "type": "array"
    }
   },
   "required": [
    "kind",
    "refs"
   ],
   "title": "Claim",
   "type": "object"
  },
  "Fact": {
   "additionalProperties": false,
   "properties": {
    "evidence_id": {
     "maxLength": 128,
     "minLength": 1,
     "title": "Evidence Id",
     "type": "string"
    },
    "metric": {
     "enum": [
      "available_stock",
      "inbound_units",
      "sold_units",
      "order_net",
      "order_average",
      "refund_cohort"
     ],
     "title": "Metric",
     "type": "string"
    },
    "sku_key": {
     "anyOf": [
      {
       "maxLength": 128,
       "minLength": 1,
       "type": "string"
      },
      {
       "type": "null"
      }
     ],
     "default": null,
     "title": "Sku Key"
    },
    "window": {
     "anyOf": [
      {
       "$ref": "#/$defs/Window"
      },
      {
       "type": "null"
      }
     ],
     "default": null
    },
    "as_of": {
     "format": "date-time",
     "title": "As Of",
     "type": "string"
    },
    "quality_flags": {
     "default": [],
     "items": {
      "maxLength": 128,
      "minLength": 1,
      "type": "string"
     },
     "title": "Quality Flags",
     "type": "array"
    },
    "value": {
     "anyOf": [
      {
       "maxLength": 80,
       "type": "string"
      },
      {
       "type": "null"
      }
     ],
     "title": "Value"
    },
    "unit": {
     "maxLength": 128,
     "minLength": 1,
     "title": "Unit",
     "type": "string"
    },
    "currency": {
     "anyOf": [
      {
       "pattern": "^[A-Z]{3}$",
       "type": "string"
      },
      {
       "type": "null"
      }
     ],
     "default": null,
     "title": "Currency"
    }
   },
   "required": [
    "evidence_id",
    "metric",
    "as_of",
    "value",
    "unit"
   ],
   "title": "Fact",
   "type": "object"
  },
  "ProductMatch": {
   "additionalProperties": false,
   "properties": {
    "sku_key": {
     "maxLength": 128,
     "minLength": 1,
     "title": "Sku Key",
     "type": "string"
    },
    "label": {
     "anyOf": [
      {
       "maxLength": 80,
       "minLength": 1,
       "type": "string"
      },
      {
       "type": "null"
      }
     ],
     "default": null,
     "title": "Label"
    }
   },
   "required": [
    "sku_key"
   ],
   "title": "ProductMatch",
   "type": "object"
  },
  "ReadResult": {
   "additionalProperties": false,
   "properties": {
    "tool_call_id": {
     "maxLength": 128,
     "minLength": 1,
     "title": "Tool Call Id",
     "type": "string"
    },
    "shop_id": {
     "maxLength": 128,
     "minLength": 1,
     "title": "Shop Id",
     "type": "string"
    },
    "source_binding": {
     "maxLength": 128,
     "minLength": 1,
     "title": "Source Binding",
     "type": "string"
    },
    "snapshot_id": {
     "maxLength": 128,
     "minLength": 1,
     "title": "Snapshot Id",
     "type": "string"
    },
    "report_id": {
     "anyOf": [
      {
       "maxLength": 128,
       "minLength": 1,
       "type": "string"
      },
      {
       "type": "null"
      }
     ],
     "default": null,
     "title": "Report Id"
    },
    "as_of": {
     "format": "date-time",
     "title": "As Of",
     "type": "string"
    },
    "complete": {
     "title": "Complete",
     "type": "boolean"
    },
    "quality_flags": {
     "default": [],
     "items": {
      "maxLength": 128,
      "minLength": 1,
      "type": "string"
     },
     "title": "Quality Flags",
     "type": "array"
    },
    "scanned_rows": {
     "minimum": 0,
     "title": "Scanned Rows",
     "type": "integer"
    },
    "sku_keys": {
     "items": {
      "maxLength": 128,
      "minLength": 1,
      "type": "string"
     },
     "maxItems": 100,
     "title": "Sku Keys",
     "type": "array"
    },
    "products": {
     "default": [],
     "items": {
      "$ref": "#/$defs/ProductMatch"
     },
     "maxItems": 100,
     "title": "Products",
     "type": "array"
    },
    "facts": {
     "default": [],
     "items": {
      "$ref": "#/$defs/Fact"
     },
     "maxItems": 100,
     "title": "Facts",
     "type": "array"
    },
    "windows": {
     "default": [],
     "items": {
      "$ref": "#/$defs/Window"
     },
     "maxItems": 2,
     "title": "Windows",
     "type": "array"
    }
   },
   "required": [
    "tool_call_id",
    "shop_id",
    "source_binding",
    "snapshot_id",
    "as_of",
    "complete",
    "scanned_rows",
    "sku_keys"
   ],
   "title": "ReadResult",
   "type": "object"
  },
  "TraceRead": {
   "additionalProperties": false,
   "properties": {
    "tool_call_id": {
     "maxLength": 128,
     "minLength": 1,
     "title": "Tool Call Id",
     "type": "string"
    },
    "name": {
     "enum": [
      "commerce.read_products",
      "commerce.read_orders",
      "commerce.read_inventory",
      "reports.read"
     ],
     "title": "Name",
     "type": "string"
    },
    "args_hash": {
     "pattern": "^[a-f0-9]{64}$",
     "title": "Args Hash",
     "type": "string"
    }
   },
   "required": [
    "tool_call_id",
    "name",
    "args_hash"
   ],
   "title": "TraceRead",
   "type": "object"
  },
  "Window": {
   "additionalProperties": false,
   "properties": {
    "start": {
     "format": "date-time",
     "title": "Start",
     "type": "string"
    },
    "end": {
     "format": "date-time",
     "title": "End",
     "type": "string"
    }
   },
   "required": [
    "start",
    "end"
   ],
   "title": "Window",
   "type": "object"
  }
 },
 "additionalProperties": false,
 "properties": {
  "schema_version": {
   "const": "p6-inquiry-result-v1",
   "default": "p6-inquiry-result-v1",
   "title": "Schema Version",
   "type": "string"
  },
  "status": {
   "enum": [
    "complete",
    "clarify",
    "unsupported",
    "insufficient_evidence",
    "invalid_response",
    "source_incomplete",
    "access_denied",
    "budget_exceeded",
    "timeout",
    "tool_denied"
   ],
   "title": "Status",
   "type": "string"
  },
  "model_calls": {
   "maximum": 3,
   "minimum": 0,
   "title": "Model Calls",
   "type": "integer"
  },
  "tool_calls": {
   "maximum": 4,
   "minimum": 0,
   "title": "Tool Calls",
   "type": "integer"
  },
  "scanned_rows": {
   "minimum": 0,
   "title": "Scanned Rows",
   "type": "integer"
  },
  "traces": {
   "items": {
    "$ref": "#/$defs/TraceRead"
   },
   "maxItems": 4,
   "title": "Traces",
   "type": "array"
  },
  "results": {
   "items": {
    "$ref": "#/$defs/ReadResult"
   },
   "maxItems": 4,
   "title": "Results",
   "type": "array"
  },
  "evidence_refs": {
   "items": {
    "type": "string"
   },
   "maxItems": 100,
   "title": "Evidence Refs",
   "type": "array"
  },
  "claims": {
   "items": {
    "$ref": "#/$defs/Claim"
   },
   "maxItems": 100,
   "title": "Claims",
   "type": "array"
  },
  "clarification_options": {
   "items": {
    "$ref": "#/$defs/ProductMatch"
   },
   "maxItems": 100,
   "title": "Clarification Options",
   "type": "array"
  },
  "evidence_mode": {
   "const": "offline_stub",
   "default": "offline_stub",
   "title": "Evidence Mode",
   "type": "string"
  },
  "workflow_version": {
   "const": "p6-readonly-inquiry-v1",
   "default": "p6-readonly-inquiry-v1",
   "title": "Workflow Version",
   "type": "string"
  }
 },
 "required": [
  "status",
  "model_calls",
  "tool_calls",
  "scanned_rows",
  "traces",
  "results",
  "evidence_refs",
  "claims",
  "clarification_options"
 ],
 "title": "ResultPayload",
 "type": "object"
}'::jsonb;
BEGIN
 IF (business.inquiry_json_valid(v,schema,schema)
  AND c::jsonb=v AND octet_length(c)<=1048576
  AND h=encode(sha256(convert_to(c,'UTF8')),'hex')
  AND w='p6-readonly-inquiry-v1' AND v->>'workflow_version'=w
  AND v->>'schema_version'='p6-inquiry-result-v1'
  AND v->>'evidence_mode'='offline_stub'
  AND state=CASE WHEN v->>'status' IN ('complete','clarify','unsupported','insufficient_evidence')
    THEN 'completed' ELSE 'failed' END
  AND jsonb_array_length(v->'traces')=(v->>'tool_calls')::int
  AND (v->>'scanned_rows')::int<=10000
  AND (v->>'status'='complete' OR (v->'results'='[]'::jsonb
    AND v->'claims'='[]'::jsonb AND v->'evidence_refs'='[]'::jsonb))
  AND (v->>'status'='clarify' OR v->'clarification_options'='[]'::jsonb)) IS NOT TRUE
 THEN RETURN false; END IF;
 IF v->>'status'='complete' AND (jsonb_array_length(v->'results')=0
  OR jsonb_array_length(v->'evidence_refs')=0 OR jsonb_array_length(v->'claims')=0)
 THEN RETURN false; END IF;
 IF (SELECT count(*) FROM jsonb_array_elements(v->'traces')) <>
  (SELECT count(DISTINCT t->>'tool_call_id') FROM jsonb_array_elements(v->'traces') t)
 THEN RETURN false; END IF;
 FOR reference IN SELECT value FROM jsonb_array_elements(v->'evidence_refs') LOOP
  IF NOT EXISTS(SELECT 1 FROM jsonb_array_elements(v->'results') r,
   jsonb_array_elements(r->'facts') f WHERE f->'evidence_id'=reference)
  THEN RETURN false; END IF;
 END LOOP;
 FOR claim IN SELECT value FROM jsonb_array_elements(v->'claims') LOOP
  IF jsonb_array_length(claim->'refs')<>
   CASE WHEN claim->>'kind'='fact' THEN 1 ELSE 2 END THEN RETURN false; END IF;
  FOR reference IN SELECT value FROM jsonb_array_elements(claim->'refs') LOOP
   IF NOT (v->'evidence_refs' @> jsonb_build_array(reference)) THEN RETURN false; END IF;
  END LOOP;
 END LOOP;
 FOR r IN SELECT value FROM jsonb_array_elements(v->'results') LOOP
  IF (r->'complete'='true'::jsonb AND r->>'source_binding'=source
   AND EXISTS(SELECT 1 FROM jsonb_array_elements(v->'traces') t
    WHERE t->>'tool_call_id'=r->>'tool_call_id')) IS NOT TRUE THEN RETURN false; END IF;
  FOR win IN SELECT value FROM jsonb_array_elements(r->'windows') LOOP
   IF ((win->>'end')::timestamptz>(win->>'start')::timestamptz) IS NOT TRUE
   THEN RETURN false; END IF;
  END LOOP;
  FOR fact IN SELECT value FROM jsonb_array_elements(r->'facts') LOOP
   IF (jsonb_typeof(fact->'sku_key')='string'
    AND r->'sku_keys' @> jsonb_build_array(fact->'sku_key')) IS NOT TRUE
   THEN RETURN false; END IF;
   IF fact->'window'<>'null'::jsonb AND NOT (r->'windows' @> jsonb_build_array(fact->'window'))
   THEN RETURN false; END IF;
   IF fact->>'metric' IN ('sold_units','order_net','order_average','refund_cohort') AND
    (jsonb_typeof(fact->'window')='object' AND jsonb_typeof(fact->'currency')='string')
     IS NOT TRUE THEN RETURN false; END IF;
   IF fact->'value'<>'null'::jsonb AND (fact->>'value') !~
    '^[+-]?([0-9]+([.][0-9]*)?|[.][0-9]+)([eE][+-]?[0-9]+)?$'
   THEN RETURN false; END IF;
  END LOOP;
 END LOOP;
 RETURN true;
EXCEPTION WHEN OTHERS THEN RETURN false;
END $$;
"""
