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

CREATE FUNCTION business.v41_actor(bearer text,csrf text,shop uuid,epoch bigint,generation bigint,
 writing boolean) RETURNS business.v4_demo_sessions LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog,business AS $$
DECLARE sid uuid; tid uuid; t business.v4_demo_tenants; s business.v4_demo_sessions;
 p business.principals; w business.web_sessions; token_digest text; allowed boolean;
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
 SELECT a.* INTO p FROM business.principals a JOIN business.identities i
  ON i.principal_id=a.id AND i.organization_id=a.organization_id
  JOIN business.web_credentials c ON c.identity_id=i.id AND c.principal_id=a.id
  AND c.organization_id=a.organization_id WHERE a.id=s.principal_id
  AND a.organization_id=t.organization_id AND i.id=s.identity_id AND i.provider='web'
  AND c.enabled FOR SHARE OF a;
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
    "v41_actor(text,text,uuid,bigint,bigint,boolean)",
)


def upgrade() -> None:
    op.execute(DDL)
    op.execute(FUNCTIONS)
    op.execute("""ALTER TABLE business.v41_action_receipts ADD CONSTRAINT v41_request_canonical
     CHECK(canonical_request=business.v41_canonical(canonical_request::jsonb))""")
    for suffix in ("product_tags", "order_fulfillments", "import_products"):
        op.execute(f"""ALTER TABLE business.v41_{suffix} ADD CONSTRAINT v41_effect_canonical
         CHECK(canonical_payload=business.v41_canonical(canonical_payload::jsonb))""")
    for suffix in TABLES:
        op.execute(f"REVOKE ALL ON business.v41_{suffix} FROM PUBLIC")
        op.execute(f"""DO $$ BEGIN IF to_regrole('commerceops_app') IS NOT NULL THEN
         REVOKE ALL ON business.v41_{suffix} FROM commerceops_app; END IF; END $$""")
    for signature in SIGNATURES:
        op.execute(f"REVOKE ALL ON FUNCTION business.{signature} FROM PUBLIC")
        op.execute(f"""DO $$ BEGIN IF to_regrole('commerceops_app') IS NOT NULL THEN
         REVOKE ALL ON FUNCTION business.{signature} FROM commerceops_app; END IF; END $$""")
    # Fail closed: no app DML or actor/helper EXECUTE is granted in this foundation slice.


def downgrade() -> None:
    raise RuntimeError("V41 history retained; destructive downgrade is not supported")
