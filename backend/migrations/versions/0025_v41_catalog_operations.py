"""V41 six-table foundation. Runtime mutation functions follow as a separately reviewed slice."""

from alembic import op

revision = "0025_v41_catalog_operations"
down_revision = "0024_v4_demo_foundation"
branch_labels = None
depends_on = None

TABLES = (
    "product_tags",
    "order_fulfillments",
    "import_jobs",
    "import_products",
    "action_receipts",
    "action_events",
)
IDENTITY = """
 tenant_id uuid NOT NULL,
 organization_id uuid NOT NULL,
 shop_id uuid NOT NULL,
 owner_session_id uuid NOT NULL,
 principal_id uuid NOT NULL,
 reset_epoch bigint NOT NULL CHECK(reset_epoch>=0),
 auth_generation bigint NOT NULL CHECK(auth_generation>=0)
"""
LINKS = """
 FOREIGN KEY(tenant_id,organization_id) REFERENCES business.v4_demo_tenants(id,organization_id),
 FOREIGN KEY(tenant_id,shop_id) REFERENCES business.v4_demo_shops(tenant_id,shop_id),
 FOREIGN KEY(owner_session_id,tenant_id) REFERENCES business.v4_demo_sessions(id,tenant_id),
 FOREIGN KEY(organization_id,principal_id) REFERENCES business.principals(organization_id,id)
"""
RECEIPT_LINK = """
 FOREIGN KEY(receipt_id,tenant_id,shop_id,owner_session_id,principal_id,reset_epoch,auth_generation)
 REFERENCES business.v41_action_receipts
 (id,tenant_id,shop_id,owner_session_id,principal_id,reset_epoch,auth_generation)
 DEFERRABLE INITIALLY DEFERRED
"""

DDL = f"""
CREATE TABLE business.v41_security_policy (
 singleton boolean PRIMARY KEY DEFAULT true CHECK(singleton),
 active_version text NOT NULL CHECK(active_version ~ '^[A-Za-z0-9_.-]{{1,80}}$'),
 config_digest text NOT NULL CHECK(config_digest ~ '^[a-f0-9]{{64}}$'),
 generation bigint NOT NULL CHECK(generation>0),
 activated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 retired_versions text[] NOT NULL DEFAULT '{{}}' CHECK(cardinality(retired_versions)<=64),
 CHECK(array_position(retired_versions,active_version) IS NULL),
 CHECK(array_position(retired_versions,NULL) IS NULL)
);
CREATE TABLE business.v41_action_receipts (
 id uuid PRIMARY KEY,
 {IDENTITY},
 operation text NOT NULL CHECK(operation IN('product_tags','order_fulfillment','import_confirm')),
 canonical_request text NOT NULL CHECK(octet_length(canonical_request)<=8192),
 request_id uuid NOT NULL,
 payload_digest text NOT NULL CHECK(payload_digest ~ '^[a-f0-9]{{64}}$'),
 resource_id uuid NOT NULL,
 resource_version integer NOT NULL CHECK(resource_version>0),
 before_revision text NOT NULL CHECK(before_revision ~ '^[a-f0-9]{{64}}$'),
 after_revision text NOT NULL CHECK(after_revision ~ '^[a-f0-9]{{64}}$'),
 effect_count integer NOT NULL CHECK(effect_count BETWEEN 1 AND 500),
 committed_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 retain_until timestamptz NOT NULL,
 UNIQUE(owner_session_id,operation,request_id),
 UNIQUE(id,tenant_id,shop_id,owner_session_id,principal_id,reset_epoch,auth_generation),
 {LINKS},
 CHECK(jsonb_typeof(canonical_request::jsonb)='object'),
 CHECK(payload_digest=encode(sha256(convert_to(canonical_request,'UTF8')),'hex')),
 CHECK(retain_until>committed_at)
);
CREATE TABLE business.v41_import_jobs (
 id uuid PRIMARY KEY,
 {IDENTITY},
 preview_key uuid NOT NULL,
 request_digest text NOT NULL CHECK(request_digest ~ '^[a-f0-9]{{64}}$'),
 file_digest text NOT NULL CHECK(file_digest ~ '^[a-f0-9]{{64}}$'),
 data_revision text NOT NULL CHECK(data_revision ~ '^[a-f0-9]{{64}}$'),
 parser_version text NOT NULL CHECK(parser_version='v41-parser-1'),
 import_schema_version text NOT NULL CHECK(import_schema_version='v41-import-1'),
 requested_parent_job_id uuid,
 parent_job_id uuid UNIQUE,
 chain_version integer NOT NULL CHECK(chain_version BETWEEN 1 AND 5),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 expires_at timestamptz NOT NULL,
 retain_until timestamptz NOT NULL,
 parse_state text NOT NULL CHECK(parse_state IN('RESERVED','RUNNING','UNKNOWN','STOPPED')),
 parse_slot smallint CHECK(parse_slot IN(0,1)),
 lease_digest text NOT NULL CHECK(lease_digest ~ '^[a-f0-9]{{64}}$'),
 process_ref uuid NOT NULL,
 parse_pid integer CHECK(parse_pid>0),
 stop_proof jsonb,
 preview_data jsonb,
 canonical_preview text CHECK(octet_length(canonical_preview)<=1048576),
 normalized_rows jsonb,
 canonical_normalized text CHECK(octet_length(canonical_normalized)<=524288),
 normalized_digest text CHECK(normalized_digest ~ '^[a-f0-9]{{64}}$'),
 mapping_digest text CHECK(mapping_digest ~ '^[a-f0-9]{{64}}$'),
 job_digest text CHECK(job_digest ~ '^[a-f0-9]{{64}}$'),
 UNIQUE(owner_session_id,preview_key),
 UNIQUE(id,tenant_id,shop_id,owner_session_id,principal_id,reset_epoch,auth_generation),
 FOREIGN KEY(requested_parent_job_id,tenant_id,shop_id,owner_session_id,principal_id,
 reset_epoch,auth_generation) REFERENCES business.v41_import_jobs
 (id,tenant_id,shop_id,owner_session_id,principal_id,reset_epoch,auth_generation),
 FOREIGN KEY(parent_job_id,tenant_id,shop_id,owner_session_id,principal_id,
 reset_epoch,auth_generation) REFERENCES business.v41_import_jobs
 (id,tenant_id,shop_id,owner_session_id,principal_id,reset_epoch,auth_generation),
 {LINKS},
 CHECK(expires_at>created_at AND expires_at<=created_at+interval '10 minutes'),
 CHECK(retain_until>expires_at),
 CHECK((parse_state='STOPPED')=(parse_slot IS NULL)),
 CHECK(stop_proof IS NULL OR jsonb_typeof(stop_proof)='object'),
 CHECK(parse_state<>'STOPPED' OR coalesce(stop_proof @> '{{"reaped":true}}'::jsonb,false)),
 CHECK(preview_data IS NULL OR (parse_state='STOPPED'
  AND canonical_preview IS NOT NULL AND normalized_rows IS NOT NULL
  AND canonical_normalized IS NOT NULL
  AND preview_data=canonical_preview::jsonb AND jsonb_typeof(preview_data)='object'
  AND normalized_rows=canonical_normalized::jsonb AND jsonb_typeof(normalized_rows)='array'
  AND jsonb_array_length(normalized_rows)<=500 AND normalized_digest IS NOT NULL
  AND mapping_digest IS NOT NULL AND job_digest IS NOT NULL
  AND parent_job_id IS NOT DISTINCT FROM requested_parent_job_id))
);
-- No expiry predicate: orphaned/unknown live processes retain capacity until proof of stop.
CREATE UNIQUE INDEX v41_global_parse_slot ON business.v41_import_jobs(parse_slot)
 WHERE parse_state IN('RESERVED','RUNNING','UNKNOWN');
CREATE UNIQUE INDEX v41_tenant_parse_slot ON business.v41_import_jobs(tenant_id)
 WHERE parse_state IN('RESERVED','RUNNING','UNKNOWN');
CREATE INDEX v41_preview_owner ON business.v41_import_jobs(tenant_id,reset_epoch,auth_generation);

CREATE TABLE business.v41_product_tags (
 {IDENTITY},
 product_id uuid NOT NULL,
 version integer NOT NULL CHECK(version>0),
 tags jsonb NOT NULL CHECK(jsonb_typeof(tags)='array' AND jsonb_array_length(tags)<=8),
 canonical_payload text NOT NULL CHECK(octet_length(canonical_payload)<=4096),
 payload_digest text NOT NULL CHECK(payload_digest ~ '^[a-f0-9]{{64}}$'),
 receipt_id uuid NOT NULL,
 PRIMARY KEY(tenant_id,shop_id,reset_epoch,product_id),
 {LINKS}, {RECEIPT_LINK},
 CHECK(payload_digest=encode(sha256(convert_to(canonical_payload,'UTF8')),'hex'))
);
CREATE TABLE business.v41_order_fulfillments (
 {IDENTITY},
 order_id uuid NOT NULL,
 version integer NOT NULL CHECK(version=1),
 status text NOT NULL CHECK(status='demo_fulfilled'),
 canonical_payload text NOT NULL CHECK(octet_length(canonical_payload)<=4096),
 payload_digest text NOT NULL CHECK(payload_digest ~ '^[a-f0-9]{{64}}$'),
 receipt_id uuid NOT NULL,
 PRIMARY KEY(tenant_id,shop_id,reset_epoch,order_id),
 {LINKS}, {RECEIPT_LINK},
 CHECK(payload_digest=encode(sha256(convert_to(canonical_payload,'UTF8')),'hex'))
);
CREATE TABLE business.v41_import_products (
 {IDENTITY},
 product_id uuid NOT NULL,
 sku_id uuid NOT NULL,
 job_id uuid NOT NULL,
 import_row integer NOT NULL CHECK(import_row BETWEEN 2 AND 501),
 canonical_sku text NOT NULL CHECK(canonical_sku ~ '^[a-z0-9][a-z0-9_.-]{{0,63}}$'),
 content jsonb NOT NULL CHECK(jsonb_typeof(content)='object'),
 canonical_payload text NOT NULL CHECK(octet_length(canonical_payload)<=16384),
 payload_digest text NOT NULL CHECK(payload_digest ~ '^[a-f0-9]{{64}}$'),
 receipt_id uuid NOT NULL,
 PRIMARY KEY(tenant_id,shop_id,reset_epoch,product_id),
 UNIQUE(tenant_id,shop_id,reset_epoch,sku_id),
 UNIQUE(tenant_id,shop_id,reset_epoch,canonical_sku),
 UNIQUE(job_id,import_row),
 FOREIGN KEY(job_id,tenant_id,shop_id,owner_session_id,principal_id,reset_epoch,auth_generation)
 REFERENCES business.v41_import_jobs
 (id,tenant_id,shop_id,owner_session_id,principal_id,reset_epoch,auth_generation),
 {LINKS}, {RECEIPT_LINK},
 CHECK(product_id<>sku_id),
 CHECK(payload_digest=encode(sha256(convert_to(canonical_payload,'UTF8')),'hex'))
);
CREATE TABLE business.v41_action_events (
 id uuid PRIMARY KEY,
 {IDENTITY},
 receipt_id uuid NOT NULL UNIQUE,
 event_kind text NOT NULL CHECK(event_kind IN('product_tags','order_fulfillment','import_confirm')),
 resource_id uuid NOT NULL,
 resource_version integer NOT NULL CHECK(resource_version>0),
 effect_count integer NOT NULL CHECK(effect_count BETWEEN 1 AND 500),
 effect_digest text NOT NULL CHECK(effect_digest ~ '^[a-f0-9]{{64}}$'),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 {LINKS}, {RECEIPT_LINK}
);
"""

