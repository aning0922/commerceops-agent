"""Synthetic SOP storage only; K3 draft transactions are not implemented here."""

from alembic import op

revision = "0020_p6_knowledge_copy"
down_revision = "0019_p6_daily_reports"
branch_labels = None
depends_on = None

DDL = r"""
CREATE SCHEMA knowledge_ext;
REVOKE ALL ON SCHEMA knowledge_ext FROM PUBLIC;
CREATE EXTENSION vector WITH SCHEMA knowledge_ext VERSION '0.8.7';
REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA knowledge_ext FROM PUBLIC;
CREATE FUNCTION business.p6_vector_safe(v knowledge_ext.vector) RETURNS boolean
LANGUAGE sql IMMUTABLE STRICT SET search_path=pg_catalog,knowledge_ext AS $$
 SELECT knowledge_ext.vector_dims(v) BETWEEN 1 AND 2000
 AND NOT EXISTS(SELECT 1 FROM unnest(v::real[]) x
   WHERE x <> 0 AND (abs(x::float8)<1e-6 OR abs(x::float8)>1e6))
 AND (SELECT sum(x::float8*x::float8) FROM unnest(v::real[]) x) BETWEEN 1e-12 AND 1e12
$$;
CREATE TABLE business.p6_knowledge_documents (
 id uuid PRIMARY KEY, organization_id uuid NOT NULL, shop_id uuid NOT NULL,
 document_key text NOT NULL, version text NOT NULL, body text NOT NULL,
 content_sha256 text NOT NULL, payload text NOT NULL,
 valid_from timestamptz NOT NULL, expires_at timestamptz NOT NULL,
 UNIQUE(organization_id,shop_id,id), UNIQUE(organization_id,shop_id,document_key,version),
 FOREIGN KEY(organization_id,shop_id) REFERENCES business.shops(organization_id,id),
 CHECK(length(body) BETWEEN 1 AND 20000 AND position(chr(13) IN body)=0),
 CHECK(content_sha256=encode(sha256(convert_to(body,'UTF8')),'hex')),
 CHECK(expires_at>valid_from),
 CHECK(jsonb_typeof(payload::jsonb)='object' AND payload::jsonb ?& ARRAY['scope','source_kind',
  'document_id','document_version','body','content_sha256','valid_from','expires_at',
  'approved','revoked','license_digest']),
 CHECK(jsonb_strip_nulls(payload::jsonb)=payload::jsonb),
 CHECK((payload::jsonb->>'source_kind')='synthetic'),
 CHECK((payload::jsonb#>>'{scope,organization_id}')=organization_id::text),
 CHECK((payload::jsonb#>>'{scope,shop_id}')=shop_id::text),
 CHECK(payload::jsonb->>'document_id'=document_key AND payload::jsonb->>'document_version'=version),
 CHECK(payload::jsonb->>'body'=body AND payload::jsonb->>'content_sha256'=content_sha256),
 CHECK((payload::jsonb->>'valid_from')::timestamptz=valid_from
   AND (payload::jsonb->>'expires_at')::timestamptz=expires_at),
 CHECK(payload::jsonb->'approved'='true'::jsonb AND payload::jsonb->'revoked'='false'::jsonb)
);
CREATE TABLE business.p6_knowledge_authorizations (
 organization_id uuid NOT NULL, shop_id uuid NOT NULL, document_id uuid NOT NULL,
 approved boolean NOT NULL, revoked boolean NOT NULL,
 PRIMARY KEY(organization_id,shop_id,document_id),
 FOREIGN KEY(organization_id,shop_id,document_id)
 REFERENCES business.p6_knowledge_documents(organization_id,shop_id,id)
);
CREATE TABLE business.p6_knowledge_chunks (
 id uuid PRIMARY KEY, organization_id uuid NOT NULL, shop_id uuid NOT NULL,
 document_id uuid NOT NULL, chunk_key text NOT NULL, chunk_version text NOT NULL,
 evidence_id text NOT NULL, payload text NOT NULL,
 UNIQUE(organization_id,shop_id,id), UNIQUE(organization_id,shop_id,evidence_id),
 UNIQUE(organization_id,shop_id,document_id,chunk_key,chunk_version),
 FOREIGN KEY(organization_id,shop_id,document_id)
 REFERENCES business.p6_knowledge_documents(organization_id,shop_id,id),
 CHECK(evidence_id=encode(sha256(convert_to(payload,'UTF8')),'hex')),
 CHECK(jsonb_strip_nulls(payload::jsonb)=payload::jsonb),
 CHECK(payload::jsonb->>'source_kind'='sop')
);
CREATE TABLE business.p6_knowledge_embeddings (
 id uuid PRIMARY KEY, organization_id uuid NOT NULL, shop_id uuid NOT NULL,
 chunk_id uuid NOT NULL, profile_digest text NOT NULL CHECK(profile_digest ~ '^[0-9a-f]{64}$'),
 dimension integer NOT NULL CHECK(dimension BETWEEN 1 AND 2000),
 evidence_id text NOT NULL, origin text NOT NULL,
 embedding knowledge_ext.vector NOT NULL, stored_sha256 text NOT NULL,
 UNIQUE(organization_id,shop_id,id), UNIQUE(organization_id,shop_id,evidence_id,profile_digest),
 FOREIGN KEY(organization_id,shop_id,chunk_id)
 REFERENCES business.p6_knowledge_chunks(organization_id,shop_id,id),
 CONSTRAINT p6_embedding_numeric_safe
 CHECK(knowledge_ext.vector_dims(embedding)=dimension AND business.p6_vector_safe(embedding)),
 CHECK(stored_sha256=encode(sha256(convert_to('knowledge-vector-pg-f32-v1:'||profile_digest||':'||
   evidence_id||':','UTF8')||knowledge_ext.vector_send(embedding)),'hex'))
);
CREATE TABLE business.p6_knowledge_registries (
 id uuid PRIMARY KEY, organization_id uuid NOT NULL, shop_id uuid NOT NULL,
 manifest text NOT NULL, manifest_digest text NOT NULL, profile text NOT NULL,
 profile_digest text NOT NULL, enabled boolean NOT NULL DEFAULT true,
 UNIQUE(organization_id,shop_id,id), UNIQUE(organization_id,shop_id,manifest_digest),
 FOREIGN KEY(organization_id,shop_id) REFERENCES business.shops(organization_id,id),
 CHECK(manifest_digest=encode(sha256(convert_to(manifest,'UTF8')),'hex')),
 CHECK(profile_digest=encode(sha256(convert_to(profile,'UTF8')),'hex')),
 CHECK(manifest::jsonb#>>'{scope,organization_id}'=organization_id::text
   AND manifest::jsonb#>>'{scope,shop_id}'=shop_id::text),
 CHECK(jsonb_array_length(manifest::jsonb->'documents') BETWEEN 1 AND 100),
 CHECK(jsonb_array_length(manifest::jsonb->'evidence_ids') BETWEEN 1 AND 1000),
 CHECK(profile::jsonb->>'origin_profile_digest'=manifest::jsonb#>>'{profile,profile_digest}'),
 CHECK(profile::jsonb->>'dimension'=manifest::jsonb#>>'{profile,dimension}'),
 CHECK(profile::jsonb->>'encoding_version'='knowledge-vector-pg-f32-v1'
 AND profile::jsonb->>'distance_version'='cosine-pgvector-0.8.7-f32-v1'
 AND profile::jsonb->>'numeric_policy'='bounded-components-1e-6-1e6-normsq-1e-12-1e12-v1')
);
CREATE FUNCTION business.p6_knowledge_bind() RETURNS trigger LANGUAGE plpgsql
SET search_path=pg_catalog,business,knowledge_ext AS $$
DECLARE doc text; c record; item jsonb;
BEGIN
 IF TG_TABLE_NAME='p6_knowledge_chunks' THEN
  SELECT payload INTO doc FROM business.p6_knowledge_documents WHERE id=NEW.document_id
   AND organization_id=NEW.organization_id AND shop_id=NEW.shop_id;
  item:=NEW.payload::jsonb->'chunk';
  IF item IS NULL OR NOT(item ?& ARRAY['document','chunk_id','chunk_version','start','end',
    'text','text_sha256']) OR (item->>'start') IS NULL OR (item->>'end') IS NULL
   OR item->'document' IS DISTINCT FROM doc::jsonb
   OR item->>'chunk_id' IS DISTINCT FROM NEW.chunk_key
   OR item->>'chunk_version' IS DISTINCT FROM NEW.chunk_version
   OR (item->>'start')::int<0 OR (item->>'end')::int<=(item->>'start')::int
   OR (item->>'end')::int>length(doc::jsonb->>'body')
   OR item->>'text' IS DISTINCT FROM substring(doc::jsonb->>'body' FROM (item->>'start')::int+1
      FOR (item->>'end')::int-(item->>'start')::int)
   OR item->>'text_sha256' IS DISTINCT FROM
       encode(sha256(convert_to(item->>'text','UTF8')),'hex') THEN
    RAISE EXCEPTION 'knowledge chunk binding' USING ERRCODE='23514';
  END IF;
 ELSIF TG_TABLE_NAME='p6_knowledge_embeddings' THEN
  SELECT * INTO c FROM business.p6_knowledge_chunks WHERE id=NEW.chunk_id
   AND organization_id=NEW.organization_id AND shop_id=NEW.shop_id;
  IF NEW.evidence_id IS DISTINCT FROM c.evidence_id OR
   NEW.origin::jsonb->'citation' IS DISTINCT FROM
      (c.payload::jsonb||jsonb_build_object('evidence_id',c.evidence_id)) OR
   knowledge_ext.vector_send((NEW.origin::jsonb->'vector')::text::knowledge_ext.vector)
    IS DISTINCT FROM knowledge_ext.vector_send(NEW.embedding) THEN
   RAISE EXCEPTION 'knowledge embedding binding' USING ERRCODE='23514';
  END IF;
 ELSE
  IF EXISTS(SELECT 1 FROM business.p6_knowledge_embeddings e
   JOIN business.p6_knowledge_chunks k ON k.id=e.chunk_id
    AND k.organization_id=e.organization_id AND k.shop_id=e.shop_id
   JOIN jsonb_array_elements_text(NEW.manifest::jsonb->'evidence_ids') refs(evidence_id)
    ON refs.evidence_id=e.evidence_id
   WHERE e.organization_id=NEW.organization_id AND e.shop_id=NEW.shop_id
    AND e.profile_digest=NEW.profile_digest
   GROUP BY k.document_id,k.chunk_key HAVING count(*)>1) THEN
   RAISE EXCEPTION 'knowledge ambiguous logical chunk' USING ERRCODE='23514';
  END IF;
  FOR item IN SELECT value FROM jsonb_array_elements(NEW.manifest::jsonb->'evidence_ids') LOOP
   IF NOT EXISTS(SELECT 1 FROM business.p6_knowledge_embeddings e
    JOIN business.p6_knowledge_chunks k ON k.id=e.chunk_id
     AND k.organization_id=e.organization_id AND k.shop_id=e.shop_id
    JOIN business.p6_knowledge_documents d ON d.id=k.document_id
     AND d.organization_id=k.organization_id AND d.shop_id=k.shop_id
    JOIN business.p6_knowledge_authorizations a ON a.document_id=d.id
     AND a.organization_id=d.organization_id AND a.shop_id=d.shop_id
    WHERE e.organization_id=NEW.organization_id AND e.shop_id=NEW.shop_id
     AND e.profile_digest=NEW.profile_digest AND e.evidence_id=item#>>'{}'
     AND e.origin::jsonb#>>'{profile,profile_digest}'=
       NEW.profile::jsonb->>'origin_profile_digest'
     AND e.dimension=(NEW.profile::jsonb->>'dimension')::int
     AND NEW.manifest::jsonb->'documents' @> jsonb_build_array(jsonb_build_object(
       'document_id',d.document_key,'document_version',d.version,'content_sha256',d.content_sha256,
       'license_digest',d.payload::jsonb->>'license_digest'))) THEN
    RAISE EXCEPTION 'knowledge registry binding' USING ERRCODE='23514';
   END IF;
  END LOOP;
 END IF;
 RETURN NEW;
END $$;
CREATE FUNCTION business.p6_knowledge_status_guard() RETURNS trigger LANGUAGE plpgsql
SET search_path=pg_catalog,business AS $$
BEGIN
 IF TG_OP<>'UPDATE' OR
  (TG_TABLE_NAME='p6_knowledge_registries' AND
    (to_jsonb(NEW)-'enabled') IS DISTINCT FROM (to_jsonb(OLD)-'enabled')) OR
  (TG_TABLE_NAME='p6_knowledge_authorizations' AND
    (to_jsonb(NEW)-ARRAY['approved','revoked']) IS DISTINCT FROM
    (to_jsonb(OLD)-ARRAY['approved','revoked'])) THEN
   RAISE EXCEPTION 'knowledge immutable' USING ERRCODE='23514';
 END IF;
 INSERT INTO business.audit_events(id,organization_id,source,action,entity_type,entity_id,
  before_state,after_state,reason,trace_id) VALUES(gen_random_uuid(),NEW.organization_id,
  'knowledge_owner','authorization_changed',TG_TABLE_NAME,
  coalesce(to_jsonb(NEW)->>'id',to_jsonb(NEW)->>'document_id'),
  to_jsonb(OLD)-ARRAY['manifest','profile'],to_jsonb(NEW)-ARRAY['manifest','profile'],
  'owner-only synthetic knowledge status',gen_random_uuid());
 RETURN NEW;
END $$;
CREATE FUNCTION business.p6_lock_knowledge(actor uuid,org uuid,shop uuid,identity uuid,
 auth bigint,registry uuid) RETURNS boolean LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path=pg_catalog,business AS $$
DECLARE r record;
BEGIN
 IF NOT business.lock_p3_permission(actor,org,shop,identity,auth,'operator') THEN
  RETURN false;
 END IF;
 SELECT * INTO r FROM business.p6_knowledge_registries
  WHERE id=registry AND organization_id=org AND shop_id=shop AND enabled FOR SHARE;
 IF NOT FOUND THEN RETURN false; END IF;
 PERFORM a.document_id FROM business.p6_knowledge_authorizations a
 JOIN business.p6_knowledge_chunks c ON c.document_id=a.document_id
  AND c.organization_id=a.organization_id AND c.shop_id=a.shop_id
 WHERE a.organization_id=org AND a.shop_id=shop
  AND r.manifest::jsonb->'evidence_ids' ? c.evidence_id
 ORDER BY a.document_id FOR SHARE OF a;
 RETURN true;
END $$;
REVOKE ALL ON FUNCTION business.p6_lock_knowledge(uuid,uuid,uuid,uuid,bigint,uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION business.p6_vector_safe(knowledge_ext.vector) FROM PUBLIC;
REVOKE ALL ON FUNCTION business.p6_knowledge_bind() FROM PUBLIC;
REVOKE ALL ON FUNCTION business.p6_knowledge_status_guard() FROM PUBLIC;
"""


