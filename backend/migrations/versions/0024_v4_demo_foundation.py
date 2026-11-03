"""Isolated V4 synchronous demo identity, fixtures and control receipts."""

from alembic import op

revision = "0024_v4_demo_foundation"
down_revision = "0023_p6_copy_drafts"
branch_labels = None
depends_on = None

DDL = r"""
CREATE TABLE business.v4_demo_fixture_versions (
 version text PRIMARY KEY CHECK (version='v4-demo-seed-1'),
 generator_version text NOT NULL CHECK (generator_version='v4-seed-generator-1'),
 canonical_content text NOT NULL,
 content jsonb NOT NULL,
 content_hash text NOT NULL CHECK (content_hash ~ '^[a-f0-9]{64}$'),
 snapshot_at timestamptz NOT NULL,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 CHECK (jsonb_typeof(content)='object'),
 CHECK (canonical_content::jsonb=content),
 CHECK (octet_length(canonical_content)<=1048576),
 CHECK (content_hash=encode(sha256(convert_to(canonical_content,'UTF8')),'hex')),
 UNIQUE (version,content_hash)
);

CREATE TABLE business.v4_demo_tenants (
 id uuid PRIMARY KEY,
 organization_id uuid NOT NULL UNIQUE REFERENCES business.organizations(id),
 fixture_version text NOT NULL,
 fixture_digest text NOT NULL,
 reset_epoch bigint NOT NULL DEFAULT 0 CHECK (reset_epoch>=0),
 created_at timestamptz NOT NULL,
 expires_at timestamptz NOT NULL,
 revoked_at timestamptz,
 retain_until timestamptz NOT NULL,
 UNIQUE (id,organization_id),
 FOREIGN KEY (fixture_version,fixture_digest)
   REFERENCES business.v4_demo_fixture_versions(version,content_hash),
 CHECK (expires_at=created_at+interval '30 minutes'),
 CHECK (retain_until=expires_at+interval '24 hours'),
 CHECK (revoked_at IS NULL OR revoked_at>=created_at)
);

CREATE TABLE business.v4_demo_shops (
 tenant_id uuid NOT NULL,
 organization_id uuid NOT NULL,
 template_key text NOT NULL CHECK (template_key IN ('v4-shop-a','v4-shop-b')),
 shop_id uuid NOT NULL UNIQUE,
 PRIMARY KEY (tenant_id,template_key),
 UNIQUE (tenant_id,shop_id),
 FOREIGN KEY (tenant_id,organization_id)
   REFERENCES business.v4_demo_tenants(id,organization_id),
 FOREIGN KEY (organization_id,shop_id) REFERENCES business.shops(organization_id,id)
);

CREATE TABLE business.v4_demo_personas (
 tenant_id uuid NOT NULL,
 organization_id uuid NOT NULL,
 persona_id text NOT NULL CHECK (persona_id IN ('operator','approver','restricted_admin')),
 principal_id uuid NOT NULL UNIQUE,
 identity_id uuid NOT NULL UNIQUE,
 PRIMARY KEY (tenant_id,persona_id),
 UNIQUE (tenant_id,persona_id,principal_id,identity_id),
 FOREIGN KEY (tenant_id,organization_id)
   REFERENCES business.v4_demo_tenants(id,organization_id),
 FOREIGN KEY (organization_id,principal_id)
   REFERENCES business.principals(organization_id,id),
 FOREIGN KEY (organization_id,identity_id,principal_id)
   REFERENCES business.identities(organization_id,id,principal_id)
);

CREATE TABLE business.v4_demo_bootstraps (
 id uuid PRIMARY KEY,
 token_hash text NOT NULL UNIQUE CHECK (token_hash ~ '^[a-f0-9]{64}$'),
 csrf_digest text NOT NULL CHECK (csrf_digest ~ '^[a-f0-9]{64}$'),
 key_version text NOT NULL,
 created_at timestamptz NOT NULL,
 expires_at timestamptz NOT NULL,
 create_request_key uuid,
 consumed_at timestamptz,
 CHECK (expires_at=created_at+interval '300 seconds'),
 CHECK (consumed_at IS NULL OR
   (create_request_key IS NOT NULL AND consumed_at>=created_at))
);

CREATE TABLE business.v4_demo_sessions (
 id uuid PRIMARY KEY,
 tenant_id uuid NOT NULL UNIQUE REFERENCES business.v4_demo_tenants(id),
 bootstrap_id uuid NOT NULL UNIQUE REFERENCES business.v4_demo_bootstraps(id),
 creation_request_key uuid NOT NULL,
 token_hash text NOT NULL UNIQUE CHECK (token_hash ~ '^[a-f0-9]{64}$'),
 persona_id text NOT NULL,
 principal_id uuid NOT NULL,
 identity_id uuid NOT NULL,
 bound_web_session_id uuid NOT NULL UNIQUE REFERENCES business.web_sessions(id),
 auth_version integer NOT NULL CHECK (auth_version>0),
 auth_generation bigint NOT NULL DEFAULT 0 CHECK (auth_generation>=0),
 reset_epoch bigint NOT NULL DEFAULT 0 CHECK (reset_epoch>=0),
 csrf_nonce uuid NOT NULL,
 csrf_digest text NOT NULL CHECK (csrf_digest ~ '^[a-f0-9]{64}$'),
 key_version text NOT NULL,
 created_at timestamptz NOT NULL,
 expires_at timestamptz NOT NULL,
 revoked_at timestamptz,
 FOREIGN KEY (tenant_id,persona_id,principal_id,identity_id)
   REFERENCES business.v4_demo_personas(tenant_id,persona_id,principal_id,identity_id),
 CHECK (expires_at=created_at+interval '30 minutes'),
 CHECK (revoked_at IS NULL OR revoked_at>=created_at)
);

CREATE TABLE business.v4_demo_receipts (
 id uuid PRIMARY KEY,
 owner_session_id uuid NOT NULL REFERENCES business.v4_demo_sessions(id),
 tenant_id uuid NOT NULL REFERENCES business.v4_demo_tenants(id),
 operation text NOT NULL CHECK (operation IN ('session_create','persona','reset','logout')),
 request_key uuid NOT NULL,
 canonical_request text NOT NULL,
 payload_digest text NOT NULL CHECK (payload_digest ~ '^[a-f0-9]{64}$'),
 epoch_before bigint NOT NULL CHECK (epoch_before>=0),
 generation_before bigint NOT NULL CHECK (generation_before>=0),
 reset_epoch bigint NOT NULL CHECK (reset_epoch>=0),
 auth_generation bigint NOT NULL CHECK (auth_generation>=0),
 committed_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 retain_until timestamptz NOT NULL,
 UNIQUE (owner_session_id,operation,request_key),
 CHECK (payload_digest=encode(sha256(convert_to(canonical_request,'UTF8')),'hex')),
 CHECK (jsonb_typeof(canonical_request::jsonb)='object'),
 CHECK (octet_length(canonical_request)<=4096),
 CHECK (retain_until>committed_at)
);

CREATE TABLE business.v4_demo_events (
 id uuid PRIMARY KEY,
 tenant_id uuid NOT NULL REFERENCES business.v4_demo_tenants(id),
 owner_session_id uuid NOT NULL REFERENCES business.v4_demo_sessions(id),
 receipt_id uuid NOT NULL REFERENCES business.v4_demo_receipts(id),
 event_kind text NOT NULL CHECK (event_kind IN
   ('demo.session_created','demo.persona_changed','demo.reset_committed',
    'demo.session_revoked','demo.seed_materialized')),
 reset_epoch bigint NOT NULL CHECK (reset_epoch>=0),
 auth_generation bigint NOT NULL CHECK (auth_generation>=0),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 UNIQUE (receipt_id,event_kind)
);

CREATE TABLE business.v4_demo_overlays (
 tenant_id uuid NOT NULL,
 shop_id uuid NOT NULL,
 reset_epoch bigint NOT NULL CHECK (reset_epoch>=0),
 object_kind text NOT NULL CHECK (object_kind IN ('product_attribute','fixture_note')),
 object_key text NOT NULL CHECK (length(object_key) BETWEEN 1 AND 128),
 version integer NOT NULL CHECK (version>0),
 payload jsonb NOT NULL,
 canonical_payload text NOT NULL,
 payload_digest text NOT NULL CHECK (payload_digest ~ '^[a-f0-9]{64}$'),
 PRIMARY KEY (tenant_id,shop_id,reset_epoch,object_kind,object_key),
 FOREIGN KEY (tenant_id,shop_id) REFERENCES business.v4_demo_shops(tenant_id,shop_id),
 CHECK (jsonb_typeof(payload)='object'),
 CHECK (canonical_payload::jsonb=payload),
 CHECK (octet_length(canonical_payload)<=16384),
 CHECK (payload_digest=encode(sha256(convert_to(canonical_payload,'UTF8')),'hex'))
);

CREATE TABLE business.v4_demo_rate_attempts (
 id uuid PRIMARY KEY,
 peer_digest text NOT NULL CHECK (peer_digest ~ '^[a-f0-9]{64}$'),
 operation text NOT NULL CHECK (operation IN ('bootstrap','session_create')),
 occurred_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

CREATE INDEX v4_demo_capacity ON business.v4_demo_tenants(expires_at)
 WHERE revoked_at IS NULL;
CREATE INDEX v4_demo_session_live ON business.v4_demo_sessions(expires_at)
 WHERE revoked_at IS NULL;
CREATE INDEX v4_demo_receipt_retention ON business.v4_demo_receipts(retain_until,tenant_id);
CREATE INDEX v4_demo_bootstrap_expiry ON business.v4_demo_bootstraps(expires_at);
CREATE INDEX v4_demo_rate_window ON business.v4_demo_rate_attempts
 (peer_digest,operation,occurred_at);
"""