FUNCTIONS = r"""
CREATE FUNCTION business.v41_canonical(value jsonb) RETURNS text LANGUAGE plpgsql IMMUTABLE
SET search_path=pg_catalog,business AS $$
DECLARE output text;
BEGIN
 CASE jsonb_typeof(value)
 WHEN 'object' THEN
  SELECT '{'||coalesce(string_agg(to_jsonb(e.key)::text||':'||business.v41_canonical(e.value),
   ',' ORDER BY e.key COLLATE "C"),'')||'}' INTO output FROM jsonb_each(value) e;
 WHEN 'array' THEN
  SELECT '['||coalesce(string_agg(business.v41_canonical(e.value),',' ORDER BY e.n),'')||']'
   INTO output FROM jsonb_array_elements(value) WITH ORDINALITY e(value,n);
 ELSE output:=value::text;
 END CASE;
 RETURN output;
END $$;
CREATE FUNCTION business.v41_hash(value jsonb) RETURNS text LANGUAGE sql IMMUTABLE
SET search_path=pg_catalog,business AS $$
 SELECT encode(sha256(convert_to(business.v41_canonical(value),'UTF8')),'hex')
$$;
CREATE FUNCTION business.v41_utc(value timestamptz) RETURNS text LANGUAGE sql IMMUTABLE
SET search_path=pg_catalog AS $$
 SELECT to_char(value AT TIME ZONE 'UTC',CASE WHEN extract(microseconds FROM value)::bigint
 %1000000=0 THEN 'YYYY-MM-DD"T"HH24:MI:SS"Z"' ELSE 'YYYY-MM-DD"T"HH24:MI:SS.US"Z"' END)
$$;
CREATE FUNCTION business.v41_scope(tid uuid,shop uuid,epoch bigint) RETURNS jsonb
LANGUAGE sql STABLE SET search_path=pg_catalog,business AS $$
 SELECT jsonb_build_object('tenant_id',tid,'shop_id',shop,'reset_epoch',epoch,
  'template_key',m.template_key) FROM business.v4_demo_shops m
 WHERE m.tenant_id=tid AND m.shop_id=shop
$$;
CREATE FUNCTION business.v41_revision(tid uuid,shop uuid,epoch bigint) RETURNS text
LANGUAGE sql STABLE SET search_path=pg_catalog,business AS $$
 SELECT business.v41_hash(jsonb_build_object('fixture_digest',t.fixture_digest,
 'scope',business.v41_scope(tid,shop,epoch),'effects',coalesce((
  SELECT jsonb_agg(jsonb_build_object('kind',e.kind,'object_id',e.object_id,'version',e.version,
   'payload_digest',e.payload_digest) ORDER BY e.kind COLLATE "C",e.object_id)
  FROM (
   SELECT 'product_tags'::text kind,product_id object_id,version,payload_digest
    FROM business.v41_product_tags WHERE tenant_id=tid AND shop_id=shop AND reset_epoch=epoch
   UNION ALL SELECT 'order_fulfillment',order_id,version,payload_digest
    FROM business.v41_order_fulfillments WHERE tenant_id=tid AND shop_id=shop AND reset_epoch=epoch
   UNION ALL SELECT 'import_confirm',product_id,1,payload_digest
    FROM business.v41_import_products WHERE tenant_id=tid AND shop_id=shop AND reset_epoch=epoch
  ) e),'[]'::jsonb))) FROM business.v4_demo_tenants t WHERE t.id=tid AND t.reset_epoch=epoch
$$;

CREATE FUNCTION business.v41_actor(bearer text,csrf text,binding text,shop uuid,epoch bigint,
 generation bigint,
 writing boolean) RETURNS business.v4_demo_sessions LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog,business AS $$
DECLARE sid uuid; tid uuid; t business.v4_demo_tenants; s business.v4_demo_sessions;
 p business.principals; w business.web_sessions; token_digest text; allowed boolean;
 policy business.v41_security_policy;
BEGIN
 IF writing IS NULL THEN RAISE EXCEPTION 'INVALID_REQUEST' USING ERRCODE='23514'; END IF;
 IF bearer IS NULL OR bearer !~ '^v4d_[A-Za-z0-9_-]{43}$' THEN
  RAISE EXCEPTION 'SESSION_INVALID' USING ERRCODE='23514'; END IF;
 token_digest:=encode(sha256(convert_to(bearer,'UTF8')),'hex');
 SELECT id,tenant_id INTO sid,tid FROM business.v4_demo_sessions WHERE token_hash=token_digest;
 IF tid IS NULL THEN RAISE EXCEPTION 'SESSION_INVALID' USING ERRCODE='23514'; END IF;
 SELECT * INTO t FROM business.v4_demo_tenants WHERE id=tid FOR UPDATE;
 SELECT * INTO s FROM business.v4_demo_sessions WHERE id=sid AND tenant_id=tid FOR UPDATE;
 IF t.id IS NULL OR s.id IS NULL OR t.revoked_at IS NOT NULL OR s.revoked_at IS NOT NULL
  OR s.expires_at<>t.expires_at OR clock_timestamp()>=t.expires_at OR s.reset_epoch<>t.reset_epoch
  OR NOT EXISTS(SELECT 1 FROM business.v4_demo_personas a WHERE a.tenant_id=tid
   AND a.organization_id=t.organization_id AND a.persona_id=s.persona_id
   AND a.principal_id=s.principal_id AND a.identity_id=s.identity_id)
 THEN RAISE EXCEPTION 'SESSION_INVALID' USING ERRCODE='23514'; END IF;
 IF epoch IS DISTINCT FROM s.reset_epoch THEN
  RAISE EXCEPTION 'EPOCH_CHANGED' USING ERRCODE='23514'; END IF;
 IF generation IS DISTINCT FROM s.auth_generation THEN
  RAISE EXCEPTION 'GENERATION_CHANGED' USING ERRCODE='23514'; END IF;
 -- Match the V40 resolver's principal/bound-session order, then hold identity and credential.
 SELECT a.* INTO p FROM business.principals a WHERE a.id=s.principal_id
  AND a.organization_id=t.organization_id FOR SHARE;
 IF p.id IS NULL OR NOT p.enabled OR p.auth_version<>s.auth_version THEN
  RAISE EXCEPTION 'SESSION_INVALID' USING ERRCODE='23514'; END IF;
 SELECT * INTO w FROM business.web_sessions WHERE id=s.bound_web_session_id FOR UPDATE;
 IF w.id IS NULL OR w.kind<>'session' OR w.revoked_at IS NOT NULL
  OR (w.organization_id,w.principal_id,w.identity_id,w.auth_version) IS DISTINCT FROM
   (t.organization_id,s.principal_id,s.identity_id,s.auth_version)
  OR w.key_version<>s.key_version OR w.token_hash=token_digest
  OR least(w.absolute_expires_at,w.idle_expires_at)<=clock_timestamp()
  OR greatest(w.absolute_expires_at,w.idle_expires_at)>s.expires_at THEN
  RAISE EXCEPTION 'SESSION_INVALID' USING ERRCODE='23514'; END IF;
 IF binding IS NULL OR octet_length(binding)>256 OR w.csrf_digest IS DISTINCT FROM
  encode(sha256(convert_to(binding,'UTF8')),'hex') THEN
  RAISE EXCEPTION 'SESSION_INVALID' USING ERRCODE='23514'; END IF;
 PERFORM 1 FROM business.identities i WHERE i.id=s.identity_id AND i.provider='web'
  AND i.organization_id=t.organization_id AND i.principal_id=s.principal_id FOR SHARE;
 IF NOT FOUND THEN RAISE EXCEPTION 'SESSION_INVALID' USING ERRCODE='23514'; END IF;
 PERFORM 1 FROM business.web_credentials c WHERE c.identity_id=s.identity_id
  AND c.organization_id=t.organization_id AND c.principal_id=s.principal_id AND c.enabled FOR SHARE;
 IF NOT FOUND THEN RAISE EXCEPTION 'SESSION_INVALID' USING ERRCODE='23514'; END IF;
 SELECT * INTO policy FROM business.v41_security_policy WHERE singleton FOR SHARE;
 IF policy.singleton IS NULL THEN
  RAISE EXCEPTION 'SERVICE_UNAVAILABLE' USING ERRCODE='23514'; END IF;
 IF s.key_version IS DISTINCT FROM policy.active_version THEN
  RAISE EXCEPTION 'SESSION_INVALID' USING ERRCODE='23514'; END IF;
 IF writing AND (csrf IS NULL OR octet_length(csrf)>256 OR s.csrf_digest<>
  encode(sha256(convert_to(csrf,'UTF8')),'hex')) THEN
  RAISE EXCEPTION 'CSRF_INVALID' USING ERRCODE='23514'; END IF;
 IF NOT EXISTS(SELECT 1 FROM business.v4_demo_shops m WHERE m.tenant_id=tid AND m.shop_id=shop)
 THEN RAISE EXCEPTION 'RESOURCE_NOT_FOUND' USING ERRCODE='23514'; END IF;
 allowed:=business.lock_p3_permission(p.id,t.organization_id,shop,s.identity_id,s.auth_version,
  'operator');
 IF NOT writing AND NOT allowed THEN allowed:=business.lock_p3_permission(p.id,t.organization_id,
  shop,s.identity_id,s.auth_version,'approver'); END IF;
 IF NOT allowed THEN RAISE EXCEPTION 'ACCESS_DENIED' USING ERRCODE='23514'; END IF;
 RETURN s;
END $$;
"""