def upgrade() -> None:
    # Deliberately fail if a different extension/schema already exists; no IF NOT EXISTS/upgrade.
    op.execute(DDL)
    for kind in ("documents", "chunks", "embeddings", "registries", "authorizations"):
        table = "business.p6_knowledge_" + kind
        op.execute(f"REVOKE ALL ON {table} FROM PUBLIC")
        if kind in ("chunks", "embeddings", "registries"):
            op.execute(
                f"CREATE TRIGGER knowledge_bind BEFORE INSERT ON {table} "
                "FOR EACH ROW EXECUTE FUNCTION business.p6_knowledge_bind()"
            )
        mutation = (
            "business.p6_knowledge_status_guard"
            if kind in ("registries", "authorizations")
            else "business.reject_inventory_mutation"
        )
        op.execute(
            f"CREATE TRIGGER knowledge_immutable BEFORE UPDATE OR DELETE ON {table} "
            f"FOR EACH ROW EXECUTE FUNCTION {mutation}()"
        )
        op.execute(
            f"CREATE TRIGGER knowledge_no_truncate BEFORE TRUNCATE ON {table} "
            "FOR EACH STATEMENT EXECUTE FUNCTION business.reject_inventory_mutation()"
        )


def downgrade() -> None:
    raise RuntimeError("destructive downgrade disabled; restore from reviewed backup")
