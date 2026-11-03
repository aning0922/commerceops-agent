"""Immutable synthetic candidates, explicit decisions, atomically saved internal drafts."""

from alembic import op

revision = "0023_p6_copy_drafts"
down_revision = "0022"  # Reserved by Root; exact frozen parent will be handed over before PG.
branch_labels = None
depends_on = None

DDL = r"""
CREATE TABLE business.p6_copy_products (
 id uuid PRIMARY KEY,organization_id uuid NOT NULL,shop_id uuid NOT NULL,
 payload text NOT NULL,evidence_id text NOT NULL,expires_at timestamptz NOT NULL,
 captured_at timestamptz NOT NULL,enabled boolean NOT NULL DEFAULT true,
 UNIQUE(organization_id,shop_id,id),
 FOREIGN KEY(organization_id,shop_id) REFERENCES business.shops(organization_id,id),
 CHECK(evidence_id=encode(sha256(convert_to(payload,'UTF8')),'hex')),
 CHECK((payload::jsonb->>'source_kind'='product' AND payload::jsonb->>'field_path'='title'
   AND jsonb_typeof(payload::jsonb->'snapshot')='object'
   AND jsonb_typeof(payload::jsonb#>'{snapshot,title}')='string') IS TRUE),
 CHECK((payload::jsonb#>>'{snapshot,source_kind}'='synthetic') IS TRUE),
 CHECK((payload::jsonb#>>'{snapshot,scope,organization_id}'=organization_id::text
   AND payload::jsonb#>>'{snapshot,scope,shop_id}'=shop_id::text) IS TRUE),
 CHECK((payload::jsonb->>'text'=payload::jsonb#>>'{snapshot,title}') IS TRUE),
 CHECK((payload::jsonb#>>'{snapshot,revoked}')::boolean IS FALSE),
 CHECK(((payload::jsonb#>>'{snapshot,captured_at}')::timestamptz=captured_at) IS TRUE),
 CHECK(((payload::jsonb#>>'{snapshot,expires_at}')::timestamptz=expires_at
  AND expires_at>captured_at) IS TRUE)
);
CREATE TABLE business.p6_copy_candidates (
 id uuid PRIMARY KEY,organization_id uuid NOT NULL,shop_id uuid NOT NULL,
 owner_id uuid NOT NULL,reviewer_id uuid NOT NULL,owner_identity uuid NOT NULL,
 owner_session uuid NOT NULL,owner_auth_version bigint NOT NULL,
 registry_id uuid NOT NULL,product_id uuid NOT NULL,request_key uuid NOT NULL,
 request_payload text NOT NULL,request_hash text NOT NULL,payload text NOT NULL,
 candidate_hash text NOT NULL,created_at timestamptz NOT NULL,expires_at timestamptz NOT NULL,
 UNIQUE(organization_id,shop_id,id,candidate_hash),UNIQUE(organization_id,owner_id,request_key),
 FOREIGN KEY(organization_id,shop_id) REFERENCES business.shops(organization_id,id),
 FOREIGN KEY(organization_id,owner_id) REFERENCES business.principals(organization_id,id),
 FOREIGN KEY(organization_id,reviewer_id) REFERENCES business.principals(organization_id,id),
 FOREIGN KEY(organization_id,shop_id,registry_id)
  REFERENCES business.p6_knowledge_registries(organization_id,shop_id,id),
 FOREIGN KEY(organization_id,shop_id,product_id)
  REFERENCES business.p6_copy_products(organization_id,shop_id,id),
 CHECK(request_hash=encode(sha256(convert_to(request_payload,'UTF8')),'hex')),
 CHECK(candidate_hash=encode(sha256(convert_to(payload,'UTF8')),'hex')),
 CHECK((jsonb_typeof(payload::jsonb->'claims')='array'
  AND jsonb_array_length(payload::jsonb->'claims') BETWEEN 2 AND 6
  AND jsonb_typeof(payload::jsonb#>'{retrieval,hits}')='array'
  AND jsonb_array_length(payload::jsonb#>'{retrieval,hits}') BETWEEN 1 AND 5
  AND jsonb_typeof(payload::jsonb->'text')='string'
  AND payload::jsonb#>'{retrieval,complete}'='true'::jsonb
  AND payload::jsonb#>'{retrieval,exhaustive}'='true'::jsonb
  AND payload::jsonb#>>'{retrieval,evidence_mode}'='synthetic_vector') IS TRUE),
 CHECK(created_at<expires_at AND expires_at<=created_at+interval '15 minutes'),
 CHECK((payload::jsonb->>'candidate_id'=id::text AND payload::jsonb->>'candidate_version'='v1'
  AND payload::jsonb->>'owner_id'=owner_id::text
  AND payload::jsonb->>'reviewer_id'=reviewer_id::text
  AND payload::jsonb->>'product_source_id'=product_id::text
  AND payload::jsonb#>>'{retrieval,registry_id}'=registry_id::text
  AND payload::jsonb#>>'{retrieval,scope,organization_id}'=organization_id::text
  AND payload::jsonb#>>'{retrieval,scope,shop_id}'=shop_id::text
  AND payload::jsonb->>'narrative_mode'='template'
  AND payload::jsonb->'publication_allowed'='false'::jsonb) IS TRUE),
 CHECK(((payload::jsonb->>'as_of')::timestamptz=created_at
   AND (payload::jsonb->>'expires_at')::timestamptz=expires_at) IS TRUE),
 CHECK((request_payload::jsonb->>'shop_id'=shop_id::text
  AND request_payload::jsonb->>'product_source_id'=product_id::text
  AND request_payload::jsonb->>'registry_id'=registry_id::text
  AND request_payload::jsonb->>'reviewer_id'=reviewer_id::text
  AND request_payload::jsonb->>'registry_digest'=
   payload::jsonb#>>'{retrieval,registry_digest}') IS TRUE)
);
CREATE TABLE business.p6_copy_decisions (
 id uuid PRIMARY KEY,organization_id uuid NOT NULL,shop_id uuid NOT NULL,
 candidate_id uuid NOT NULL,candidate_hash text NOT NULL,actor_id uuid NOT NULL,
 identity_id uuid NOT NULL,session_id uuid NOT NULL,auth_version bigint NOT NULL,
 request_key uuid NOT NULL,action text NOT NULL CHECK(action IN ('approve','reject')),
 reason text NOT NULL CHECK(length(btrim(reason)) BETWEEN 1 AND 500),
 request_payload text NOT NULL,request_hash text NOT NULL,
 decided_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 UNIQUE(organization_id,actor_id,request_key),UNIQUE(candidate_id),
 UNIQUE(organization_id,shop_id,id,candidate_id,candidate_hash,action),
 FOREIGN KEY(organization_id,shop_id,candidate_id,candidate_hash)
 REFERENCES business.p6_copy_candidates(organization_id,shop_id,id,candidate_hash),
 FOREIGN KEY(organization_id,actor_id) REFERENCES business.principals(organization_id,id),
 CHECK(request_hash=encode(sha256(convert_to(request_payload,'UTF8')),'hex')),
 CHECK((request_payload::jsonb->>'candidate_id'=candidate_id::text
  AND request_payload::jsonb->>'candidate_hash'=candidate_hash
  AND request_payload::jsonb->>'candidate_version'='v1'
  AND request_payload::jsonb->>'action'=action
  AND request_payload::jsonb->>'reason'=reason) IS TRUE)
);
CREATE TABLE business.p6_copy_drafts (
 id uuid PRIMARY KEY,organization_id uuid NOT NULL,shop_id uuid NOT NULL,
 candidate_id uuid NOT NULL,candidate_hash text NOT NULL,decision_id uuid NOT NULL,
 action text NOT NULL DEFAULT 'approve' CHECK(action='approve'),text text NOT NULL,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),UNIQUE(candidate_id),UNIQUE(decision_id),
 FOREIGN KEY(organization_id,shop_id,decision_id,candidate_id,candidate_hash,action)
 REFERENCES business.p6_copy_decisions
 (organization_id,shop_id,id,candidate_id,candidate_hash,action)
);
CREATE FUNCTION business.p6_copy_reviewer(reviewer uuid,org uuid,shop uuid) RETURNS boolean
LANGUAGE sql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,business AS $$
 SELECT EXISTS(SELECT 1 FROM business.principals p
 JOIN business.principal_shop_scopes s ON s.principal_id=p.id
  AND s.organization_id=p.organization_id
 JOIN business.principal_role_shop_grants g ON g.principal_id=s.principal_id
  AND g.organization_id=s.organization_id AND g.shop_id=s.shop_id
 WHERE p.id=reviewer AND p.organization_id=org AND p.enabled AND 'approver'=ANY(p.roles)
  AND s.shop_id=shop AND s.enabled AND g.enabled AND g.role='approver' FOR SHARE OF p,s,g)
$$;
CREATE FUNCTION business.p6_lock_copy_product(actor uuid,org uuid,shop uuid,identity uuid,
 auth bigint,pid uuid) RETURNS boolean LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path=pg_catalog,business AS $$
BEGIN
 IF NOT business.lock_p3_permission(actor,org,shop,identity,auth,'operator') THEN
  RETURN false;
 END IF;
 PERFORM 1 FROM business.p6_copy_products WHERE id=pid AND organization_id=org AND shop_id=shop
  AND enabled AND captured_at<=clock_timestamp() AND clock_timestamp()<expires_at FOR SHARE;
 RETURN FOUND;
END $$;
CREATE FUNCTION business.p6_copy_session(sid uuid,actor uuid,org uuid,identity uuid,auth bigint)
RETURNS boolean LANGUAGE sql VOLATILE SET search_path=pg_catalog,business AS $$
 SELECT EXISTS(SELECT 1 FROM business.web_sessions s WHERE s.id=sid AND s.kind='session'
  AND s.principal_id=actor AND s.organization_id=org AND s.identity_id=identity
  AND s.auth_version=auth AND s.revoked_at IS NULL
  AND clock_timestamp()<least(s.absolute_expires_at,s.idle_expires_at) FOR SHARE OF s)
$$;
CREATE FUNCTION business.p6_copy_sources_current(cid uuid) RETURNS boolean LANGUAGE sql VOLATILE
SET search_path=pg_catalog,business AS $$
 SELECT coalesce((SELECT c.expires_at>clock_timestamp() AND p.enabled AND r.enabled
  AND p.captured_at<=clock_timestamp() AND clock_timestamp()<p.expires_at
  AND c.payload::jsonb->'product'=p.payload::jsonb||jsonb_build_object('evidence_id',p.evidence_id)
  AND c.payload::jsonb#>>'{retrieval,registry_digest}'=r.manifest_digest
  AND NOT EXISTS(SELECT 1 FROM jsonb_array_elements(c.payload::jsonb#>'{retrieval,hits}') hit
   WHERE NOT EXISTS(SELECT 1 FROM business.p6_knowledge_chunks k
    JOIN business.p6_knowledge_documents d ON d.id=k.document_id
     AND d.organization_id=k.organization_id AND d.shop_id=k.shop_id
    JOIN business.p6_knowledge_authorizations a ON a.document_id=d.id
     AND a.organization_id=d.organization_id AND a.shop_id=d.shop_id
    WHERE k.organization_id=c.organization_id AND k.shop_id=c.shop_id
     AND k.evidence_id=hit->>'evidence_id' AND a.approved AND NOT a.revoked
     AND d.valid_from<=clock_timestamp() AND clock_timestamp()<d.expires_at
     AND r.manifest::jsonb->'evidence_ids' ? k.evidence_id
     AND hit=k.payload::jsonb||jsonb_build_object('evidence_id',k.evidence_id)))
 FROM business.p6_copy_candidates c JOIN business.p6_copy_products p ON p.id=c.product_id
  AND p.organization_id=c.organization_id AND p.shop_id=c.shop_id
 JOIN business.p6_knowledge_registries r ON r.id=c.registry_id
  AND r.organization_id=c.organization_id AND r.shop_id=c.shop_id WHERE c.id=cid),false)
$$;
CREATE FUNCTION business.p6_lock_copy(actor uuid,org uuid,identity uuid,auth bigint,cid uuid)
RETURNS boolean LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path=pg_catalog,business AS $$
DECLARE c record;
BEGIN
 SELECT * INTO c FROM business.p6_copy_candidates WHERE id=cid AND organization_id=org;
 IF NOT FOUND OR c.reviewer_id<>actor THEN RETURN false; END IF;
 IF NOT business.lock_p3_permission(actor,org,c.shop_id,identity,auth,'approver') THEN
  RETURN false;
 END IF;
 IF NOT business.lock_p3_permission(c.owner_id,org,c.shop_id,c.owner_identity,
   c.owner_auth_version,'operator') THEN RETURN false; END IF;
 PERFORM 1 FROM business.p6_copy_candidates WHERE id=cid FOR UPDATE;
 PERFORM 1 FROM business.p6_knowledge_registries WHERE id=c.registry_id FOR SHARE;
 PERFORM 1 FROM business.p6_copy_products WHERE id=c.product_id FOR SHARE;
 PERFORM a.document_id FROM business.p6_knowledge_authorizations a
 JOIN business.p6_knowledge_chunks k ON k.document_id=a.document_id
  AND k.organization_id=a.organization_id AND k.shop_id=a.shop_id
 WHERE a.organization_id=org AND a.shop_id=c.shop_id
  AND EXISTS(SELECT 1 FROM business.p6_knowledge_registries r WHERE r.id=c.registry_id
    AND r.manifest::jsonb->'evidence_ids' ? k.evidence_id)
 ORDER BY a.document_id FOR SHARE OF a;
 RETURN true;
END $$;
CREATE FUNCTION business.p6_copy_insert_guard() RETURNS trigger LANGUAGE plpgsql
SET search_path=pg_catalog,business AS $$
DECLARE c record; claim jsonb; hit jsonb; i int;
BEGIN
 IF TG_TABLE_NAME='p6_copy_candidates' THEN
  IF NOT business.p6_copy_session(NEW.owner_session,NEW.owner_id,NEW.organization_id,
       NEW.owner_identity,NEW.owner_auth_version) OR
   NOT business.lock_p3_permission(NEW.owner_id,NEW.organization_id,NEW.shop_id,
       NEW.owner_identity,NEW.owner_auth_version,'operator') OR
   NOT business.p6_copy_reviewer(NEW.reviewer_id,NEW.organization_id,NEW.shop_id) THEN
   RAISE EXCEPTION 'copy candidate permission' USING ERRCODE='23514';
  END IF;
  IF jsonb_typeof(NEW.payload::jsonb->'claims') IS DISTINCT FROM 'array' OR
   jsonb_typeof(NEW.payload::jsonb#>'{retrieval,hits}') IS DISTINCT FROM 'array' THEN
   RAISE EXCEPTION 'copy claims null or type' USING ERRCODE='23514';
  END IF;
  IF jsonb_array_length(NEW.payload::jsonb->'claims') NOT BETWEEN 2 AND 6 OR
   jsonb_array_length(NEW.payload::jsonb#>'{retrieval,hits}') NOT BETWEEN 1 AND 5 OR
   jsonb_array_length(NEW.payload::jsonb->'claims')<>
    1+jsonb_array_length(NEW.payload::jsonb#>'{retrieval,hits}') THEN
   RAISE EXCEPTION 'copy claims required' USING ERRCODE='23514';
  END IF;
  FOR i IN 0..jsonb_array_length(NEW.payload::jsonb->'claims')-1 LOOP
   claim:=NEW.payload::jsonb->'claims'->i;
   IF i=0 THEN
    IF claim->>'kind' IS DISTINCT FROM 'product_title' OR
     claim->'product' IS DISTINCT FROM NEW.payload::jsonb->'product' OR
     claim->>'text' IS DISTINCT FROM '商品名称：'||(NEW.payload::jsonb#>>'{product,text}') THEN
     RAISE EXCEPTION 'copy product claim' USING ERRCODE='23514';
    END IF;
   ELSE
    hit:=NEW.payload::jsonb#>'{retrieval,hits}'->(i-1);
    IF claim->>'kind' IS DISTINCT FROM 'sop_excerpt' OR claim->'sop' IS DISTINCT FROM hit OR
     claim->>'text' IS DISTINCT FROM 'SOP 操作说明：'||(hit#>>'{chunk,text}') THEN
     RAISE EXCEPTION 'copy sop claim' USING ERRCODE='23514';
    END IF;
   END IF;
  END LOOP;
  IF NEW.payload::jsonb->>'text' IS DISTINCT FROM (SELECT string_agg(v->>'text',E'\n' ORDER BY n)
    FROM jsonb_array_elements(NEW.payload::jsonb->'claims') WITH ORDINALITY t(v,n)) THEN
   RAISE EXCEPTION 'copy text binding' USING ERRCODE='23514';
  END IF;
 ELSIF TG_TABLE_NAME='p6_copy_decisions' THEN
  IF NOT business.p6_copy_session(NEW.session_id,NEW.actor_id,NEW.organization_id,
      NEW.identity_id,NEW.auth_version) OR
   NOT business.p6_lock_copy(NEW.actor_id,NEW.organization_id,NEW.identity_id,
      NEW.auth_version,NEW.candidate_id) OR
   NOT business.p6_copy_sources_current(NEW.candidate_id) THEN
   RAISE EXCEPTION 'copy decision permission or source' USING ERRCODE='23514';
  END IF;
 ELSE
  SELECT * INTO c FROM business.p6_copy_candidates WHERE id=NEW.candidate_id;
  IF NEW.text IS DISTINCT FROM c.payload::jsonb->>'text' THEN
   RAISE EXCEPTION 'copy draft text' USING ERRCODE='23514';
  END IF;
 END IF;
 RETURN NEW;
END $$;
CREATE FUNCTION business.p6_copy_commit_guard() RETURNS trigger LANGUAGE plpgsql
SET search_path=pg_catalog,business AS $$
DECLARE n int;
BEGIN
 IF TG_TABLE_NAME='p6_copy_candidates' THEN
  IF NOT business.p6_copy_sources_current(NEW.id) OR
   NOT business.p6_copy_session(NEW.owner_session,NEW.owner_id,NEW.organization_id,
    NEW.owner_identity,NEW.owner_auth_version) THEN
   RAISE EXCEPTION 'copy candidate stale' USING ERRCODE='23514';
  END IF;
 ELSE
  SELECT count(*) INTO n FROM business.p6_copy_drafts WHERE decision_id=NEW.id;
  IF (NEW.action='approve' AND n<>1) OR (NEW.action='reject' AND n<>0) OR
   NOT business.p6_copy_session(NEW.session_id,NEW.actor_id,NEW.organization_id,
    NEW.identity_id,NEW.auth_version) OR NOT business.p6_copy_sources_current(NEW.candidate_id) THEN
   RAISE EXCEPTION 'copy atomic decision or expiry' USING ERRCODE='23514';
  END IF;
 END IF;
 RETURN NULL;
END $$;
CREATE FUNCTION business.p6_copy_audit() RETURNS trigger LANGUAGE plpgsql
SET search_path=pg_catalog,business AS $$
BEGIN
 IF TG_TABLE_NAME='p6_copy_candidates' THEN
  INSERT INTO business.audit_events(id,organization_id,actor_id,source,action,entity_type,
   entity_id,after_state,reason,trace_id) VALUES(gen_random_uuid(),NEW.organization_id,
   NEW.owner_id,'copy_candidate','candidate_created','copy_candidate',NEW.id::text,
   jsonb_build_object('candidate_hash',NEW.candidate_hash,'registry_id',NEW.registry_id,
    'product_id',NEW.product_id),'scoped template candidate only',gen_random_uuid());
  RETURN NEW;
 END IF;
 INSERT INTO business.audit_events(id,organization_id,actor_id,source,action,entity_type,
  entity_id,after_state,reason,trace_id) VALUES(gen_random_uuid(),NEW.organization_id,
  NEW.actor_id,'copy_review','copy_'||NEW.action,'copy_decision',NEW.id::text,
  jsonb_build_object('candidate_id',NEW.candidate_id,'candidate_hash',NEW.candidate_hash),
  'explicit scoped internal draft review',gen_random_uuid());
 RETURN NEW;
END $$;
CREATE FUNCTION business.p6_copy_product_status() RETURNS trigger LANGUAGE plpgsql
SET search_path=pg_catalog,business AS $$
BEGIN
 IF TG_OP<>'UPDATE' OR (to_jsonb(NEW)-'enabled') IS DISTINCT FROM (to_jsonb(OLD)-'enabled') THEN
  RAISE EXCEPTION 'copy product immutable' USING ERRCODE='23514';
 END IF;
 INSERT INTO business.audit_events(id,organization_id,source,action,entity_type,entity_id,
  after_state,reason,trace_id) VALUES(gen_random_uuid(),NEW.organization_id,'knowledge_owner',
  'copy_product_status','copy_product',NEW.id::text,jsonb_build_object('enabled',NEW.enabled),
  'owner-only synthetic product status',gen_random_uuid());
 RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION business.p6_copy_reviewer(uuid,uuid,uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION business.p6_lock_copy_product(uuid,uuid,uuid,uuid,bigint,uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION business.p6_lock_copy(uuid,uuid,uuid,bigint,uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION business.p6_copy_sources_current(uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION business.p6_copy_session(uuid,uuid,uuid,uuid,bigint) FROM PUBLIC;
REVOKE ALL ON FUNCTION business.p6_copy_insert_guard() FROM PUBLIC;
REVOKE ALL ON FUNCTION business.p6_copy_commit_guard() FROM PUBLIC;
REVOKE ALL ON FUNCTION business.p6_copy_audit() FROM PUBLIC;
REVOKE ALL ON FUNCTION business.p6_copy_product_status() FROM PUBLIC;
"""