SIGNATURES = (
    "v41_canonical(jsonb)",
    "v41_hash(jsonb)",
    "v41_utc(timestamptz)",
    "v41_scope(uuid,uuid,bigint)",
    "v41_revision(uuid,uuid,bigint)",
    "v41_actor(text,text,text,uuid,bigint,bigint,boolean)",
)

ACTION_FUNCTIONS = r"""
CREATE FUNCTION business.v41_tags_valid(value jsonb) RETURNS boolean LANGUAGE sql IMMUTABLE
SET search_path=pg_catalog,business AS $$
 SELECT CASE WHEN jsonb_typeof(value) IS DISTINCT FROM 'array' THEN false
 ELSE jsonb_array_length(value)<=8 AND NOT EXISTS(
  SELECT 1 FROM jsonb_array_elements(value) e WHERE jsonb_typeof(e) IS DISTINCT FROM 'string'
  OR length(e#>>'{}') NOT BETWEEN 1 AND 24 OR btrim(e#>>'{}')<>e#>>'{}'
  OR (e#>>'{}') ~ '[[:cntrl:]]' OR normalize(e#>>'{}',NFC)<>e#>>'{}')
 AND (SELECT count(*)=count(DISTINCT e) FROM jsonb_array_elements(value) e) END
$$;
CREATE FUNCTION business.v41_product_valid(value jsonb,currency text) RETURNS boolean
LANGUAGE sql IMMUTABLE SET search_path=pg_catalog,business AS $$
 SELECT coalesce(jsonb_typeof(value)='object'
 AND value ?& ARRAY['sku','canonical_sku','title','price','currency','tags']
 AND value-ARRAY['sku','canonical_sku','title','price','currency','tags']='{}'::jsonb
 AND jsonb_typeof(value->'sku')='string' AND value->>'sku' ~ '^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$'
 AND jsonb_typeof(value->'canonical_sku')='string'
 AND value->>'canonical_sku'=lower(value->>'sku' COLLATE "C")
 AND jsonb_typeof(value->'title')='string' AND length(value->>'title') BETWEEN 1 AND 120
 AND btrim(value->>'title')=value->>'title' AND (value->>'title') !~ '[[:cntrl:]]'
 AND normalize(value->>'title',NFC)=value->>'title'
 AND jsonb_typeof(value->'price')='string'
 AND value->>'price' ~ '^(0|[1-9][0-9]{0,13})(\.[0-9]{0,5}[1-9])?$'
 AND jsonb_typeof(value->'currency')='string' AND value->>'currency'=currency
 AND business.v41_tags_valid(value->'tags'),false)
$$;
CREATE FUNCTION business.v41_request_body(canonical text,operation text,target uuid) RETURNS jsonb
LANGUAGE plpgsql IMMUTABLE SET search_path=pg_catalog,business AS $$
DECLARE req jsonb; body jsonb; allowed text[]; path text; field text;
BEGIN
 IF octet_length(canonical)>8192 THEN
  RAISE EXCEPTION 'INVALID_REQUEST' USING ERRCODE='23514'; END IF;
 req:=canonical::jsonb;
 path:=CASE operation WHEN 'product_tags' THEN '/api/v4/products/'||target||'/tags'
  WHEN 'order_fulfillment' THEN '/api/v4/orders/'||target||'/fulfillment'
  WHEN 'import_confirm' THEN '/api/v4/imports/'||target||'/confirm' ELSE NULL END;
 IF path IS NULL OR jsonb_typeof(req) IS DISTINCT FROM 'object'
  OR req-ARRAY['method','path','body']<>'{}'::jsonb
  OR req->>'method' IS DISTINCT FROM 'POST' OR req->>'path' IS DISTINCT FROM path
  OR canonical IS DISTINCT FROM business.v41_canonical(req) THEN
  RAISE EXCEPTION 'INVALID_REQUEST' USING ERRCODE='23514'; END IF;
 body:=req->'body';
 allowed:=ARRAY['shop_id','request_key','expected_epoch','expected_generation',
  'expected_data_revision']
  ||CASE operation WHEN 'product_tags' THEN ARRAY['expected_version','tags']
   WHEN 'order_fulfillment' THEN ARRAY['expected_version','action']
   ELSE ARRAY['expected_job_version','expected_job_digest'] END;
 IF jsonb_typeof(body) IS DISTINCT FROM 'object' OR NOT(body ?& allowed)
  OR body-allowed<>'{}'::jsonb OR jsonb_typeof(body->'expected_data_revision') IS DISTINCT FROM
  'string'
  OR body->>'expected_data_revision' !~ '^[a-f0-9]{64}$' THEN
  RAISE EXCEPTION 'INVALID_REQUEST' USING ERRCODE='23514'; END IF;
 FOREACH field IN ARRAY ARRAY['shop_id','request_key'] LOOP
  IF jsonb_typeof(body->field) IS DISTINCT FROM 'string' OR
   (body->>field)::uuid::text IS DISTINCT FROM body->>field THEN
   RAISE EXCEPTION 'INVALID_REQUEST' USING ERRCODE='23514'; END IF;
 END LOOP;
 FOREACH field IN ARRAY ARRAY['expected_epoch','expected_generation']||
  CASE WHEN operation='import_confirm' THEN ARRAY['expected_job_version']
   ELSE ARRAY['expected_version'] END LOOP
  IF jsonb_typeof(body->field) IS DISTINCT FROM 'number'
   OR body->>field !~ '^(0|[1-9][0-9]{0,8})$' THEN
   RAISE EXCEPTION 'INVALID_REQUEST' USING ERRCODE='23514'; END IF;
 END LOOP;
 IF operation='product_tags' AND NOT business.v41_tags_valid(body->'tags') THEN
  RAISE EXCEPTION 'INVALID_REQUEST' USING ERRCODE='23514'; END IF;
 IF operation='order_fulfillment' AND body->>'action' IS DISTINCT FROM 'mark_demo_fulfilled' THEN
  RAISE EXCEPTION 'INVALID_REQUEST' USING ERRCODE='23514'; END IF;
 IF operation='import_confirm' AND (jsonb_typeof(body->'expected_job_digest') IS DISTINCT FROM
  'string'
  OR body->>'expected_job_digest' !~ '^[a-f0-9]{64}$'
  OR (body->>'expected_job_version')::integer NOT BETWEEN 1 AND 5) THEN
  RAISE EXCEPTION 'INVALID_REQUEST' USING ERRCODE='23514'; END IF;
 RETURN body;
END $$;
CREATE FUNCTION business.v41_template(tid uuid,shop uuid) RETURNS jsonb
LANGUAGE sql STABLE SET search_path=pg_catalog,business AS $$
 SELECT item FROM business.v4_demo_tenants t
 JOIN business.v4_demo_fixture_versions f ON f.version=t.fixture_version AND
  f.content_hash=t.fixture_digest
 JOIN business.v4_demo_shops m ON m.tenant_id=t.id AND m.shop_id=shop
 CROSS JOIN LATERAL jsonb_array_elements(f.content->'shops') item
 WHERE t.id=tid AND item->>'shop_key'=m.template_key
$$;
CREATE FUNCTION business.v41_effect_summary(receipt uuid) RETURNS jsonb LANGUAGE sql STABLE
SET search_path=pg_catalog,business AS $$
 SELECT jsonb_build_object('count',count(*),'digest',business.v41_hash(coalesce(
  jsonb_agg(jsonb_build_object('kind',e.kind,'object_id',e.object_id,'payload_digest',
  e.payload_digest)
    ORDER BY e.kind COLLATE "C",e.object_id),'[]'::jsonb))) FROM (
  SELECT 'product_tags'::text kind,product_id object_id,payload_digest
   FROM business.v41_product_tags WHERE receipt_id=receipt
  UNION ALL SELECT 'order_fulfillment',order_id,payload_digest
   FROM business.v41_order_fulfillments WHERE receipt_id=receipt
  UNION ALL SELECT 'import_confirm',product_id,payload_digest
   FROM business.v41_import_products WHERE receipt_id=receipt
 ) e
$$;
CREATE FUNCTION business.v41_preview_digest(job business.v41_import_jobs) RETURNS text
LANGUAGE sql STABLE SET search_path=pg_catalog,business AS $$
 SELECT business.v41_hash(jsonb_build_object('scope',jsonb_build_object(
  'tenant_id',(job).tenant_id,'shop_id',(job).shop_id,'owner_session_id',(job).owner_session_id,
  'principal_id',(job).principal_id,'reset_epoch',(job).reset_epoch,
  'auth_generation',(job).auth_generation,'data_revision',(job).data_revision,
  'session_expires_at',business.v41_utc(s.expires_at)),
  'data',(job).preview_data#-'{job,job_digest}',
  'normalized_digest',(job).normalized_digest,'request_digest',(job).request_digest,
  'mapping_digest',(job).mapping_digest))
 FROM business.v4_demo_sessions s WHERE s.id=(job).owner_session_id
$$;
CREATE FUNCTION business.v41_apply_action(bearer text,csrf text,binding text,canonical text,
 operation text,
  target uuid)
RETURNS business.v41_action_receipts LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog,business AS $$
DECLARE body jsonb; s business.v4_demo_sessions; t business.v4_demo_tenants;
 old business.v41_action_receipts; result business.v41_action_receipts;
 prior business.v41_product_tags; j business.v41_import_jobs;
 shop uuid; rid uuid; before text; after text; template jsonb; payload jsonb;
 version integer; effect_count integer:=1; product jsonb; normalized jsonb; record jsonb;
 product_id uuid; sku_id uuid; row_number integer:=1; summary jsonb; org uuid;
BEGIN
 body:=business.v41_request_body(canonical,operation,target);
 shop:=(body->>'shop_id')::uuid;
 s:=business.v41_actor(bearer,csrf,binding,shop,(body->>'expected_epoch')::bigint,
  (body->>'expected_generation')::bigint,true);
 SELECT * INTO t FROM business.v4_demo_tenants WHERE id=s.tenant_id;
 org:=t.organization_id;
 SELECT * INTO old FROM business.v41_action_receipts r WHERE r.owner_session_id=s.id
  AND r.operation=v41_apply_action.operation AND r.request_id=(body->>'request_key')::uuid;
 IF old.id IS NOT NULL THEN
  IF old.canonical_request<>canonical OR (old.tenant_id,old.shop_id,old.principal_id,
   old.reset_epoch,old.auth_generation) IS DISTINCT FROM
   (s.tenant_id,shop,s.principal_id,s.reset_epoch,s.auth_generation) THEN
   RAISE EXCEPTION 'IDEMPOTENCY_CONFLICT' USING ERRCODE='23514'; END IF;
  RETURN old;
 END IF;
 before:=business.v41_revision(s.tenant_id,shop,s.reset_epoch);
 IF before IS DISTINCT FROM body->>'expected_data_revision' THEN
  RAISE EXCEPTION 'SNAPSHOT_CHANGED' USING ERRCODE='23514'; END IF;
 template:=business.v41_template(s.tenant_id,shop);
 IF template IS NULL THEN RAISE EXCEPTION 'SERVICE_UNAVAILABLE' USING ERRCODE='23514'; END IF;
 rid:=gen_random_uuid();
 IF operation='product_tags' THEN
  IF NOT EXISTS(SELECT 1 FROM jsonb_array_elements(template->'products') p
    WHERE p->'ref'->>'id'=target::text) AND NOT EXISTS(
    SELECT 1 FROM business.v41_import_products p WHERE p.tenant_id=s.tenant_id AND p.shop_id=shop
    AND p.reset_epoch=s.reset_epoch AND p.product_id=target) THEN
   RAISE EXCEPTION 'RESOURCE_NOT_FOUND' USING ERRCODE='23514'; END IF;
  SELECT * INTO prior FROM business.v41_product_tags p WHERE p.tenant_id=s.tenant_id
   AND p.shop_id=shop AND p.reset_epoch=s.reset_epoch AND p.product_id=target FOR UPDATE;
  IF coalesce(prior.version,0)<>(body->>'expected_version')::integer THEN
   RAISE EXCEPTION 'VERSION_CONFLICT' USING ERRCODE='23514'; END IF;
  version:=coalesce(prior.version,0)+1;
  payload:=jsonb_build_object('scope',business.v41_scope(s.tenant_id,shop,s.reset_epoch),
    'product_id',target,'version',version,'tags',body->'tags');
  INSERT INTO business.v41_product_tags(tenant_id,organization_id,shop_id,owner_session_id,
   principal_id,reset_epoch,auth_generation,product_id,version,tags,canonical_payload,
  payload_digest,receipt_id)
  VALUES(s.tenant_id,org,shop,s.id,s.principal_id,s.reset_epoch,s.auth_generation,target,version,
   body->'tags',business.v41_canonical(payload),business.v41_hash(payload),rid)
  ON CONFLICT ON CONSTRAINT v41_product_tags_pkey DO UPDATE SET
   owner_session_id=EXCLUDED.owner_session_id,principal_id=EXCLUDED.principal_id,
   auth_generation=EXCLUDED.auth_generation,version=EXCLUDED.version,tags=EXCLUDED.tags,
   canonical_payload=EXCLUDED.canonical_payload,payload_digest=EXCLUDED.payload_digest,
   receipt_id=EXCLUDED.receipt_id;
 ELSIF operation='order_fulfillment' THEN
  SELECT p INTO product FROM jsonb_array_elements(template->'orders') p WHERE
  p->'ref'->>'id'=target::text;
  IF product IS NULL THEN RAISE EXCEPTION 'RESOURCE_NOT_FOUND' USING ERRCODE='23514'; END IF;
  IF jsonb_typeof(product->'paid_at') IS DISTINCT FROM 'string' THEN
   RAISE EXCEPTION 'PAYMENT_STATE_UNKNOWN' USING ERRCODE='23514'; END IF;
  IF (body->>'expected_version')::integer<>0 OR EXISTS(SELECT 1 FROM
  business.v41_order_fulfillments f
   WHERE f.tenant_id=s.tenant_id AND f.shop_id=shop AND f.reset_epoch=s.reset_epoch AND
  f.order_id=target)
  THEN RAISE EXCEPTION 'STATE_CONFLICT' USING ERRCODE='23514'; END IF;
  version:=1;
  payload:=jsonb_build_object('scope',business.v41_scope(s.tenant_id,shop,s.reset_epoch),
   'order_id',target,'version',1,'status','demo_fulfilled');
  INSERT INTO business.v41_order_fulfillments(tenant_id,organization_id,shop_id,owner_session_id,
   principal_id,reset_epoch,auth_generation,order_id,version,status,canonical_payload,
  payload_digest,receipt_id)
  VALUES(s.tenant_id,org,shop,s.id,s.principal_id,s.reset_epoch,s.auth_generation,target,1,
   'demo_fulfilled',business.v41_canonical(payload),business.v41_hash(payload),rid);
 ELSE
  SELECT * INTO j FROM business.v41_import_jobs i WHERE i.id=target AND i.tenant_id=s.tenant_id
   AND i.shop_id=shop AND i.owner_session_id=s.id AND i.principal_id=s.principal_id
   AND i.reset_epoch=s.reset_epoch AND i.auth_generation IS NOT DISTINCT FROM s.auth_generation
   FOR UPDATE;
  IF j.id IS NULL THEN RAISE EXCEPTION 'RESOURCE_NOT_FOUND' USING ERRCODE='23514'; END IF;
  IF j.parse_state<>'STOPPED' OR j.preview_data->>'state' IS DISTINCT FROM 'READY'
   OR j.preview_data->'confirmable' IS DISTINCT FROM 'true'::jsonb
   OR EXISTS(SELECT 1 FROM business.v41_import_jobs child WHERE child.parent_job_id=j.id)
   OR EXISTS(SELECT 1 FROM business.v41_action_receipts r WHERE r.operation='import_confirm'
    AND r.resource_id=j.id) THEN
   RAISE EXCEPTION 'STATE_CONFLICT' USING ERRCODE='23514'; END IF;
  IF clock_timestamp()>=j.expires_at THEN
   RAISE EXCEPTION 'IMPORT_EXPIRED' USING ERRCODE='23514'; END IF;
  IF j.data_revision IS DISTINCT FROM before OR j.data_revision IS DISTINCT FROM
  body->>'expected_data_revision'
   OR j.parser_version<>'v41-parser-1' OR j.import_schema_version<>'v41-import-1' THEN
   RAISE EXCEPTION 'SNAPSHOT_CHANGED' USING ERRCODE='23514'; END IF;
  IF j.chain_version<>(body->>'expected_job_version')::integer
   OR j.job_digest IS DISTINCT FROM body->>'expected_job_digest' THEN
   RAISE EXCEPTION 'VERSION_CONFLICT' USING ERRCODE='23514'; END IF;
  IF j.job_digest IS DISTINCT FROM business.v41_preview_digest(j)
   OR j.file_digest IS DISTINCT FROM j.preview_data->>'file_digest'
   OR j.job_digest IS DISTINCT FROM j.preview_data->'job'->>'job_digest'
   OR j.id::text IS DISTINCT FROM j.preview_data->'job'->>'import_job_id'
   OR j.chain_version::text IS DISTINCT FROM j.preview_data->'job'->>'version'
   OR j.data_revision IS DISTINCT FROM j.preview_data->'job'->>'data_revision'
   OR j.parser_version IS DISTINCT FROM j.preview_data->'job'->>'parser_version'
   OR j.import_schema_version IS DISTINCT FROM j.preview_data->'job'->>'import_schema_version'
   OR business.v41_utc(j.expires_at) IS DISTINCT FROM j.preview_data->'job'->>'expires_at'
   OR j.mapping_digest IS DISTINCT FROM business.v41_hash(jsonb_build_object(
    'mapping',j.preview_data->'mapping','mapping_version',1)) THEN
   RAISE EXCEPTION 'VERSION_CONFLICT' USING ERRCODE='23514'; END IF;
  normalized:=jsonb_build_object('rows',j.normalized_rows,'parser_version',j.parser_version,
   'import_schema_version',j.import_schema_version);
  IF j.normalized_digest IS DISTINCT FROM business.v41_hash(normalized)
   OR jsonb_typeof(j.normalized_rows) IS DISTINCT FROM 'array'
   OR jsonb_array_length(j.normalized_rows) NOT BETWEEN 1 AND 500 THEN
   RAISE EXCEPTION 'IMPORT_INVALID' USING ERRCODE='23514'; END IF;
  effect_count:=jsonb_array_length(j.normalized_rows);
  IF effect_count+(SELECT count(*) FROM business.v41_import_products p WHERE p.tenant_id=s.tenant_id
   AND p.shop_id=shop AND p.reset_epoch=s.reset_epoch)>500 THEN
   RAISE EXCEPTION 'LIMIT_EXCEEDED' USING ERRCODE='23514'; END IF;
  FOR record IN SELECT value FROM jsonb_array_elements(j.normalized_rows) LOOP
   row_number:=row_number+1;
   IF NOT business.v41_product_valid(record,template->>'currency') OR EXISTS(
    SELECT 1 FROM jsonb_array_elements(template->'skus') p
     WHERE lower(p->>'label' COLLATE "C")=record->>'canonical_sku') OR EXISTS(
    SELECT 1 FROM business.v41_import_products p WHERE p.tenant_id=s.tenant_id AND p.shop_id=shop
     AND p.reset_epoch=s.reset_epoch AND p.canonical_sku=record->>'canonical_sku') THEN
    RAISE EXCEPTION 'IMPORT_INVALID' USING ERRCODE='23514'; END IF;
   product_id:=gen_random_uuid(); sku_id:=gen_random_uuid();
   payload:=jsonb_build_object('scope',business.v41_scope(s.tenant_id,shop,s.reset_epoch),
    'product_id',product_id,'sku_id',sku_id,'import_job_id',j.id,'import_row',row_number,
    'file_digest',j.file_digest,'product',record);
   INSERT INTO business.v41_import_products(tenant_id,organization_id,shop_id,owner_session_id,
    principal_id,reset_epoch,auth_generation,product_id,sku_id,job_id,import_row,canonical_sku,
    content,canonical_payload,payload_digest,receipt_id)
   VALUES(s.tenant_id,org,shop,s.id,s.principal_id,s.reset_epoch,s.auth_generation,product_id,
  sku_id,
    j.id,row_number,record->>'canonical_sku',record,business.v41_canonical(payload),
  business.v41_hash(payload),rid);
  END LOOP;
  version:=j.chain_version;
 END IF;
 after:=business.v41_revision(s.tenant_id,shop,s.reset_epoch);
 summary:=business.v41_effect_summary(rid);
 INSERT INTO business.v41_action_receipts(id,tenant_id,organization_id,shop_id,owner_session_id,
  principal_id,reset_epoch,auth_generation,operation,canonical_request,request_id,payload_digest,
  resource_id,resource_version,before_revision,after_revision,effect_count,retain_until)
 VALUES(rid,s.tenant_id,org,shop,s.id,s.principal_id,s.reset_epoch,s.auth_generation,operation,
  canonical,
  (body->>'request_key')::uuid,encode(sha256(convert_to(canonical,'UTF8')),'hex'),target,version,
  before,after,effect_count,t.retain_until) RETURNING * INTO result;
 INSERT INTO business.v41_action_events(id,tenant_id,organization_id,shop_id,owner_session_id,
  principal_id,reset_epoch,auth_generation,receipt_id,event_kind,resource_id,resource_version,
  effect_count,effect_digest)
 VALUES(gen_random_uuid(),s.tenant_id,org,shop,s.id,s.principal_id,s.reset_epoch,s.auth_generation,
  rid,operation,target,version,effect_count,summary->>'digest');
 IF NOT business.lock_p3_permission(s.principal_id,org,shop,s.identity_id,s.auth_version,
  'operator') THEN
  RAISE EXCEPTION 'ACCESS_DENIED' USING ERRCODE='23514'; END IF;
 IF clock_timestamp()>=s.expires_at THEN RAISE EXCEPTION 'SESSION_INVALID' USING
  ERRCODE='23514'; END IF;
 RETURN result;
END $$;
"""

