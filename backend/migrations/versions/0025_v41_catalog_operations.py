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
 invocation_verifier bytea NOT NULL CHECK(octet_length(invocation_verifier)=32),
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
 canonical_preview_request text NOT NULL CHECK(octet_length(canonical_preview_request)<=16384),
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
 canonical_preview text CHECK(octet_length(canonical_preview)<=2097152),
 normalized_rows jsonb,
 canonical_normalized text CHECK(octet_length(canonical_normalized)<=1048576),
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
 CHECK(request_digest=encode(sha256(convert_to(canonical_preview_request,'UTF8')),'hex')),
 CHECK(expires_at>created_at AND expires_at<=created_at+interval '10 minutes'),
 CHECK(retain_until>expires_at),
 CHECK((parse_state='STOPPED')=(parse_slot IS NULL)),
 CHECK(stop_proof IS NULL OR jsonb_typeof(stop_proof)='object'),
 CHECK(parse_state<>'STOPPED' OR coalesce(stop_proof @> '{{"reaped": true}}'::jsonb,false)),
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

CREATE FUNCTION business.v41_hmac_sha256(material bytea,payload bytea) RETURNS bytea
LANGUAGE plpgsql IMMUTABLE SET search_path=pg_catalog,business AS $$
DECLARE normalized bytea; block bytea; inner_pad bytea; outer_pad bytea; n integer;
BEGIN
 IF material IS NULL OR payload IS NULL OR octet_length(material) NOT BETWEEN 1 AND 1024
  OR octet_length(payload)>4096 THEN
  RAISE EXCEPTION 'INVALID_REQUEST' USING ERRCODE='23514'; END IF;
 normalized:=CASE WHEN octet_length(material)>64 THEN sha256(material) ELSE material END;
 block:=normalized||decode(repeat('00',64-octet_length(normalized)),'hex');
 inner_pad:=block; outer_pad:=block;
 FOR n IN 0..63 LOOP
  inner_pad:=set_byte(inner_pad,n,get_byte(block,n)#54);
  outer_pad:=set_byte(outer_pad,n,get_byte(block,n)#92);
 END LOOP;
 RETURN sha256(outer_pad||sha256(inner_pad||payload));
END $$;
CREATE FUNCTION business.v41_invocation_mac(material bytea,bound uuid,version text) RETURNS text
LANGUAGE plpgsql IMMUTABLE SET search_path=pg_catalog,business AS $$
DECLARE payload bytea;
BEGIN
 IF material IS NULL OR octet_length(material)<>32 OR bound IS NULL OR version IS NULL
  OR version !~ '^[A-Za-z0-9_.-]{1,80}$' THEN
  RAISE EXCEPTION 'INVALID_REQUEST' USING ERRCODE='23514'; END IF;
 payload:=convert_to('v41-runtime-binding-1','UTF8')||decode('00','hex')||
  convert_to(business.v41_canonical(jsonb_build_object('bound_session_id',bound,
   'key_version',version)),'UTF8');
 RETURN rtrim(translate(replace(encode(business.v41_hmac_sha256(material,payload),'base64'),
  chr(10),''),'+/','-_'),'=');
END $$;
-- Caller holds the principal SHARE lock. The existing p3_revoke_scope trigger on
-- credentials/scopes/grants must acquire principal UPDATE and advance auth_version before
-- committing any change. Read their committed predicates here without taking reverse tuple
-- locks: a pending revocation linearizes after this transaction; a committed one is rejected.
CREATE FUNCTION business.v41_permission(actor uuid,org uuid,shop uuid,identity uuid,
 auth bigint,requested_role text) RETURNS boolean LANGUAGE sql STABLE
SET search_path=pg_catalog,business AS $$
 SELECT EXISTS(SELECT 1 FROM business.principals p
 JOIN business.identities i ON i.principal_id=p.id AND i.organization_id=p.organization_id
 JOIN business.web_credentials c ON c.identity_id=i.id AND c.principal_id=p.id
  AND c.organization_id=p.organization_id
 JOIN business.principal_shop_scopes s ON s.principal_id=p.id
  AND s.organization_id=p.organization_id
 JOIN business.principal_role_shop_grants g ON g.principal_id=s.principal_id
  AND g.organization_id=s.organization_id AND g.shop_id=s.shop_id
 WHERE p.id=actor AND p.organization_id=org AND p.enabled AND p.auth_version=auth
  AND requested_role=ANY(p.roles) AND i.id=identity AND i.provider='web' AND c.enabled
  AND s.shop_id=shop AND s.enabled AND g.enabled AND g.role=requested_role)
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
 -- Match V40 principal/bound order; identity SHARE, credential predicates under principal SHARE.
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
 IF binding IS NULL OR binding !~ '^[A-Za-z0-9_-]{43}\.[A-Za-z0-9_-]{43}$'
  OR w.csrf_digest IS DISTINCT FROM
  encode(sha256(convert_to(split_part(binding,'.',1),'UTF8')),'hex') THEN
  RAISE EXCEPTION 'SESSION_INVALID' USING ERRCODE='23514'; END IF;
 PERFORM 1 FROM business.identities i WHERE i.id=s.identity_id AND i.provider='web'
  AND i.organization_id=t.organization_id AND i.principal_id=s.principal_id FOR SHARE;
 IF NOT FOUND THEN RAISE EXCEPTION 'SESSION_INVALID' USING ERRCODE='23514'; END IF;
 PERFORM 1 FROM business.web_credentials c WHERE c.identity_id=s.identity_id
  AND c.organization_id=t.organization_id AND c.principal_id=s.principal_id AND c.enabled;
 IF NOT FOUND THEN RAISE EXCEPTION 'SESSION_INVALID' USING ERRCODE='23514'; END IF;
 SELECT * INTO policy FROM business.v41_security_policy WHERE singleton FOR SHARE;
 IF policy.singleton IS NULL THEN
  RAISE EXCEPTION 'SERVICE_UNAVAILABLE' USING ERRCODE='23514'; END IF;
 IF s.key_version IS DISTINCT FROM policy.active_version
  OR split_part(binding,'.',2) IS DISTINCT FROM business.v41_invocation_mac(
   policy.invocation_verifier,s.bound_web_session_id,policy.active_version) THEN
  RAISE EXCEPTION 'SESSION_INVALID' USING ERRCODE='23514'; END IF;
 IF writing AND (csrf IS NULL OR octet_length(csrf)>256 OR s.csrf_digest<>
  encode(sha256(convert_to(csrf,'UTF8')),'hex')) THEN
  RAISE EXCEPTION 'CSRF_INVALID' USING ERRCODE='23514'; END IF;
 IF NOT EXISTS(SELECT 1 FROM business.v4_demo_shops m WHERE m.tenant_id=tid AND m.shop_id=shop)
 THEN RAISE EXCEPTION 'RESOURCE_NOT_FOUND' USING ERRCODE='23514'; END IF;
 allowed:=business.v41_permission(p.id,t.organization_id,shop,s.identity_id,s.auth_version,
  'operator');
 IF NOT writing AND NOT allowed THEN allowed:=business.v41_permission(p.id,t.organization_id,
  shop,s.identity_id,s.auth_version,'approver'); END IF;
 IF NOT allowed THEN RAISE EXCEPTION 'ACCESS_DENIED' USING ERRCODE='23514'; END IF;
 RETURN s;
END $$;
CREATE FUNCTION business.v41_read_guard(bearer text,binding text,shop uuid,epoch bigint,
 generation bigint) RETURNS text LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog,business AS $$
DECLARE s business.v4_demo_sessions;
BEGIN
 s:=business.v41_actor(bearer,NULL,binding,shop,epoch,generation,false);
 RETURN business.v41_revision(s.tenant_id,shop,s.reset_epoch);
END $$;
CREATE FUNCTION business.v41_write_guard(bearer text,csrf text,binding text,shop uuid,epoch bigint,
 generation bigint) RETURNS text LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog,business AS $$
DECLARE s business.v4_demo_sessions;
BEGIN
 s:=business.v41_actor(bearer,csrf,binding,shop,epoch,generation,true);
 RETURN business.v41_revision(s.tenant_id,shop,s.reset_epoch);
END $$;
"""

SIGNATURES = (
    "v41_hmac_sha256(bytea,bytea)",
    "v41_invocation_mac(bytea,uuid,text)",
    "v41_permission(uuid,uuid,uuid,uuid,bigint,text)",
    "v41_write_guard(text,text,text,uuid,bigint,bigint)",
    "v41_read_guard(text,text,uuid,bigint,bigint)",
    "v41_canonical(jsonb)",
    "v41_hash(jsonb)",
    "v41_utc(timestamptz)",
    "v41_scope(uuid,uuid,bigint)",
    "v41_revision(uuid,uuid,bigint)",
    "v41_actor(text,text,text,uuid,bigint,bigint,boolean)",
)

ACTION_FUNCTIONS = r"""
CREATE FUNCTION business.v41_text_valid(value text) RETURNS boolean LANGUAGE sql IMMUTABLE
SET search_path=pg_catalog,business AS $$
 SELECT coalesce(btrim(value)=value AND normalize(value,NFC)=value AND value COLLATE "C" !~ (
 U&'[\0001-\001F\007F-\00A0\00AD\0378-\0379\0380-\0383\038B\038D\03A2\0530\0557-\0558' ||
 U&'\058B-\058C\0590\05C8-\05CF\05EB-\05EE\05F5-\0605\061C\06DD\070E-\070F\074B-\074C' ||
 U&'\07B2-\07BF\07FB-\07FC\082E-\082F\083F\085C-\085D\085F\086B-\086F\088F-\0897\08E2\0984' ||
 U&'\098D-\098E\0991-\0992\09A9\09B1\09B3-\09B5\09BA-\09BB\09C5-\09C6\09C9-\09CA' ||
 U&'\09CF-\09D6\09D8-\09DB\09DE\09E4-\09E5\09FF-\0A00\0A04\0A0B-\0A0E\0A11-\0A12\0A29\0A31' ||
 U&'\0A34\0A37\0A3A-\0A3B\0A3D\0A43-\0A46\0A49-\0A4A\0A4E-\0A50\0A52-\0A58\0A5D\0A5F-\0A65' ||
 U&'\0A77-\0A80\0A84\0A8E\0A92\0AA9\0AB1\0AB4\0ABA-\0ABB\0AC6\0ACA\0ACE-\0ACF\0AD1-\0ADF' ||
 U&'\0AE4-\0AE5\0AF2-\0AF8\0B00\0B04\0B0D-\0B0E\0B11-\0B12\0B29\0B31\0B34\0B3A-\0B3B' ||
 U&'\0B45-\0B46\0B49-\0B4A\0B4E-\0B54\0B58-\0B5B\0B5E\0B64-\0B65\0B78-\0B81\0B84' ||
 U&'\0B8B-\0B8D\0B91\0B96-\0B98\0B9B\0B9D\0BA0-\0BA2\0BA5-\0BA7\0BAB-\0BAD\0BBA-\0BBD' ||
 U&'\0BC3-\0BC5\0BC9\0BCE-\0BCF\0BD1-\0BD6\0BD8-\0BE5\0BFB-\0BFF\0C0D\0C11\0C29\0C3A-\0C3B' ||
 U&'\0C45\0C49\0C4E-\0C54\0C57\0C5B-\0C5C\0C5E-\0C5F\0C64-\0C65\0C70-\0C76\0C8D\0C91\0CA9' ||
 U&'\0CB4\0CBA-\0CBB\0CC5\0CC9\0CCE-\0CD4\0CD7-\0CDC\0CDF\0CE4-\0CE5\0CF0\0CF4-\0CFF\0D0D' ||
 U&'\0D11\0D45\0D49\0D50-\0D53\0D64-\0D65\0D80\0D84\0D97-\0D99\0DB2\0DBC\0DBE-\0DBF' ||
 U&'\0DC7-\0DC9\0DCB-\0DCE\0DD5\0DD7\0DE0-\0DE5\0DF0-\0DF1\0DF5-\0E00\0E3B-\0E3E' ||
 U&'\0E5C-\0E80\0E83\0E85\0E8B\0EA4\0EA6\0EBE-\0EBF\0EC5\0EC7\0ECF\0EDA-\0EDB\0EE0-\0EFF' ||
 U&'\0F48\0F6D-\0F70\0F98\0FBD\0FCD\0FDB-\0FFF\10C6\10C8-\10CC\10CE-\10CF\1249\124E-\124F' ||
 U&'\1257\1259\125E-\125F\1289\128E-\128F\12B1\12B6-\12B7\12BF\12C1\12C6-\12C7\12D7\1311' ||
 U&'\1316-\1317\135B-\135C\137D-\137F\139A-\139F\13F6-\13F7\13FE-\13FF\1680\169D-\169F' ||
 U&'\16F9-\16FF\1716-\171E\1737-\173F\1754-\175F\176D\1771\1774-\177F\17DE-\17DF' ||
 U&'\17EA-\17EF\17FA-\17FF\180E\181A-\181F\1879-\187F\18AB-\18AF\18F6-\18FF\191F' ||
 U&'\192C-\192F\193C-\193F\1941-\1943\196E-\196F\1975-\197F\19AC-\19AF\19CA-\19CF' ||
 U&'\19DB-\19DD\1A1C-\1A1D\1A5F\1A7D-\1A7E\1A8A-\1A8F\1A9A-\1A9F\1AAE-\1AAF\1ACF-\1AFF' ||
 U&'\1B4D-\1B4F\1B7F\1BF4-\1BFB\1C38-\1C3A\1C4A-\1C4C\1C89-\1C8F\1CBB-\1CBC\1CC8-\1CCF' ||
 U&'\1CFB-\1CFF\1F16-\1F17\1F1E-\1F1F\1F46-\1F47\1F4E-\1F4F\1F58\1F5A\1F5C\1F5E\1F7E-\1F7F' ||
 U&'\1FB5\1FC5\1FD4-\1FD5\1FDC\1FF0-\1FF1\1FF5\1FFF-\200F\2028-\202F\205F-\206F\2072-\2073' ||
 U&'\208F\209D-\209F\20C1-\20CF\20F1-\20FF\218C-\218F\2427-\243F\244B-\245F\2B74-\2B75' ||
 U&'\2B96\2CF4-\2CF8\2D26\2D28-\2D2C\2D2E-\2D2F\2D68-\2D6E\2D71-\2D7E\2D97-\2D9F\2DA7\2DAF' ||
 U&'\2DB7\2DBF\2DC7\2DCF\2DD7\2DDF\2E5E-\2E7F\2E9A\2EF4-\2EFF\2FD6-\2FEF\2FFC-\3000\3040' ||
 U&'\3097-\3098\3100-\3104\3130\318F\31E4-\31EF\321F\A48D-\A48F\A4C7-\A4CF\A62C-\A63F' ||
 U&'\A6F8-\A6FF\A7CB-\A7CF\A7D2\A7D4\A7DA-\A7F1\A82D-\A82F\A83A-\A83F\A878-\A87F' ||
 U&'\A8C6-\A8CD\A8DA-\A8DF\A954-\A95E\A97D-\A97F\A9CE\A9DA-\A9DD\A9FF\AA37-\AA3F' ||
 U&'\AA4E-\AA4F\AA5A-\AA5B\AAC3-\AADA\AAF7-\AB00\AB07-\AB08\AB0F-\AB10\AB17-\AB1F\AB27' ||
 U&'\AB2F\AB6C-\AB6F\ABEE-\ABEF\ABFA-\ABFF\D7A4-\D7AF\D7C7-\D7CA\D7FC-\D7FF\E000-\F8FF' ||
 U&'\FA6E-\FA6F\FADA-\FAFF\FB07-\FB12\FB18-\FB1C\FB37\FB3D\FB3F\FB42\FB45\FBC3-\FBD2' ||
 U&'\FD90-\FD91\FDC8-\FDCE\FDD0-\FDEF\FE1A-\FE1F\FE53\FE67\FE6C-\FE6F\FE75\FEFD-\FF00' ||
 U&'\FFBF-\FFC1\FFC8-\FFC9\FFD0-\FFD1\FFD8-\FFD9\FFDD-\FFDF\FFE7\FFEF-\FFFB\FFFE-\FFFF' ||
 U&'\+01000C\+010027\+01003B\+01003E\+01004E-\+01004F\+01005E-\+01007F\+0100FB-\+0100FF' ||
 U&'\+010103-\+010106\+010134-\+010136\+01018F\+01019D-\+01019F\+0101A1-\+0101CF' ||
 U&'\+0101FE-\+01027F\+01029D-\+01029F\+0102D1-\+0102DF\+0102FC-\+0102FF\+010324-\+01032C' ||
 U&'\+01034B-\+01034F\+01037B-\+01037F\+01039E\+0103C4-\+0103C7\+0103D6-\+0103FF' ||
 U&'\+01049E-\+01049F\+0104AA-\+0104AF\+0104D4-\+0104D7\+0104FC-\+0104FF\+010528-\+01052F' ||
 U&'\+010564-\+01056E\+01057B\+01058B\+010593\+010596\+0105A2\+0105B2\+0105BA' ||
 U&'\+0105BD-\+0105FF\+010737-\+01073F\+010756-\+01075F\+010768-\+01077F\+010786\+0107B1' ||
 U&'\+0107BB-\+0107FF\+010806-\+010807\+010809\+010836\+010839-\+01083B\+01083D-\+01083E' ||
 U&'\+010856\+01089F-\+0108A6\+0108B0-\+0108DF\+0108F3\+0108F6-\+0108FA\+01091C-\+01091E' ||
 U&'\+01093A-\+01093E\+010940-\+01097F\+0109B8-\+0109BB\+0109D0-\+0109D1\+010A04' ||
 U&'\+010A07-\+010A0B\+010A14\+010A18\+010A36-\+010A37\+010A3B-\+010A3E\+010A49-\+010A4F' ||
 U&'\+010A59-\+010A5F\+010AA0-\+010ABF\+010AE7-\+010AEA\+010AF7-\+010AFF\+010B36-\+010B38' ||
 U&'\+010B56-\+010B57\+010B73-\+010B77\+010B92-\+010B98\+010B9D-\+010BA8\+010BB0-\+010BFF' ||
 U&'\+010C49-\+010C7F\+010CB3-\+010CBF\+010CF3-\+010CF9\+010D28-\+010D2F\+010D3A-\+010E5F' ||
 U&'\+010E7F\+010EAA\+010EAE-\+010EAF\+010EB2-\+010EFC\+010F28-\+010F2F\+010F5A-\+010F6F' ||
 U&'\+010F8A-\+010FAF\+010FCC-\+010FDF\+010FF7-\+010FFF\+01104E-\+011051\+011076-\+01107E' ||
 U&'\+0110BD\+0110C3-\+0110CF\+0110E9-\+0110EF\+0110FA-\+0110FF\+011135\+011148-\+01114F' ||
 U&'\+011177-\+01117F\+0111E0\+0111F5-\+0111FF\+011212\+011242-\+01127F\+011287\+011289' ||
 U&'\+01128E\+01129E\+0112AA-\+0112AF\+0112EB-\+0112EF\+0112FA-\+0112FF\+011304' ||
 U&'\+01130D-\+01130E\+011311-\+011312\+011329\+011331\+011334\+01133A\+011345-\+011346' ||
 U&'\+011349-\+01134A\+01134E-\+01134F\+011351-\+011356\+011358-\+01135C\+011364-\+011365' ||
 U&'\+01136D-\+01136F\+011375-\+0113FF\+01145C\+011462-\+01147F\+0114C8-\+0114CF' ||
 U&'\+0114DA-\+01157F\+0115B6-\+0115B7\+0115DE-\+0115FF\+011645-\+01164F\+01165A-\+01165F' ||
 U&'\+01166D-\+01167F\+0116BA-\+0116BF\+0116CA-\+0116FF\+01171B-\+01171C\+01172C-\+01172F' ||
 U&'\+011747-\+0117FF\+01183C-\+01189F\+0118F3-\+0118FE\+011907-\+011908\+01190A-\+01190B' ||
 U&'\+011914\+011917\+011936\+011939-\+01193A\+011947-\+01194F\+01195A-\+01199F' ||
 U&'\+0119A8-\+0119A9\+0119D8-\+0119D9\+0119E5-\+0119FF\+011A48-\+011A4F\+011AA3-\+011AAF' ||
 U&'\+011AF9-\+011AFF\+011B0A-\+011BFF\+011C09\+011C37\+011C46-\+011C4F\+011C6D-\+011C6F' ||
 U&'\+011C90-\+011C91\+011CA8\+011CB7-\+011CFF\+011D07\+011D0A\+011D37-\+011D39\+011D3B' ||
 U&'\+011D3E\+011D48-\+011D4F\+011D5A-\+011D5F\+011D66\+011D69\+011D8F\+011D92' ||
 U&'\+011D99-\+011D9F\+011DAA-\+011EDF\+011EF9-\+011EFF\+011F11\+011F3B-\+011F3D' ||
 U&'\+011F5A-\+011FAF\+011FB1-\+011FBF\+011FF2-\+011FFE\+01239A-\+0123FF\+01246F' ||
 U&'\+012475-\+01247F\+012544-\+012F8F\+012FF3-\+012FFF\+013430-\+01343F\+013456-\+0143FF' ||
 U&'\+014647-\+0167FF\+016A39-\+016A3F\+016A5F\+016A6A-\+016A6D\+016ABF\+016ACA-\+016ACF' ||
 U&'\+016AEE-\+016AEF\+016AF6-\+016AFF\+016B46-\+016B4F\+016B5A\+016B62\+016B78-\+016B7C' ||
 U&'\+016B90-\+016E3F\+016E9B-\+016EFF\+016F4B-\+016F4E\+016F88-\+016F8E\+016FA0-\+016FDF' ||
 U&'\+016FE5-\+016FEF\+016FF2-\+016FFF\+0187F8-\+0187FF\+018CD6-\+018CFF\+018D09-\+01AFEF' ||
 U&'\+01AFF4\+01AFFC\+01AFFF\+01B123-\+01B131\+01B133-\+01B14F\+01B153-\+01B154' ||
 U&'\+01B156-\+01B163\+01B168-\+01B16F\+01B2FC-\+01BBFF\+01BC6B-\+01BC6F\+01BC7D-\+01BC7F' ||
 U&'\+01BC89-\+01BC8F\+01BC9A-\+01BC9B\+01BCA0-\+01CEFF\+01CF2E-\+01CF2F\+01CF47-\+01CF4F' ||
 U&'\+01CFC4-\+01CFFF\+01D0F6-\+01D0FF\+01D127-\+01D128\+01D173-\+01D17A\+01D1EB-\+01D1FF' ||
 U&'\+01D246-\+01D2BF\+01D2D4-\+01D2DF\+01D2F4-\+01D2FF\+01D357-\+01D35F\+01D379-\+01D3FF' ||
 U&'\+01D455\+01D49D\+01D4A0-\+01D4A1\+01D4A3-\+01D4A4\+01D4A7-\+01D4A8\+01D4AD\+01D4BA' ||
 U&'\+01D4BC\+01D4C4\+01D506\+01D50B-\+01D50C\+01D515\+01D51D\+01D53A\+01D53F\+01D545' ||
 U&'\+01D547-\+01D549\+01D551\+01D6A6-\+01D6A7\+01D7CC-\+01D7CD\+01DA8C-\+01DA9A\+01DAA0' ||
 U&'\+01DAB0-\+01DEFF\+01DF1F-\+01DF24\+01DF2B-\+01DFFF\+01E007\+01E019-\+01E01A\+01E022' ||
 U&'\+01E025\+01E02B-\+01E02F\+01E06E-\+01E08E\+01E090-\+01E0FF\+01E12D-\+01E12F' ||
 U&'\+01E13E-\+01E13F\+01E14A-\+01E14D\+01E150-\+01E28F\+01E2AF-\+01E2BF\+01E2FA-\+01E2FE' ||
 U&'\+01E300-\+01E4CF\+01E4FA-\+01E7DF\+01E7E7\+01E7EC\+01E7EF\+01E7FF\+01E8C5-\+01E8C6' ||
 U&'\+01E8D7-\+01E8FF\+01E94C-\+01E94F\+01E95A-\+01E95D\+01E960-\+01EC70\+01ECB5-\+01ED00' ||
 U&'\+01ED3E-\+01EDFF\+01EE04\+01EE20\+01EE23\+01EE25-\+01EE26\+01EE28\+01EE33\+01EE38' ||
 U&'\+01EE3A\+01EE3C-\+01EE41\+01EE43-\+01EE46\+01EE48\+01EE4A\+01EE4C\+01EE50\+01EE53' ||
 U&'\+01EE55-\+01EE56\+01EE58\+01EE5A\+01EE5C\+01EE5E\+01EE60\+01EE63\+01EE65-\+01EE66' ||
 U&'\+01EE6B\+01EE73\+01EE78\+01EE7D\+01EE7F\+01EE8A\+01EE9C-\+01EEA0\+01EEA4\+01EEAA' ||
 U&'\+01EEBC-\+01EEEF\+01EEF2-\+01EFFF\+01F02C-\+01F02F\+01F094-\+01F09F\+01F0AF-\+01F0B0' ||
 U&'\+01F0C0\+01F0D0\+01F0F6-\+01F0FF\+01F1AE-\+01F1E5\+01F203-\+01F20F\+01F23C-\+01F23F' ||
 U&'\+01F249-\+01F24F\+01F252-\+01F25F\+01F266-\+01F2FF\+01F6D8-\+01F6DB\+01F6ED-\+01F6EF' ||
 U&'\+01F6FD-\+01F6FF\+01F777-\+01F77A\+01F7DA-\+01F7DF\+01F7EC-\+01F7EF\+01F7F1-\+01F7FF' ||
 U&'\+01F80C-\+01F80F\+01F848-\+01F84F\+01F85A-\+01F85F\+01F888-\+01F88F\+01F8AE-\+01F8AF' ||
 U&'\+01F8B2-\+01F8FF\+01FA54-\+01FA5F\+01FA6E-\+01FA6F\+01FA7D-\+01FA7F\+01FA89-\+01FA8F' ||
 U&'\+01FABE\+01FAC6-\+01FACD\+01FADC-\+01FADF\+01FAE9-\+01FAEF\+01FAF9-\+01FAFF\+01FB93' ||
 U&'\+01FBCB-\+01FBEF\+01FBFA-\+01FFFF\+02A6E0-\+02A6FF\+02B73A-\+02B73F\+02B81E-\+02B81F' ||
 U&'\+02CEA2-\+02CEAF\+02EBE1-\+02F7FF\+02FA1E-\+02FFFF\+03134B-\+03134F\+0323B0-\+0E00FF' ||
 U&'\+0E01F0-\+10FFFF]'),false)
$$;
CREATE FUNCTION business.v41_tags_valid(value jsonb) RETURNS boolean LANGUAGE sql IMMUTABLE
SET search_path=pg_catalog,business AS $$
 SELECT CASE WHEN jsonb_typeof(value) IS DISTINCT FROM 'array' THEN false
 ELSE jsonb_array_length(value)<=8 AND NOT EXISTS(
  SELECT 1 FROM jsonb_array_elements(value) e WHERE jsonb_typeof(e) IS DISTINCT FROM 'string'
  OR length(e#>>'{}') NOT BETWEEN 1 AND 24 OR NOT business.v41_text_valid(e#>>'{}'))
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
 AND business.v41_text_valid(value->>'title')
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
 IF NOT business.v41_permission(s.principal_id,org,shop,s.identity_id,s.auth_version,
  'operator') THEN
  RAISE EXCEPTION 'ACCESS_DENIED' USING ERRCODE='23514'; END IF;
 IF clock_timestamp()>=s.expires_at THEN RAISE EXCEPTION 'SESSION_INVALID' USING
  ERRCODE='23514'; END IF;
 RETURN result;
END $$;
"""

ACTION_SIGNATURES = (
    "v41_text_valid(text)",
    "v41_tags_valid(jsonb)",
    "v41_product_valid(jsonb,text)",
    "v41_request_body(text,text,uuid)",
    "v41_template(uuid,uuid)",
    "v41_effect_summary(uuid)",
    "v41_preview_digest(business.v41_import_jobs)",
    "v41_apply_action(text,text,text,text,text,uuid)",
)

GUARDS = r"""
CREATE FUNCTION business.v41_demo_principal(org uuid,actor uuid) RETURNS boolean
LANGUAGE sql STABLE SET search_path=pg_catalog,business AS $$
 SELECT EXISTS(SELECT 1 FROM business.v4_demo_personas a
   WHERE a.organization_id=org AND a.principal_id=actor)
$$;
CREATE FUNCTION business.v41_demo_binding_guard() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog,business AS $$
BEGIN
 IF (NEW.organization_id,NEW.principal_id) IS DISTINCT FROM
    (OLD.organization_id,OLD.principal_id)
  AND (business.v41_demo_principal(OLD.organization_id,OLD.principal_id)
   OR business.v41_demo_principal(NEW.organization_id,NEW.principal_id)) THEN
  RAISE EXCEPTION 'V41_DEMO_BINDING_IMMUTABLE' USING ERRCODE='23514'; END IF;
 RETURN NEW;
END $$;
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
 -- Also serialize owner-originated deferred checks with the same principal authority point.
 PERFORM 1 FROM business.principals WHERE id=NEW.principal_id
  AND organization_id=NEW.organization_id FOR SHARE;
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
  OR NOT business.v41_permission(s.principal_id,t.organization_id,NEW.shop_id,
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

PARSE_FUNCTIONS = r"""
CREATE FUNCTION business.v41_preview_command(canonical text) RETURNS jsonb
LANGUAGE plpgsql IMMUTABLE SET search_path=pg_catalog,business AS $$
DECLARE req jsonb; body jsonb; allowed text[]; field text; mapping jsonb;
BEGIN
 IF canonical IS NULL OR octet_length(canonical)>16384 THEN
  RAISE EXCEPTION 'INVALID_REQUEST' USING ERRCODE='23514'; END IF;
 req:=canonical::jsonb;
 IF jsonb_typeof(req) IS DISTINCT FROM 'object' OR req-ARRAY['command','file_digest']<>'{}'::jsonb
  OR canonical IS DISTINCT FROM business.v41_canonical(req)
  OR jsonb_typeof(req->'file_digest') IS DISTINCT FROM 'string'
  OR req->>'file_digest' !~ '^[a-f0-9]{64}$' THEN
  RAISE EXCEPTION 'INVALID_REQUEST' USING ERRCODE='23514'; END IF;
 body:=req->'command';
 allowed:=ARRAY['shop_id','request_key','expected_epoch','expected_generation','expected_data_revision',
  'format','filename','mapping','mapping_version','parent_job_id'];
 IF jsonb_typeof(body) IS DISTINCT FROM 'object' OR NOT(body ?& allowed)
  OR body-allowed<>'{}'::jsonb OR body->'mapping_version' IS DISTINCT FROM '1'::jsonb
  OR jsonb_typeof(body->'expected_data_revision') IS DISTINCT FROM 'string'
  OR body->>'expected_data_revision' !~ '^[a-f0-9]{64}$'
  OR jsonb_typeof(body->'filename') IS DISTINCT FROM 'string'
  OR length(body->>'filename') NOT BETWEEN 1 AND 128
  OR jsonb_typeof(body->'format') IS DISTINCT FROM 'string'
  OR body->>'format' NOT IN('csv','xlsx') THEN
  RAISE EXCEPTION 'INVALID_REQUEST' USING ERRCODE='23514'; END IF;
 FOREACH field IN ARRAY ARRAY['shop_id','request_key'] LOOP
  IF jsonb_typeof(body->field) IS DISTINCT FROM 'string'
   OR (body->>field)::uuid::text IS DISTINCT FROM body->>field THEN
   RAISE EXCEPTION 'INVALID_REQUEST' USING ERRCODE='23514'; END IF;
 END LOOP;
 FOREACH field IN ARRAY ARRAY['expected_epoch','expected_generation'] LOOP
  IF jsonb_typeof(body->field) IS DISTINCT FROM 'number'
   OR body->>field !~ '^(0|[1-9][0-9]{0,8})$' THEN
   RAISE EXCEPTION 'INVALID_REQUEST' USING ERRCODE='23514'; END IF;
 END LOOP;
 IF body->'parent_job_id' IS DISTINCT FROM 'null'::jsonb AND
  (jsonb_typeof(body->'parent_job_id') IS DISTINCT FROM 'string'
   OR (body->>'parent_job_id')::uuid::text IS DISTINCT FROM body->>'parent_job_id') THEN
  RAISE EXCEPTION 'INVALID_REQUEST' USING ERRCODE='23514'; END IF;
 mapping:=body->'mapping';
 IF mapping IS DISTINCT FROM 'null'::jsonb THEN
  allowed:=ARRAY['sku','title','price','currency','tags'];
  IF jsonb_typeof(mapping) IS DISTINCT FROM 'object' OR NOT(mapping ?& allowed)
   OR mapping-allowed<>'{}'::jsonb THEN
   RAISE EXCEPTION 'INVALID_REQUEST' USING ERRCODE='23514'; END IF;
  FOREACH field IN ARRAY allowed LOOP
   IF field='tags' AND mapping->field='null'::jsonb THEN CONTINUE; END IF;
   IF jsonb_typeof(mapping->field) IS DISTINCT FROM 'string'
    OR length(mapping->>field) NOT BETWEEN 1 AND 80 THEN
    RAISE EXCEPTION 'INVALID_REQUEST' USING ERRCODE='23514'; END IF;
  END LOOP;
  IF (SELECT count(*)<>count(DISTINCT value) FROM jsonb_each(mapping)
    WHERE value<>'null'::jsonb) THEN
   RAISE EXCEPTION 'INVALID_REQUEST' USING ERRCODE='23514'; END IF;
 END IF;
 RETURN req;
END $$;
CREATE FUNCTION business.v41_reserve_preview(bearer text,csrf text,binding text,canonical text,
 lease_digest text,process_ref uuid) RETURNS business.v41_import_jobs
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,business AS $$
DECLARE req jsonb; body jsonb; s business.v4_demo_sessions; t business.v4_demo_tenants;
 prior business.v41_import_jobs; parent business.v41_import_jobs; result business.v41_import_jobs;
 shop uuid; version integer:=1; active integer; slot smallint; stamp timestamptz; digest text;
BEGIN
 req:=business.v41_preview_command(canonical); body:=req->'command';
 shop:=(body->>'shop_id')::uuid;
 s:=business.v41_actor(bearer,csrf,binding,shop,(body->>'expected_epoch')::bigint,
  (body->>'expected_generation')::bigint,true);
 SELECT * INTO t FROM business.v4_demo_tenants WHERE id=s.tenant_id;
 digest:=business.v41_hash(req);
 SELECT * INTO prior FROM business.v41_import_jobs j WHERE j.owner_session_id=s.id
  AND j.preview_key IS NOT DISTINCT FROM (body->>'request_key')::uuid;
 IF prior.id IS NOT NULL THEN
  IF prior.request_digest<>digest OR (prior.tenant_id,prior.shop_id,prior.principal_id,
   prior.reset_epoch,prior.auth_generation) IS DISTINCT FROM
   (s.tenant_id,shop,s.principal_id,s.reset_epoch,s.auth_generation) THEN
   RAISE EXCEPTION 'IDEMPOTENCY_CONFLICT' USING ERRCODE='23514'; END IF;
  RETURN prior;
 END IF;
 IF body->>'expected_data_revision' IS DISTINCT FROM
  business.v41_revision(s.tenant_id,shop,s.reset_epoch) THEN
  RAISE EXCEPTION 'SNAPSHOT_CHANGED' USING ERRCODE='23514'; END IF;
 IF lease_digest IS NULL OR lease_digest !~ '^[a-f0-9]{64}$' OR process_ref IS NULL THEN
  RAISE EXCEPTION 'INVALID_REQUEST' USING ERRCODE='23514'; END IF;
 stamp:=clock_timestamp();
 IF (SELECT count(*) FROM business.v41_import_jobs j WHERE j.tenant_id=s.tenant_id)>=12 THEN
  RAISE EXCEPTION 'LIMIT_EXCEEDED' USING ERRCODE='23514'; END IF;
 IF body->'parent_job_id'<>'null'::jsonb THEN
  SELECT * INTO parent FROM business.v41_import_jobs j
   WHERE j.id=(body->>'parent_job_id')::uuid AND j.tenant_id=s.tenant_id AND j.shop_id=shop
   AND j.owner_session_id=s.id AND j.principal_id=s.principal_id AND j.reset_epoch=s.reset_epoch
   AND j.auth_generation IS NOT DISTINCT FROM s.auth_generation FOR UPDATE;
  IF parent.id IS NULL THEN RAISE EXCEPTION 'RESOURCE_NOT_FOUND' USING ERRCODE='23514'; END IF;
  IF parent.preview_data IS NULL OR parent.expires_at<=stamp OR EXISTS(
    SELECT 1 FROM business.v41_import_jobs j WHERE j.parent_job_id=parent.id) OR EXISTS(
    SELECT 1 FROM business.v41_action_receipts r WHERE r.operation='import_confirm'
    AND r.resource_id=parent.id) THEN
   RAISE EXCEPTION 'STATE_CONFLICT' USING ERRCODE='23514'; END IF;
  IF parent.file_digest<>req->>'file_digest' THEN
   RAISE EXCEPTION 'IMPORT_INVALID' USING ERRCODE='23514'; END IF;
  version:=parent.chain_version+1;
  IF version>5 THEN RAISE EXCEPTION 'LIMIT_EXCEEDED' USING ERRCODE='23514'; END IF;
 END IF;
 SELECT count(*) INTO active FROM business.v41_import_jobs j WHERE j.tenant_id=s.tenant_id
  AND j.reset_epoch=s.reset_epoch AND j.auth_generation IS NOT DISTINCT FROM s.auth_generation
  AND j.preview_data IS NOT NULL AND j.expires_at>stamp AND NOT EXISTS(
   SELECT 1 FROM business.v41_import_jobs child WHERE child.parent_job_id=j.id) AND NOT EXISTS(
   SELECT 1 FROM business.v41_action_receipts r WHERE r.operation='import_confirm'
   AND r.resource_id=j.id);
 IF active-CASE WHEN parent.id IS NULL THEN 0 ELSE 1 END>=3 THEN
  RAISE EXCEPTION 'LIMIT_EXCEEDED' USING ERRCODE='23514'; END IF;
 IF NOT pg_try_advisory_xact_lock(1446261845,1) OR EXISTS(
   SELECT 1 FROM business.v41_import_jobs j WHERE j.tenant_id=s.tenant_id AND
  j.parse_state<>'STOPPED')
 THEN RAISE EXCEPTION 'RATE_LIMITED' USING ERRCODE='23514'; END IF;
 SELECT n::smallint INTO slot FROM generate_series(0,1) n WHERE NOT EXISTS(
  SELECT 1 FROM business.v41_import_jobs j WHERE j.parse_slot=n AND j.parse_state<>'STOPPED')
  ORDER BY n LIMIT 1;
 IF slot IS NULL THEN RAISE EXCEPTION 'RATE_LIMITED' USING ERRCODE='23514'; END IF;
 INSERT INTO business.v41_import_jobs(id,tenant_id,organization_id,shop_id,owner_session_id,
  principal_id,reset_epoch,auth_generation,preview_key,canonical_preview_request,request_digest,
  file_digest,data_revision,
  parser_version,import_schema_version,requested_parent_job_id,chain_version,created_at,expires_at,
  retain_until,parse_state,parse_slot,lease_digest,process_ref)
 VALUES(gen_random_uuid(),s.tenant_id,t.organization_id,shop,s.id,s.principal_id,s.reset_epoch,
  s.auth_generation,(body->>'request_key')::uuid,canonical,digest,req->>'file_digest',
  body->>'expected_data_revision','v41-parser-1','v41-import-1',parent.id,version,stamp,
  least(stamp+interval '10 minutes',s.expires_at),t.retain_until,'RESERVED',slot,
  lease_digest,process_ref) RETURNING * INTO result;
 RETURN result;
END $$;
CREATE FUNCTION business.v41_bind_parser(job uuid,lease text,process uuid,pid integer) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,business AS $$
DECLARE j business.v41_import_jobs;
BEGIN
 SELECT * INTO j FROM business.v41_import_jobs WHERE id=job FOR UPDATE;
 IF j.id IS NULL OR lease IS NULL OR octet_length(lease)>256 OR j.lease_digest IS DISTINCT FROM
  encode(sha256(convert_to(lease,'UTF8')),'hex') OR process IS DISTINCT FROM j.process_ref
  OR pid IS NULL OR pid<=0 OR j.parse_state NOT IN('RESERVED','RUNNING')
  OR (j.parse_pid IS NOT NULL AND j.parse_pid<>pid) THEN
  RAISE EXCEPTION 'V41_PARSE_LEASE_INVALID' USING ERRCODE='23514'; END IF;
 UPDATE business.v41_import_jobs SET parse_pid=pid,parse_state='RUNNING' WHERE id=job;
END $$;
CREATE FUNCTION business.v41_stop_parser(job uuid,lease text,process uuid,proof jsonb) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,business AS $$
DECLARE j business.v41_import_jobs;
BEGIN
 SELECT * INTO j FROM business.v41_import_jobs WHERE id=job FOR UPDATE;
 IF j.id IS NULL OR lease IS NULL OR octet_length(lease)>256 OR j.lease_digest IS DISTINCT FROM
  encode(sha256(convert_to(lease,'UTF8')),'hex') OR process IS DISTINCT FROM j.process_ref THEN
  RAISE EXCEPTION 'V41_PARSE_LEASE_INVALID' USING ERRCODE='23514'; END IF;
 IF jsonb_typeof(proof) IS DISTINCT FROM 'object'
  OR NOT(proof ?& ARRAY['process_ref','pid','native_exit','timed_out','reaped','output_digest'])
  OR proof-ARRAY['process_ref','pid','native_exit','timed_out','reaped','output_digest']
    <>'{}'::jsonb
  OR proof->>'process_ref' IS DISTINCT FROM process::text
  OR proof->'reaped' IS DISTINCT FROM 'true'::jsonb
  OR jsonb_typeof(proof->'timed_out') IS DISTINCT FROM 'boolean'
  OR jsonb_typeof(proof->'pid') IS DISTINCT FROM 'number'
  OR proof->>'pid' !~ '^[1-9][0-9]{0,9}$'
  OR jsonb_typeof(proof->'native_exit') IS DISTINCT FROM 'number'
  OR proof->>'native_exit' !~ '^-?(0|[1-9][0-9]{0,2})$' THEN
  RAISE EXCEPTION 'V41_PARSE_STOP_PROOF_INVALID' USING ERRCODE='23514'; END IF;
 IF j.parse_pid IS NOT NULL AND j.parse_pid<>(proof->>'pid')::integer THEN
  RAISE EXCEPTION 'V41_PARSE_STOP_PROOF_INVALID' USING ERRCODE='23514'; END IF;
 IF j.parse_state='STOPPED' THEN
  IF j.stop_proof IS DISTINCT FROM proof THEN
   RAISE EXCEPTION 'V41_PARSE_STOP_PROOF_INVALID' USING ERRCODE='23514'; END IF;
  RETURN;
 END IF;
 IF jsonb_typeof(proof->'output_digest') IS DISTINCT FROM 'string'
  OR proof->>'output_digest' !~ '^[a-f0-9]{64}$' THEN
  RAISE EXCEPTION 'V41_PARSE_STOP_PROOF_INVALID' USING ERRCODE='23514'; END IF;
 UPDATE business.v41_import_jobs SET parse_pid=(proof->>'pid')::integer,parse_state='STOPPED',
  parse_slot=NULL,stop_proof=proof WHERE id=job;
END $$;
CREATE FUNCTION business.v41_publish_preview(bearer text,csrf text,binding text,job uuid,lease text,
 canonical text,normalized text) RETURNS business.v41_import_jobs
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,business AS $$
DECLARE j business.v41_import_jobs; candidate business.v41_import_jobs; parent
  business.v41_import_jobs;
 s business.v4_demo_sessions; data jsonb; rows jsonb; native jsonb; active integer; row jsonb;
BEGIN
 IF canonical IS NULL OR normalized IS NULL OR octet_length(canonical)>2097152
  OR octet_length(normalized)>1048576 THEN
  RAISE EXCEPTION 'LIMIT_EXCEEDED' USING ERRCODE='23514'; END IF;
 data:=canonical::jsonb; rows:=normalized::jsonb;
 SELECT * INTO j FROM business.v41_import_jobs WHERE id=job;
 IF j.id IS NULL THEN RAISE EXCEPTION 'RESOURCE_NOT_FOUND' USING ERRCODE='23514'; END IF;
 s:=business.v41_actor(bearer,csrf,binding,j.shop_id,j.reset_epoch,j.auth_generation,true);
 SELECT * INTO j FROM business.v41_import_jobs WHERE id=job FOR UPDATE;
 IF (j.tenant_id,j.owner_session_id,j.principal_id) IS DISTINCT FROM
  (s.tenant_id,s.id,s.principal_id) THEN
  RAISE EXCEPTION 'RESOURCE_NOT_FOUND' USING ERRCODE='23514'; END IF;
 IF lease IS NULL OR octet_length(lease)>256 OR j.lease_digest IS DISTINCT FROM
  encode(sha256(convert_to(lease,'UTF8')),'hex') OR j.parse_state<>'STOPPED'
  OR j.stop_proof->'native_exit' IS DISTINCT FROM '0'::jsonb
  OR j.stop_proof->'timed_out' IS DISTINCT FROM 'false'::jsonb
  OR j.stop_proof->'reaped' IS DISTINCT FROM 'true'::jsonb THEN
  RAISE EXCEPTION 'V41_PARSE_RESULT_INVALID' USING ERRCODE='23514'; END IF;
 IF j.preview_data IS NOT NULL THEN
  IF j.canonical_preview<>canonical OR j.canonical_normalized<>normalized THEN
   RAISE EXCEPTION 'IDEMPOTENCY_CONFLICT' USING ERRCODE='23514'; END IF;
  RETURN j;
 END IF;
 IF clock_timestamp()>=j.expires_at THEN
  RAISE EXCEPTION 'IMPORT_EXPIRED' USING ERRCODE='23514'; END IF;
 IF j.data_revision IS DISTINCT FROM business.v41_revision(j.tenant_id,j.shop_id,j.reset_epoch) THEN
  RAISE EXCEPTION 'SNAPSHOT_CHANGED' USING ERRCODE='23514'; END IF;
 IF jsonb_typeof(data) IS DISTINCT FROM 'object' OR jsonb_typeof(rows) IS DISTINCT FROM 'array'
  OR jsonb_array_length(rows)>500 OR canonical IS DISTINCT FROM business.v41_canonical(data)
  OR normalized IS DISTINCT FROM business.v41_canonical(rows)
  OR data->'mapping' IS DISTINCT FROM j.canonical_preview_request::jsonb->'command'->'mapping'
  OR data->'mapping_version' IS DISTINCT FROM '1'::jsonb
  OR data->>'file_digest' IS DISTINCT FROM j.file_digest
  OR data->'job'->>'import_job_id' IS DISTINCT FROM j.id::text
  OR data->'job'->>'version' IS DISTINCT FROM j.chain_version::text
  OR data->'job'->'parent_job_id' IS DISTINCT FROM
    coalesce(to_jsonb(j.requested_parent_job_id),'null'::jsonb)
  OR data->'job'->>'data_revision' IS DISTINCT FROM j.data_revision
  OR data->'job'->>'parser_version' IS DISTINCT FROM j.parser_version
  OR data->'job'->>'import_schema_version' IS DISTINCT FROM j.import_schema_version
  OR data->'job'->>'expires_at' IS DISTINCT FROM business.v41_utc(j.expires_at)
  OR jsonb_typeof(data->'state') IS DISTINCT FROM 'string'
  OR data->>'state' NOT IN('DISCOVERED','READY','INVALID') THEN
  RAISE EXCEPTION 'V41_PREVIEW_CONTENT_INVALID' USING ERRCODE='23514'; END IF;
 IF data->>'state'='READY' THEN
  IF jsonb_typeof(data->'mapping') IS DISTINCT FROM 'object'
   OR data->'confirmable' IS DISTINCT FROM 'true'::jsonb
   OR data->'issue_count' IS DISTINCT FROM '0'::jsonb
   OR jsonb_array_length(rows) NOT BETWEEN 1 AND 500
   OR data->>'row_count' IS DISTINCT FROM jsonb_array_length(rows)::text THEN
   RAISE EXCEPTION 'V41_PREVIEW_CONTENT_INVALID' USING ERRCODE='23514'; END IF;
  FOR row IN SELECT value FROM jsonb_array_elements(rows) LOOP
   IF NOT business.v41_product_valid(row,
     business.v41_template(j.tenant_id,j.shop_id)->>'currency') THEN
    RAISE EXCEPTION 'V41_PREVIEW_CONTENT_INVALID' USING ERRCODE='23514'; END IF;
  END LOOP;
 ELSE
  IF jsonb_array_length(rows)<>0 OR data->'confirmable' IS DISTINCT FROM 'false'::jsonb THEN
   RAISE EXCEPTION 'V41_PREVIEW_CONTENT_INVALID' USING ERRCODE='23514'; END IF;
 END IF;
 IF j.requested_parent_job_id IS NOT NULL THEN
  SELECT * INTO parent FROM business.v41_import_jobs WHERE id=j.requested_parent_job_id FOR UPDATE;
  IF parent.preview_data IS NULL OR parent.expires_at<=clock_timestamp() OR EXISTS(
    SELECT 1 FROM business.v41_import_jobs child WHERE child.parent_job_id=parent.id) OR EXISTS(
    SELECT 1 FROM business.v41_action_receipts r WHERE r.operation='import_confirm'
    AND r.resource_id=parent.id) THEN
   RAISE EXCEPTION 'STATE_CONFLICT' USING ERRCODE='23514'; END IF;
 END IF;
 SELECT count(*) INTO active FROM business.v41_import_jobs i WHERE i.tenant_id=j.tenant_id
  AND i.reset_epoch=j.reset_epoch AND i.auth_generation IS NOT DISTINCT FROM j.auth_generation
  AND i.preview_data IS NOT NULL AND i.expires_at>clock_timestamp() AND NOT EXISTS(
   SELECT 1 FROM business.v41_import_jobs child WHERE child.parent_job_id=i.id) AND NOT EXISTS(
   SELECT 1 FROM business.v41_action_receipts r WHERE r.operation='import_confirm' AND
  r.resource_id=i.id);
 IF active-CASE WHEN parent.id IS NULL THEN 0 ELSE 1 END>=3 THEN
  RAISE EXCEPTION 'LIMIT_EXCEEDED' USING ERRCODE='23514'; END IF;
 candidate:=j;
 candidate.preview_data:=data; candidate.normalized_rows:=rows;
 candidate.normalized_digest:=business.v41_hash(jsonb_build_object('rows',rows,
  'parser_version',j.parser_version,'import_schema_version',j.import_schema_version));
 candidate.mapping_digest:=business.v41_hash(jsonb_build_object('mapping',data->'mapping',
  'mapping_version',1));
 IF data->'job'->>'job_digest' IS DISTINCT FROM business.v41_preview_digest(candidate) THEN
  RAISE EXCEPTION 'VERSION_CONFLICT' USING ERRCODE='23514'; END IF;
 native:=jsonb_build_object('schema_version','v41-parser-result-1','file_digest',j.file_digest,
  'headers',data->'headers','row_count',data->'row_count','state',data->'state','products',rows,
  'sample',data->'sample','issues',data->'issues','issue_count',data->'issue_count');
 IF business.v41_hash(native) IS DISTINCT FROM j.stop_proof->>'output_digest' THEN
  RAISE EXCEPTION 'V41_PARSE_RESULT_INVALID' USING ERRCODE='23514'; END IF;
 UPDATE business.v41_import_jobs SET parent_job_id=requested_parent_job_id,preview_data=data,
  canonical_preview=canonical,normalized_rows=rows,canonical_normalized=normalized,
  normalized_digest=candidate.normalized_digest,mapping_digest=candidate.mapping_digest,
  job_digest=data->'job'->>'job_digest' WHERE id=j.id RETURNING * INTO candidate;
 RETURN candidate;
END $$;
"""

PARSE_SIGNATURES = (
    "v41_preview_command(text)",
    "v41_reserve_preview(text,text,text,text,text,uuid)",
    "v41_bind_parser(uuid,text,uuid,integer)",
    "v41_stop_parser(uuid,text,uuid,jsonb)",
    "v41_publish_preview(text,text,text,uuid,text,text,text)",
)


def upgrade() -> None:
    op.execute(DDL)
    op.execute(FUNCTIONS)
    op.execute(ACTION_FUNCTIONS)
    op.execute(GUARDS)
    op.execute(PARSE_FUNCTIONS)
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
    # Alphabetical trigger order rejects ownership rebinding before the original NEW-principal
    # trigger takes locks. Same-principal changes, INSERT and DELETE keep their original path.
    for table in ("web_credentials", "principal_shop_scopes", "principal_role_shop_grants"):
        op.execute(f"""CREATE TRIGGER a_v41_demo_binding BEFORE UPDATE ON business.{table}
         FOR EACH ROW EXECUTE FUNCTION business.v41_demo_binding_guard()""")
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
        *PARSE_SIGNATURES,
        "v41_demo_principal(uuid,uuid)",
        "v41_demo_binding_guard()",
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