TABLES = (
    "fixture_versions",
    "tenants",
    "shops",
    "personas",
    "bootstraps",
    "sessions",
    "receipts",
    "events",
    "overlays",
    "rate_attempts",
)

FUNCTIONS = r"""
CREATE FUNCTION business.v4_demo_guard() RETURNS trigger LANGUAGE plpgsql
SET search_path=pg_catalog,business AS $$
DECLARE n jsonb; o jsonb; tenant uuid; deadline timestamptz;
BEGIN
 IF TG_OP='TRUNCATE' THEN
  RAISE EXCEPTION 'demo history immutable' USING ERRCODE='23514';
 END IF;
 IF TG_OP='DELETE' THEN
  IF TG_TABLE_NAME='v4_demo_overlays' THEN RETURN OLD; END IF;
  o:=to_jsonb(OLD);
  tenant:=CASE WHEN TG_TABLE_NAME='v4_demo_tenants' THEN (o->>'id')::uuid
    ELSE (o->>'tenant_id')::uuid END;
  IF tenant IS NOT NULL THEN
   SELECT retain_until INTO deadline FROM business.v4_demo_tenants WHERE id=tenant;
  ELSIF TG_TABLE_NAME IN ('v4_demo_bootstraps','v4_demo_rate_attempts') THEN
   deadline:=coalesce((o->>'expires_at')::timestamptz,(o->>'occurred_at')::timestamptz)
     +interval '24 hours';
  END IF;
  IF current_user<>pg_get_userbyid((SELECT relowner FROM pg_class WHERE oid=TG_RELID))
    OR deadline IS NULL OR clock_timestamp()<deadline OR TG_TABLE_NAME='v4_demo_fixture_versions'
  THEN RAISE EXCEPTION 'demo retention immutable' USING ERRCODE='23514'; END IF;
  RETURN OLD;
 END IF;
 n:=to_jsonb(NEW);
 IF TG_TABLE_NAME='v4_demo_overlays' THEN
  IF NOT EXISTS(SELECT 1 FROM business.v4_demo_tenants t JOIN business.v4_demo_sessions s
   ON s.tenant_id=t.id WHERE t.id=NEW.tenant_id AND t.reset_epoch=NEW.reset_epoch
   AND s.reset_epoch=t.reset_epoch AND t.revoked_at IS NULL AND s.revoked_at IS NULL
   AND clock_timestamp()<t.expires_at) THEN
   RAISE EXCEPTION 'demo overlay stale' USING ERRCODE='23514'; END IF;
 END IF;
 IF TG_OP='INSERT' THEN RETURN NEW; END IF;
 o:=to_jsonb(OLD);
 IF TG_TABLE_NAME='v4_demo_bootstraps' THEN
  IF (n-ARRAY['create_request_key','consumed_at'])<>(o-ARRAY['create_request_key','consumed_at'])
   OR (OLD.create_request_key IS NOT NULL AND
      NEW.create_request_key IS DISTINCT FROM OLD.create_request_key)
   OR (OLD.consumed_at IS NOT NULL AND NEW.consumed_at IS DISTINCT FROM OLD.consumed_at)
  THEN RAISE EXCEPTION 'demo bootstrap immutable' USING ERRCODE='23514'; END IF;
 ELSIF TG_TABLE_NAME='v4_demo_tenants' THEN
  IF (n-ARRAY['reset_epoch','revoked_at'])<>(o-ARRAY['reset_epoch','revoked_at'])
   OR NEW.reset_epoch NOT IN (OLD.reset_epoch,OLD.reset_epoch+1)
   OR (OLD.revoked_at IS NOT NULL AND NEW.revoked_at IS DISTINCT FROM OLD.revoked_at)
  THEN RAISE EXCEPTION 'demo tenant immutable' USING ERRCODE='23514'; END IF;
 ELSIF TG_TABLE_NAME='v4_demo_sessions' THEN
  IF (n-ARRAY['persona_id','principal_id','identity_id','bound_web_session_id','auth_version',
     'auth_generation','reset_epoch','csrf_nonce','csrf_digest','revoked_at']) <>
    (o-ARRAY['persona_id','principal_id','identity_id','bound_web_session_id','auth_version',
     'auth_generation','reset_epoch','csrf_nonce','csrf_digest','revoked_at'])
   OR NEW.reset_epoch NOT IN (OLD.reset_epoch,OLD.reset_epoch+1)
   OR (OLD.revoked_at IS NOT NULL AND NEW.revoked_at IS DISTINCT FROM OLD.revoked_at)
  THEN RAISE EXCEPTION 'demo session immutable' USING ERRCODE='23514'; END IF;
  IF (n-ARRAY['revoked_at'])<>(o-ARRAY['revoked_at']) THEN
   IF NEW.auth_generation<>OLD.auth_generation+1
    OR NEW.bound_web_session_id=OLD.bound_web_session_id OR NEW.csrf_nonce=OLD.csrf_nonce
    OR NEW.csrf_digest=OLD.csrf_digest OR NOT EXISTS(
     SELECT 1 FROM business.web_sessions w WHERE w.id=OLD.bound_web_session_id
     AND w.revoked_at IS NOT NULL)
   THEN RAISE EXCEPTION 'demo binding rotation required' USING ERRCODE='23514'; END IF;
  END IF;
 ELSE
  RAISE EXCEPTION 'demo history immutable' USING ERRCODE='23514';
 END IF;
 RETURN NEW;
END $$;

CREATE FUNCTION business.v4_demo_commit_guard() RETURNS trigger LANGUAGE plpgsql
SET search_path=pg_catalog,business AS $$
DECLARE body jsonb; tid uuid; t business.v4_demo_tenants;
 s business.v4_demo_sessions; w business.web_sessions; req jsonb;
BEGIN
 body:=to_jsonb(NEW);
 tid:=CASE WHEN TG_TABLE_NAME='v4_demo_tenants' THEN NEW.id
   ELSE (body->>'tenant_id')::uuid END;
 SELECT * INTO t FROM business.v4_demo_tenants WHERE id=tid;
 SELECT * INTO s FROM business.v4_demo_sessions WHERE tenant_id=tid;
 IF t.id IS NULL OR s.id IS NULL OR t.expires_at<>s.expires_at
  OR t.reset_epoch<>s.reset_epoch OR (t.revoked_at IS NULL)<>(s.revoked_at IS NULL)
  OR (SELECT count(*) FROM business.v4_demo_shops WHERE tenant_id=tid)<>2
  OR (SELECT count(*) FROM business.v4_demo_personas WHERE tenant_id=tid)<>3
 THEN RAISE EXCEPTION 'demo binding incomplete' USING ERRCODE='23514'; END IF;
 SELECT * INTO w FROM business.web_sessions WHERE id=s.bound_web_session_id;
 IF w.id IS NULL OR w.kind<>'session' OR
  (w.organization_id,w.principal_id,w.identity_id,w.auth_version) IS DISTINCT FROM
  (t.organization_id,s.principal_id,s.identity_id,s.auth_version)
  OR w.absolute_expires_at>t.expires_at OR w.idle_expires_at>t.expires_at
  OR w.token_hash=s.token_hash
  OR EXISTS(SELECT 1 FROM business.v4_demo_bootstraps b WHERE b.token_hash=w.token_hash)
  OR (s.revoked_at IS NOT NULL AND w.revoked_at IS NULL)
 THEN RAISE EXCEPTION 'demo private binding invalid' USING ERRCODE='23514'; END IF;
 IF s.revoked_at IS NULL AND (w.revoked_at IS NOT NULL OR
   clock_timestamp()>=least(w.absolute_expires_at,w.idle_expires_at,t.expires_at)
   OR NOT EXISTS(SELECT 1 FROM business.principals p JOIN business.identities i
     ON i.organization_id=p.organization_id AND i.principal_id=p.id
     JOIN business.web_credentials c ON c.organization_id=p.organization_id
     AND c.principal_id=p.id AND c.identity_id=i.id
     WHERE p.id=s.principal_id AND p.organization_id=t.organization_id AND p.enabled
     AND p.auth_version=s.auth_version AND i.id=s.identity_id AND i.provider='web' AND c.enabled)
 ) THEN RAISE EXCEPTION 'demo credential invalid' USING ERRCODE='23514'; END IF;
 IF EXISTS(SELECT 1 FROM business.v4_demo_shops m JOIN business.shops sh ON sh.id=m.shop_id
   WHERE m.tenant_id=tid AND (sh.organization_id<>t.organization_id OR sh.adapter_kind<>'mock'
    OR sh.environment<>'mock' OR sh.external_shop_key<>m.template_key
    OR sh.currency<>CASE m.template_key WHEN 'v4-shop-a' THEN 'TWD' ELSE 'CNY' END
    OR sh.timezone<>CASE m.template_key WHEN 'v4-shop-a' THEN 'Asia/Taipei' ELSE
 'Asia/Shanghai' END))
 THEN RAISE EXCEPTION 'demo shop source invalid' USING ERRCODE='23514'; END IF;
 IF TG_TABLE_NAME='v4_demo_sessions' AND TG_OP='UPDATE' THEN
  IF NOT EXISTS(SELECT 1 FROM business.v4_demo_receipts r WHERE r.owner_session_id=s.id
    AND r.epoch_before=OLD.reset_epoch AND r.generation_before=OLD.auth_generation
    AND r.reset_epoch=NEW.reset_epoch AND r.auth_generation=NEW.auth_generation
    AND r.operation=CASE WHEN NEW.revoked_at IS NOT NULL THEN 'logout'
      WHEN NEW.reset_epoch<>OLD.reset_epoch THEN 'reset' ELSE 'persona' END)
  THEN RAISE EXCEPTION 'demo effect receipt missing' USING ERRCODE='23514'; END IF;
 END IF;
 IF TG_TABLE_NAME='v4_demo_tenants' AND TG_OP='UPDATE' AND NEW.reset_epoch<>OLD.reset_epoch THEN
  IF NOT EXISTS(SELECT 1 FROM business.v4_demo_receipts r WHERE r.tenant_id=tid
   AND r.operation='reset' AND r.epoch_before=OLD.reset_epoch AND r.reset_epoch=NEW.reset_epoch)
  THEN RAISE EXCEPTION 'demo reset receipt missing' USING ERRCODE='23514'; END IF;
 END IF;
 IF TG_TABLE_NAME='v4_demo_receipts' THEN
  req:=NEW.canonical_request::jsonb;
  IF NEW.owner_session_id<>s.id OR NEW.retain_until<>t.retain_until
   OR (req#>>'{body,request_key}') IS DISTINCT FROM NEW.request_key::text
   OR req->>'method'<>'POST' OR req->>'path' IS DISTINCT FROM
    '/api/v4/demo/'||CASE NEW.operation WHEN 'session_create' THEN 'sessions' ELSE NEW.operation END
   OR NOT EXISTS(SELECT 1 FROM business.v4_demo_events e WHERE e.receipt_id=NEW.id
      AND e.tenant_id=tid AND e.owner_session_id=s.id
      AND e.reset_epoch=NEW.reset_epoch AND e.auth_generation=NEW.auth_generation
      AND e.event_kind=CASE NEW.operation WHEN 'session_create' THEN 'demo.session_created'
       WHEN 'persona' THEN 'demo.persona_changed' WHEN 'reset' THEN 'demo.reset_committed'
       ELSE 'demo.session_revoked' END)
  THEN RAISE EXCEPTION 'demo receipt binding invalid' USING ERRCODE='23514'; END IF;
  IF (NEW.operation='session_create' AND (NEW.request_key<>s.creation_request_key
     OR NEW.reset_epoch<>0 OR NEW.auth_generation<>0 OR NOT EXISTS(
      SELECT 1 FROM business.v4_demo_events WHERE receipt_id=NEW.id AND
 event_kind='demo.seed_materialized')))
   OR (NEW.operation='persona' AND (NEW.reset_epoch<>NEW.epoch_before
      OR NEW.auth_generation<>NEW.generation_before+1))
   OR (NEW.operation='reset' AND (NEW.reset_epoch<>NEW.epoch_before+1
      OR NEW.auth_generation<>NEW.generation_before+1))
   OR (NEW.operation='logout' AND (NEW.reset_epoch<>NEW.epoch_before
      OR NEW.auth_generation<>NEW.generation_before))
  THEN RAISE EXCEPTION 'demo receipt transition invalid' USING ERRCODE='23514'; END IF;
 END IF;
 RETURN NULL;
END $$;

CREATE FUNCTION business.v4_demo_provision(
 bid uuid,rkey uuid,request_text text,request_digest text,public_hash text,
 sid uuid,wid uuid,csrf_hash text,nonce uuid,private_hash text,
 private_csrf_hash text,keyver text,credential_hash text)
RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,business AS $$
DECLARE b business.v4_demo_bootstraps; f business.v4_demo_fixture_versions;
 tid uuid:=gen_random_uuid(); org uuid:=gen_random_uuid(); sh uuid; pid uuid; iid uuid;
 persona text; skey text; p_role text; operator_id uuid; operator_identity uuid; auth integer;
 stamp timestamptz; expiry timestamptz; rid uuid:=gen_random_uuid(); body jsonb;
BEGIN
 PERFORM pg_advisory_xact_lock(1446261840,1);
 SELECT * INTO b FROM business.v4_demo_bootstraps WHERE id=bid FOR UPDATE;
 stamp:=clock_timestamp(); expiry:=stamp+interval '30 minutes';
 body:=request_text::jsonb;
 SELECT * INTO f FROM business.v4_demo_fixture_versions WHERE version='v4-demo-seed-1';
 IF b.id IS NULL OR b.consumed_at IS NOT NULL OR b.create_request_key IS DISTINCT FROM rkey
  OR stamp>=b.expires_at OR f.version IS NULL OR public_hash=private_hash
  OR public_hash=b.token_hash OR private_hash=b.token_hash
  OR body->>'method'<>'POST' OR body->>'path'<>'/api/v4/demo/sessions'
  OR body#>>'{body,request_key}' IS DISTINCT FROM rkey::text
  OR body#>>'{body,fixture_version}' IS DISTINCT FROM f.version
  OR (body->'body')-ARRAY['request_key','fixture_version']<>'{}'::jsonb
  OR request_digest<>encode(sha256(convert_to(request_text,'UTF8')),'hex')
  OR EXISTS(SELECT 1 FROM business.web_sessions WHERE token_hash=public_hash)
  OR EXISTS(SELECT 1 FROM business.v4_demo_sessions WHERE token_hash=private_hash)
 THEN RAISE EXCEPTION 'demo provision denied' USING ERRCODE='23514'; END IF;
 IF (SELECT count(*) FROM business.v4_demo_tenants t JOIN business.v4_demo_sessions s
   ON s.tenant_id=t.id WHERE t.revoked_at IS NULL AND s.revoked_at IS NULL AND
 t.expires_at>stamp)>=3
 THEN RAISE EXCEPTION 'demo capacity limit' USING ERRCODE='23514'; END IF;
 INSERT INTO business.organizations(id,name,feishu_app_id,feishu_tenant_key)
 VALUES(org,'V4 synthetic demo '||tid,'v4-demo-app-'||tid,'v4-demo-tenant-'||tid);
 INSERT INTO business.v4_demo_tenants
  (id,organization_id,fixture_version,fixture_digest,created_at,expires_at,retain_until)
 VALUES(tid,org,f.version,f.content_hash,stamp,expiry,expiry+interval '24 hours');
 FOREACH skey IN ARRAY ARRAY['v4-shop-a','v4-shop-b'] LOOP
  sh:=gen_random_uuid();
  INSERT INTO business.shops(id,organization_id,adapter_kind,external_shop_key,timezone,
   currency,config_ref,environment) VALUES(sh,org,'mock',skey,
   CASE skey WHEN 'v4-shop-a' THEN 'Asia/Taipei' ELSE 'Asia/Shanghai' END,
   CASE skey WHEN 'v4-shop-a' THEN 'TWD' ELSE 'CNY' END,
   'v4-demo:'||tid||':'||skey||':'||'v1','mock');
  INSERT INTO business.v4_demo_shops VALUES(tid,org,skey,sh);
 END LOOP;
 FOREACH persona IN ARRAY ARRAY['operator','approver','restricted_admin'] LOOP
  pid:=gen_random_uuid(); iid:=gen_random_uuid();
  p_role:=CASE persona WHEN 'restricted_admin' THEN 'admin' ELSE persona END;
  INSERT INTO business.principals(id,organization_id,display_name,roles)
   VALUES(pid,org,'V4 demo '||persona,ARRAY[p_role]);
  INSERT INTO business.identities(id,organization_id,principal_id,provider,app_id,tenant_key,
 external_subject)
   VALUES(iid,org,pid,'web','v4-demo-app-'||tid,'v4-demo-tenant-'||tid,
    'v4.'||replace(tid::text,'-','')||'.'||persona);
  FOR sh IN SELECT shop_id FROM business.v4_demo_shops WHERE tenant_id=tid
   AND (persona='operator' OR (persona='approver' AND template_key='v4-shop-a')) ORDER BY
 shop_id LOOP
   INSERT INTO business.principal_shop_scopes VALUES(org,sh,pid,true);
   INSERT INTO business.principal_role_shop_grants VALUES(org,sh,pid,p_role,true);
  END LOOP;
  INSERT INTO business.web_credentials(login,organization_id,principal_id,identity_id,
 password_hash,enabled)
   VALUES('v4.'||replace(tid::text,'-','')||'.'||persona,org,pid,iid,credential_hash,true);
  INSERT INTO business.v4_demo_personas VALUES(tid,org,persona,pid,iid);
  IF persona='operator' THEN operator_id:=pid; operator_identity:=iid; END IF;
 END LOOP;
 SELECT auth_version INTO auth FROM business.principals WHERE id=operator_id;
 INSERT INTO business.web_sessions(id,token_hash,kind,organization_id,principal_id,identity_id,
  auth_version,csrf_digest,key_version,created_at,last_seen_at,absolute_expires_at,idle_expires_at)
 VALUES(wid,private_hash,'session',org,operator_id,operator_identity,auth,
  private_csrf_hash,keyver,stamp,stamp,expiry,expiry);
 INSERT INTO business.v4_demo_sessions
  (id,tenant_id,bootstrap_id,creation_request_key,token_hash,persona_id,principal_id,identity_id,
   bound_web_session_id,auth_version,csrf_nonce,csrf_digest,key_version,created_at,expires_at)
 VALUES(sid,tid,bid,rkey,public_hash,'operator',operator_id,operator_identity,wid,auth,
  nonce,csrf_hash,keyver,stamp,expiry);
 INSERT INTO business.v4_demo_receipts(id,owner_session_id,tenant_id,operation,request_key,
  canonical_request,payload_digest,epoch_before,generation_before,reset_epoch,auth_generation,
 retain_until)
 VALUES(rid,sid,tid,'session_create',rkey,request_text,request_digest,0,0,0,0,expiry+interval
 '24 hours');
 INSERT INTO business.v4_demo_events(id,tenant_id,owner_session_id,receipt_id,event_kind,
 reset_epoch,auth_generation)
 VALUES(gen_random_uuid(),tid,sid,rid,'demo.session_created',0,0),
  (gen_random_uuid(),tid,sid,rid,'demo.seed_materialized',0,0);
 UPDATE business.v4_demo_bootstraps SET consumed_at=stamp WHERE id=bid;
 RETURN tid;
END $$;
"""