ACTION_SIGNATURES = (
    "v41_tags_valid(jsonb)",
    "v41_product_valid(jsonb,text)",
    "v41_request_body(text,text,uuid)",
    "v41_template(uuid,uuid)",
    "v41_effect_summary(uuid)",
    "v41_preview_digest(business.v41_import_jobs)",
    "v41_apply_action(text,text,text,text,text,uuid)",
)

GUARDS = r"""
CREATE FUNCTION business.v41_policy_guard() RETURNS trigger LANGUAGE plpgsql
SET search_path=pg_catalog,business AS $$
BEGIN
 IF TG_OP IN('DELETE','TRUNCATE') THEN
  RAISE EXCEPTION 'V41_POLICY_IMMUTABLE' USING ERRCODE='23514'; END IF;
 IF current_user<>pg_get_userbyid((SELECT relowner FROM pg_class WHERE oid=TG_RELID)) THEN
  RAISE EXCEPTION 'V41_OWNER_REQUIRED' USING ERRCODE='23514'; END IF;
 IF TG_OP='INSERT' THEN
  IF NEW.generation<>1 OR cardinality(NEW.retired_versions)<>0 THEN
   RAISE EXCEPTION 'V41_POLICY_TRANSITION' USING ERRCODE='23514'; END IF;
 ELSE
  IF NEW.generation<>OLD.generation+1 OR NEW.active_version=OLD.active_version
   OR NEW.active_version=ANY(OLD.retired_versions)
   OR NEW.retired_versions IS DISTINCT FROM OLD.retired_versions||OLD.active_version
   OR NEW.activated_at<OLD.activated_at THEN
   RAISE EXCEPTION 'V41_POLICY_TRANSITION' USING ERRCODE='23514'; END IF;
 END IF;
 RETURN NEW;
END $$;
CREATE FUNCTION business.v41_mutation_guard() RETURNS trigger LANGUAGE plpgsql
SET search_path=pg_catalog,business AS $$
DECLARE n jsonb; o jsonb; deadline timestamptz; payload jsonb; j business.v41_import_jobs;
BEGIN
 IF TG_OP='TRUNCATE' THEN RAISE EXCEPTION 'V41_HISTORY_IMMUTABLE' USING ERRCODE='23514'; END IF;
 IF current_user<>pg_get_userbyid((SELECT relowner FROM pg_class WHERE oid=TG_RELID)) THEN
  RAISE EXCEPTION 'V41_DIRECT_WRITE_DENIED' USING ERRCODE='23514'; END IF;
 IF TG_OP='DELETE' THEN
  SELECT retain_until INTO deadline FROM business.v4_demo_tenants WHERE id=OLD.tenant_id;
  IF deadline IS NULL OR clock_timestamp()<deadline OR EXISTS(
   SELECT 1 FROM business.v41_import_jobs p WHERE p.tenant_id=OLD.tenant_id AND
  p.parse_state<>'STOPPED') THEN
   RAISE EXCEPTION 'V41_RETENTION_OR_PROCESS_HOLD' USING ERRCODE='23514'; END IF;
  RETURN OLD;
 END IF;
 n:=to_jsonb(NEW);
 IF TG_OP='UPDATE' THEN
  o:=to_jsonb(OLD);
  IF TG_TABLE_NAME='v41_product_tags' THEN
   IF (n-ARRAY['principal_id','auth_generation','version','tags','canonical_payload',
  'payload_digest','receipt_id'])
    <>(o-ARRAY['principal_id','auth_generation','version','tags','canonical_payload',
  'payload_digest','receipt_id'])
    OR NEW.version<>OLD.version+1 OR NEW.receipt_id=OLD.receipt_id THEN
    RAISE EXCEPTION 'V41_TAG_TRANSITION' USING ERRCODE='23514'; END IF;
  ELSIF TG_TABLE_NAME='v41_import_jobs' THEN
   IF (n-ARRAY['parse_state','parse_slot','parse_pid','stop_proof','parent_job_id','preview_data',
      'canonical_preview','normalized_rows','canonical_normalized','normalized_digest',
  'mapping_digest','job_digest'])
    <>(o-ARRAY['parse_state','parse_slot','parse_pid','stop_proof','parent_job_id','preview_data',
      'canonical_preview','normalized_rows','canonical_normalized','normalized_digest',
  'mapping_digest','job_digest'])
    OR (OLD.parse_pid IS NOT NULL AND NEW.parse_pid IS DISTINCT FROM OLD.parse_pid)
    OR (OLD.stop_proof IS NOT NULL AND NEW.stop_proof IS DISTINCT FROM OLD.stop_proof)
    OR (OLD.preview_data IS NOT NULL AND n<>o)
    OR (OLD.parse_state='STOPPED' AND NEW.parse_state<>'STOPPED')
    OR (OLD.parse_state='UNKNOWN' AND NEW.parse_state NOT IN('UNKNOWN','STOPPED'))
    OR (OLD.parse_state='RUNNING' AND NEW.parse_state NOT IN('RUNNING','UNKNOWN','STOPPED'))
   THEN RAISE EXCEPTION 'V41_PREVIEW_IMMUTABLE' USING ERRCODE='23514'; END IF;
  ELSE RAISE EXCEPTION 'V41_HISTORY_IMMUTABLE' USING ERRCODE='23514'; END IF;
 END IF;
 IF TG_TABLE_NAME='v41_product_tags' THEN
  IF NOT business.v41_tags_valid(NEW.tags) OR (TG_OP='INSERT' AND NEW.version<>1) THEN
   RAISE EXCEPTION 'V41_TAG_INVALID' USING ERRCODE='23514'; END IF;
  payload:=jsonb_build_object('scope',business.v41_scope(NEW.tenant_id,NEW.shop_id,NEW.reset_epoch),
   'product_id',NEW.product_id,'version',NEW.version,'tags',NEW.tags);
 ELSIF TG_TABLE_NAME='v41_order_fulfillments' THEN
  payload:=jsonb_build_object('scope',business.v41_scope(NEW.tenant_id,NEW.shop_id,NEW.reset_epoch),
   'order_id',NEW.order_id,'version',NEW.version,'status',NEW.status);
 ELSIF TG_TABLE_NAME='v41_import_products' THEN
  SELECT * INTO j FROM business.v41_import_jobs WHERE id=NEW.job_id;
  IF j.id IS NULL OR NEW.content IS DISTINCT FROM j.normalized_rows->(NEW.import_row-2)
   OR NEW.canonical_sku IS DISTINCT FROM NEW.content->>'canonical_sku' THEN
   RAISE EXCEPTION 'V41_IMPORT_SOURCE_INVALID' USING ERRCODE='23514'; END IF;
  payload:=jsonb_build_object('scope',business.v41_scope(NEW.tenant_id,NEW.shop_id,NEW.reset_epoch),
   'product_id',NEW.product_id,'sku_id',NEW.sku_id,'import_job_id',NEW.job_id,
   'import_row',NEW.import_row,'file_digest',j.file_digest,'product',NEW.content);
 END IF;
 IF payload IS NOT NULL THEN
  IF NEW.canonical_payload IS DISTINCT FROM business.v41_canonical(payload) THEN
   RAISE EXCEPTION 'V41_EFFECT_PAYLOAD_INVALID' USING ERRCODE='23514'; END IF;
 END IF;
 RETURN NEW;
END $$;
CREATE FUNCTION business.v41_commit_guard() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog,business AS $$
DECLARE s business.v4_demo_sessions; t business.v4_demo_tenants;
 r business.v41_action_receipts; e business.v41_action_events; summary jsonb; body jsonb;
 template jsonb; product jsonb; j business.v41_import_jobs;
 active_version text;
BEGIN
 -- Lease-authenticated cleanup after actual reap must remain possible after identity expiry.
 IF TG_TABLE_NAME='v41_import_jobs' AND TG_OP='UPDATE' THEN
  IF NEW.preview_data IS NULL THEN RETURN NULL; END IF;
 END IF;
 SELECT * INTO s FROM business.v4_demo_sessions WHERE id=NEW.owner_session_id AND
  tenant_id=NEW.tenant_id;
 SELECT * INTO t FROM business.v4_demo_tenants WHERE id=NEW.tenant_id;
 SELECT p.active_version INTO active_version FROM business.v41_security_policy p WHERE p.singleton;
 IF s.id IS NULL OR t.id IS NULL OR s.principal_id<>NEW.principal_id
  OR s.reset_epoch<>NEW.reset_epoch OR s.auth_generation<>NEW.auth_generation
  OR s.revoked_at IS NOT NULL OR t.revoked_at IS NOT NULL OR s.expires_at<>t.expires_at
  OR t.organization_id<>NEW.organization_id OR t.reset_epoch<>NEW.reset_epoch
  OR clock_timestamp()>=least(s.expires_at,t.expires_at)
  OR active_version IS DISTINCT FROM s.key_version
  OR NOT EXISTS(SELECT 1 FROM business.web_sessions w JOIN business.principals p ON
  p.id=s.principal_id
   AND p.organization_id=t.organization_id JOIN business.identities i ON i.id=s.identity_id
   AND i.principal_id=p.id AND i.organization_id=p.organization_id AND i.provider='web'
   JOIN business.web_credentials c ON c.identity_id=i.id AND c.principal_id=p.id
   AND c.organization_id=p.organization_id WHERE w.id=s.bound_web_session_id AND w.kind='session'
   AND w.organization_id=t.organization_id AND w.principal_id=s.principal_id
   AND w.identity_id=s.identity_id AND w.auth_version IS NOT DISTINCT FROM s.auth_version
   AND p.auth_version IS NOT DISTINCT FROM s.auth_version
   AND p.enabled AND c.enabled AND w.revoked_at IS NULL AND w.key_version=s.key_version
   AND least(w.absolute_expires_at,w.idle_expires_at)>clock_timestamp()
   AND greatest(w.absolute_expires_at,w.idle_expires_at)<=s.expires_at)
  OR NOT business.lock_p3_permission(s.principal_id,t.organization_id,NEW.shop_id,
   s.identity_id,s.auth_version,'operator') THEN
  RAISE EXCEPTION 'V41_COMMIT_AUTHORITY_INVALID' USING ERRCODE='23514'; END IF;
 IF TG_TABLE_NAME='v41_import_jobs' THEN
  IF NEW.expires_at>least(NEW.created_at+interval '10 minutes',s.expires_at)
   OR NEW.retain_until<>t.retain_until THEN
   RAISE EXCEPTION 'V41_PREVIEW_DEADLINE_INVALID' USING ERRCODE='23514'; END IF;
  RETURN NULL;
 END IF;
 IF TG_TABLE_NAME='v41_action_receipts' THEN r:=NEW;
 ELSE SELECT * INTO r FROM business.v41_action_receipts WHERE id=NEW.receipt_id; END IF;
 IF r.id IS NULL OR (r.tenant_id,r.shop_id,r.owner_session_id,r.principal_id,r.reset_epoch,
  r.auth_generation)
  IS DISTINCT FROM (NEW.tenant_id,NEW.shop_id,NEW.owner_session_id,NEW.principal_id,
   NEW.reset_epoch,NEW.auth_generation) THEN
  RAISE EXCEPTION 'V41_RECEIPT_BINDING_INVALID' USING ERRCODE='23514'; END IF;
 body:=business.v41_request_body(r.canonical_request,r.operation,r.resource_id);
 IF (body->>'shop_id')::uuid<>r.shop_id OR (body->>'expected_epoch')::bigint<>r.reset_epoch
  OR (body->>'expected_generation')::bigint<>r.auth_generation
  OR body->>'expected_data_revision' IS DISTINCT FROM r.before_revision
  OR r.retain_until<>t.retain_until THEN
  RAISE EXCEPTION 'V41_REQUEST_BINDING_INVALID' USING ERRCODE='23514'; END IF;
 IF TG_TABLE_NAME='v41_product_tags' THEN
  IF r.operation<>'product_tags' OR r.resource_id<>NEW.product_id
   OR r.resource_version<>NEW.version OR body->'tags' IS DISTINCT FROM NEW.tags
   OR (body->>'expected_version')::integer<>NEW.version-1 THEN
   RAISE EXCEPTION 'V41_TAG_RECEIPT_INVALID' USING ERRCODE='23514'; END IF;
 END IF;
 IF TG_TABLE_NAME='v41_order_fulfillments' THEN
  template:=business.v41_template(NEW.tenant_id,NEW.shop_id);
  SELECT p INTO product FROM jsonb_array_elements(template->'orders') p
   WHERE p->'ref'->>'id'=NEW.order_id::text;
  IF r.operation<>'order_fulfillment' OR r.resource_id<>NEW.order_id OR r.resource_version<>1
   OR (body->>'expected_version')::integer<>0 OR jsonb_typeof(product->'paid_at') IS DISTINCT
  FROM 'string'
  THEN RAISE EXCEPTION 'V41_FULFILLMENT_RECEIPT_INVALID' USING ERRCODE='23514'; END IF;
 END IF;
 IF TG_TABLE_NAME='v41_import_products' THEN
  SELECT * INTO j FROM business.v41_import_jobs WHERE id=NEW.job_id;
  IF r.operation<>'import_confirm' OR r.resource_id<>NEW.job_id OR
  r.resource_version<>j.chain_version
   OR body->>'expected_job_digest' IS DISTINCT FROM j.job_digest
   OR (body->>'expected_job_version')::integer<>j.chain_version OR
  j.data_revision<>r.before_revision
  THEN RAISE EXCEPTION 'V41_IMPORT_RECEIPT_INVALID' USING ERRCODE='23514'; END IF;
 END IF;
 SELECT * INTO e FROM business.v41_action_events WHERE receipt_id=r.id;
 summary:=business.v41_effect_summary(r.id);
 IF e.id IS NULL OR e.event_kind<>r.operation OR e.resource_id<>r.resource_id
  OR e.resource_version<>r.resource_version OR e.effect_count<>r.effect_count
  OR (summary->>'count')::integer<>r.effect_count OR e.effect_digest IS DISTINCT FROM
  summary->>'digest'
  OR r.after_revision IS DISTINCT FROM business.v41_revision(r.tenant_id,r.shop_id,
  r.reset_epoch) THEN
  RAISE EXCEPTION 'V41_ATOMIC_EFFECT_INVALID' USING ERRCODE='23514'; END IF;
 RETURN NULL;
END $$;
"""