def upgrade() -> None:
    op.execute(DDL)
    for suffix in ("products", "candidates", "decisions", "drafts"):
        table = "business.p6_copy_" + suffix
        op.execute(f"REVOKE ALL ON {table} FROM PUBLIC")
        immutable = (
            "business.p6_copy_product_status"
            if suffix == "products"
            else "business.reject_inventory_mutation"
        )
        op.execute(
            f"CREATE TRIGGER copy_immutable BEFORE UPDATE OR DELETE ON {table} "
            f"FOR EACH ROW EXECUTE FUNCTION {immutable}()"
        )
        op.execute(
            f"CREATE TRIGGER copy_no_truncate BEFORE TRUNCATE ON {table} "
            "FOR EACH STATEMENT EXECUTE FUNCTION business.reject_inventory_mutation()"
        )
        if suffix != "products":
            op.execute(
                f"CREATE TRIGGER copy_bind BEFORE INSERT ON {table} "
                "FOR EACH ROW EXECUTE FUNCTION business.p6_copy_insert_guard()"
            )
        if suffix in ("candidates", "decisions"):
            op.execute(
                f"CREATE CONSTRAINT TRIGGER copy_commit AFTER INSERT ON {table} "
                "DEFERRABLE INITIALLY DEFERRED FOR EACH ROW "
                "EXECUTE FUNCTION business.p6_copy_commit_guard()"
            )
    op.execute(
        "CREATE TRIGGER copy_candidate_audit AFTER INSERT ON business.p6_copy_candidates "
        "FOR EACH ROW EXECUTE FUNCTION business.p6_copy_audit()"
    )
    op.execute(
        "CREATE TRIGGER copy_decision_audit AFTER INSERT ON business.p6_copy_decisions "
        "FOR EACH ROW EXECUTE FUNCTION business.p6_copy_audit()"
    )


def downgrade() -> None:
    raise RuntimeError("destructive downgrade disabled; restore from reviewed backup")