def upgrade() -> None:
    op.execute(DDL)
    op.execute(FUNCTIONS)
    for suffix in TABLES:
        table = "business.v4_demo_" + suffix
        op.execute(f"REVOKE ALL ON {table} FROM PUBLIC")
        op.execute(
            f"CREATE TRIGGER v4_demo_guard BEFORE INSERT OR UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION business.v4_demo_guard()"
        )
        op.execute(
            f"CREATE TRIGGER v4_demo_no_truncate BEFORE TRUNCATE ON {table} "
            "FOR EACH STATEMENT EXECUTE FUNCTION business.v4_demo_guard()"
        )
        if suffix in ("tenants", "sessions", "receipts", "events"):
            op.execute(
                f"CREATE CONSTRAINT TRIGGER v4_demo_commit AFTER INSERT OR UPDATE ON {table} "
                "DEFERRABLE INITIALLY DEFERRED FOR EACH ROW "
                "EXECUTE FUNCTION business.v4_demo_commit_guard()"
            )
    for signature in (
        "v4_demo_guard()",
        "v4_demo_commit_guard()",
        "v4_demo_provision(uuid,uuid,text,text,text,uuid,uuid,text,uuid,text,text,text,text)",
    ):
        op.execute(f"REVOKE ALL ON FUNCTION business.{signature} FROM PUBLIC")


def downgrade() -> None:
    raise RuntimeError("destructive downgrade disabled; restore reviewed backup")