def upgrade() -> None:
    op.execute(DDL)
    op.execute(FUNCTIONS)
    op.execute(ACTION_FUNCTIONS)
    op.execute(GUARDS)
    op.execute("REVOKE ALL ON business.v41_security_policy FROM PUBLIC")
    op.execute("""DO $$ BEGIN IF to_regrole('commerceops_app') IS NOT NULL THEN
     REVOKE ALL ON business.v41_security_policy FROM commerceops_app; END IF; END $$""")
    op.execute("""CREATE TRIGGER v41_policy_write BEFORE INSERT OR UPDATE OR DELETE
     ON business.v41_security_policy FOR EACH ROW EXECUTE FUNCTION business.v41_policy_guard()""")
    op.execute("""CREATE TRIGGER v41_policy_truncate BEFORE TRUNCATE
     ON business.v41_security_policy FOR EACH STATEMENT
     EXECUTE FUNCTION business.v41_policy_guard()""")
    op.execute("""ALTER TABLE business.v41_action_receipts ADD CONSTRAINT v41_request_canonical
     CHECK(canonical_request=business.v41_canonical(canonical_request::jsonb))""")
    for suffix in ("product_tags", "order_fulfillments", "import_products"):
        op.execute(f"""ALTER TABLE business.v41_{suffix} ADD CONSTRAINT v41_effect_canonical
         CHECK(canonical_payload=business.v41_canonical(canonical_payload::jsonb))""")
    for suffix in TABLES:
        op.execute(f"REVOKE ALL ON business.v41_{suffix} FROM PUBLIC")
        op.execute(f"""DO $$ BEGIN IF to_regrole('commerceops_app') IS NOT NULL THEN
         REVOKE ALL ON business.v41_{suffix} FROM commerceops_app; END IF; END $$""")
        op.execute(f"""CREATE TRIGGER v41_mutation BEFORE INSERT OR UPDATE OR DELETE
         ON business.v41_{suffix} FOR EACH ROW EXECUTE FUNCTION business.v41_mutation_guard()""")
        op.execute(f"""CREATE TRIGGER v41_no_truncate BEFORE TRUNCATE ON business.v41_{suffix}
         FOR EACH STATEMENT EXECUTE FUNCTION business.v41_mutation_guard()""")
        op.execute(f"""CREATE CONSTRAINT TRIGGER v41_commit AFTER INSERT OR UPDATE
         ON business.v41_{suffix} DEFERRABLE INITIALLY DEFERRED
         FOR EACH ROW EXECUTE FUNCTION business.v41_commit_guard()""")
    for signature in (
        *SIGNATURES,
        *ACTION_SIGNATURES,
        "v41_policy_guard()",
        "v41_mutation_guard()",
        "v41_commit_guard()",
    ):
        op.execute(f"REVOKE ALL ON FUNCTION business.{signature} FROM PUBLIC")
        op.execute(f"""DO $$ BEGIN IF to_regrole('commerceops_app') IS NOT NULL THEN
         REVOKE ALL ON FUNCTION business.{signature} FROM commerceops_app; END IF; END $$""")
    # Fail closed: no app DML or actor/helper EXECUTE is granted in this foundation slice.


def downgrade() -> None:
    raise RuntimeError("V41 history retained; destructive downgrade is not supported")
