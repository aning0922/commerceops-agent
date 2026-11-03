"""K2 owner-only synthetic registration and scoped read transactions. No API/Worker wiring."""

import json
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from psycopg import Connection, sql
from psycopg.pq import TransactionStatus

from commerceops.application.knowledge_copy.citations import Embedding
from commerceops.application.knowledge_copy.contracts import Manifest, Query, checked, digest
from commerceops.application.knowledge_copy.ranking import cosine_distance
from commerceops.application.replenishment.contracts import Actor, WebFailure
from commerceops.infrastructure.knowledge_copy_values import (
    PgEvidence,
    PgProfile,
    PgRetrieval,
    canonical,
    f32_vector,
    pg_digest,
    pg_profile,
    query_parameter,
    validate_logical_corpus,
    vector_bytes,
    vector_parameter,
)
from commerceops.infrastructure.web_sessions import actor_guard

DB = Connection[dict[str, Any]]
TABLES = ("documents", "authorizations", "chunks", "embeddings", "registries")


def _transaction(db: DB) -> None:
    if db.autocommit and db.info.transaction_status != TransactionStatus.INTRANS:
        raise ValueError("KNOWLEDGE_TRANSACTION_REQUIRED")
    db.execute("SET LOCAL statement_timeout='5s'")
    db.execute("SET LOCAL lock_timeout='5s'")


def _owner(db: DB) -> None:
    _transaction(db)
    row = db.execute(
        "SELECT current_user=pg_get_userbyid(relowner) AS allowed "
        "FROM pg_class WHERE oid='business.p6_knowledge_documents'::regclass"
    ).fetchone()
    if not row or not row["allowed"]:
        raise ValueError("KNOWLEDGE_OWNER_REQUIRED")


def grant_knowledge_runtime(db: DB) -> None:
    """Explicit owner bootstrap after grant_runtime; no role creation or key access."""
    _owner(db)
    db.execute("GRANT USAGE ON SCHEMA knowledge_ext TO commerceops_app")
    db.execute("REVOKE CREATE ON SCHEMA knowledge_ext FROM commerceops_app")
    for table in TABLES:
        target = sql.Identifier("business", "p6_knowledge_" + table)
        db.execute(sql.SQL("REVOKE ALL ON {} FROM commerceops_app").format(target))
        db.execute(sql.SQL("GRANT SELECT ON {} TO commerceops_app").format(target))
    db.execute(
        "GRANT EXECUTE ON FUNCTION business.p6_lock_knowledge"
        "(uuid,uuid,uuid,uuid,bigint,uuid) TO commerceops_app"
    )
    db.execute(
        "GRANT EXECUTE ON FUNCTION business.p6_vector_safe(knowledge_ext.vector) TO commerceops_app"
    )
    for signature in (
        "vector_in(cstring,oid,integer)",
        "vector_out(knowledge_ext.vector)",
        "vector_send(knowledge_ext.vector)",
        "vector_dims(knowledge_ext.vector)",
        "vector(knowledge_ext.vector,integer,boolean)",
        "vector_to_float4(knowledge_ext.vector,integer,boolean)",
        "cosine_distance(knowledge_ext.vector,knowledge_ext.vector)",
    ):
        # Static signatures only, no user-supplied SQL identifier or type.
        db.execute(f"GRANT EXECUTE ON FUNCTION knowledge_ext.{signature} TO commerceops_app")


def _register_synthetic_corpus(
    db: DB,
    registry_id: UUID,
    manifest: Manifest,
    corpus: tuple[Embedding, ...],
) -> None:
    """Append immutable owner-provided fixture evidence; no unlicensed/actual sources supported.

    Caller owns commit/rollback. Repeated registration must match the immutable old rows exactly;
    it does not re-enable a revoked authorization or registry.
    """
    _owner(db)
    manifest = checked(manifest)
    corpus = tuple(checked(item) for item in corpus)
    validate_logical_corpus(corpus)
    if (
        tuple(sorted(item.citation.evidence_id for item in corpus)) != manifest.evidence_ids
        or len(corpus) > 1000
    ):
        raise ValueError("KNOWLEDGE_CORPUS_INCOMPLETE")
    profile = pg_profile(manifest.profile.profile_digest, manifest.profile.dimension)
    org, shop = UUID(manifest.scope.organization_id), UUID(manifest.scope.shop_id)
    for item in corpus:
        c, doc = item.citation.chunk, item.citation.chunk.document
        if (
            doc.scope != manifest.scope
            or item.profile != manifest.profile
            or not doc.approved
            or doc.revoked
        ):
            raise ValueError("KNOWLEDGE_CORPUS_INVALID")
        from commerceops.application.knowledge_copy.contracts import DocumentBinding

        if DocumentBinding.of(doc) not in manifest.documents:
            raise ValueError("KNOWLEDGE_CORPUS_INVALID")
        docid = uuid5(
            NAMESPACE_URL, f"p6-document:{org}:{shop}:{doc.document_id}:{doc.document_version}"
        )
        payload = canonical(doc.model_dump(mode="json"))
        db.execute(
            """INSERT INTO business.p6_knowledge_documents
         (id,organization_id,shop_id,document_key,version,body,content_sha256,payload,valid_from,expires_at)
         VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING""",
            (
                docid,
                org,
                shop,
                doc.document_id,
                doc.document_version,
                doc.body,
                doc.content_sha256,
                payload,
                doc.valid_from,
                doc.expires_at,
            ),
        )
        stored = db.execute(
            "SELECT payload FROM business.p6_knowledge_documents WHERE id=%s", (docid,)
        ).fetchone()
        if not stored or stored["payload"] != payload:
            raise ValueError("KNOWLEDGE_DOCUMENT_CONFLICT")
        db.execute(
            """INSERT INTO business.p6_knowledge_authorizations
         VALUES(%s,%s,%s,true,false) ON CONFLICT DO NOTHING""",
            (org, shop, docid),
        )
        chunkid = uuid5(NAMESPACE_URL, f"p6-chunk:{org}:{shop}:{item.citation.evidence_id}")
        chunk_payload = canonical(item.citation.payload("evidence_id"))
        db.execute(
            """INSERT INTO business.p6_knowledge_chunks
         (id,organization_id,shop_id,document_id,chunk_key,chunk_version,evidence_id,payload)
         VALUES(%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING""",
            (
                chunkid,
                org,
                shop,
                docid,
                c.chunk_id,
                c.chunk_version,
                item.citation.evidence_id,
                chunk_payload,
            ),
        )
        embedding_id = uuid5(
            NAMESPACE_URL,
            f"p6-vector:{org}:{shop}:{item.citation.evidence_id}:{profile.profile_digest}",
        )
        raw = vector_bytes(item.vector)
        stored_hash = pg_digest(profile.profile_digest, item.citation.evidence_id, raw)
        origin = canonical(item.model_dump(mode="json"))
        db.execute(
            """INSERT INTO business.p6_knowledge_embeddings
         (id,organization_id,shop_id,chunk_id,profile_digest,dimension,evidence_id,origin,
          embedding,stored_sha256) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s::knowledge_ext.vector,%s)
         ON CONFLICT DO NOTHING""",
            (
                embedding_id,
                org,
                shop,
                chunkid,
                profile.profile_digest,
                profile.dimension,
                item.citation.evidence_id,
                origin,
                vector_parameter(item.vector),
                stored_hash,
            ),
        )
        stored = db.execute(
            """SELECT origin,stored_sha256,
         knowledge_ext.vector_send(embedding) AS actual FROM business.p6_knowledge_embeddings
         WHERE id=%s""",
            (embedding_id,),
        ).fetchone()
        if (
            not stored
            or stored["origin"] != origin
            or stored["stored_sha256"] != stored_hash
            or bytes(stored["actual"]) != raw
        ):
            raise ValueError("KNOWLEDGE_VECTOR_CONFLICT")
    manifest_payload = canonical(manifest.payload("manifest_digest"))
    profile_payload = canonical(profile.payload("profile_digest"))
    inserted = db.execute(
        """INSERT INTO business.p6_knowledge_registries
     (id,organization_id,shop_id,manifest,manifest_digest,profile,profile_digest)
     VALUES(%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING RETURNING id""",
        (
            registry_id,
            org,
            shop,
            manifest_payload,
            manifest.manifest_digest,
            profile_payload,
            profile.profile_digest,
        ),
    ).fetchone()
    stored = db.execute(
        "SELECT manifest,profile FROM business.p6_knowledge_registries WHERE id=%s", (registry_id,)
    ).fetchone()
    if not stored or stored["manifest"] != manifest_payload or stored["profile"] != profile_payload:
        raise ValueError("KNOWLEDGE_REGISTRY_CONFLICT")
    if inserted:
        db.execute(
            """INSERT INTO business.audit_events
         (id,organization_id,source,action,entity_type,entity_id,after_state,reason,trace_id)
         VALUES(gen_random_uuid(),%s,'knowledge_owner','synthetic_corpus_registered',
          'knowledge_registry',%s,jsonb_build_object('registry_digest',%s::text),
          'self-authored synthetic fixtures only',gen_random_uuid())""",
            (org, str(registry_id), manifest.manifest_digest),
        )


def register_synthetic_corpus(
    db: DB,
    registry_id: UUID,
    manifest: Manifest,
    corpus: tuple[Embedding, ...],
) -> None:
    _owner(db)  # Start the caller-owned transaction before the nested savepoint.
    with db.transaction():
        _register_synthetic_corpus(db, registry_id, manifest, corpus)


REGISTRY_DUPLICATES_SQL = """SELECT EXISTS(
 SELECT 1 FROM business.p6_knowledge_embeddings e
 JOIN business.p6_knowledge_chunks c ON c.id=e.chunk_id
  AND c.organization_id=e.organization_id AND c.shop_id=e.shop_id
 JOIN business.p6_knowledge_registries r ON r.id=%s
  AND r.organization_id=e.organization_id AND r.shop_id=e.shop_id
 JOIN jsonb_array_elements_text(r.manifest::jsonb->'evidence_ids') refs(evidence_id)
  ON refs.evidence_id=e.evidence_id
 WHERE r.organization_id=%s AND r.shop_id=%s AND e.profile_digest=r.profile_digest
 GROUP BY c.document_id,c.chunk_key HAVING count(*)>1) AS ambiguous"""


RETRIEVE_SQL = """
WITH eligible AS MATERIALIZED (
 SELECT e.*, d.document_key,d.version,c.chunk_key FROM business.p6_knowledge_embeddings e
 JOIN business.p6_knowledge_chunks c ON c.id=e.chunk_id
  AND c.organization_id=e.organization_id AND c.shop_id=e.shop_id
 JOIN business.p6_knowledge_documents d ON d.id=c.document_id
  AND d.organization_id=c.organization_id AND d.shop_id=c.shop_id
 JOIN business.p6_knowledge_authorizations a ON a.document_id=d.id
  AND a.organization_id=d.organization_id AND a.shop_id=d.shop_id
 JOIN business.p6_knowledge_registries r ON r.id=%(registry)s
  AND r.organization_id=e.organization_id AND r.shop_id=e.shop_id
 WHERE e.organization_id=%(org)s AND e.shop_id=%(shop)s AND r.enabled
  AND r.manifest_digest=%(manifest_digest)s AND e.profile_digest=r.profile_digest
  AND r.profile_digest=%(profile_digest)s
  AND r.manifest::jsonb->'evidence_ids' ? e.evidence_id
  AND r.manifest::jsonb->'documents' @> jsonb_build_array(jsonb_build_object(
   'document_id',d.document_key,'document_version',d.version,'content_sha256',d.content_sha256,
   'license_digest',d.payload::jsonb->>'license_digest'))
  AND a.approved AND NOT a.revoked
  AND d.valid_from<=statement_timestamp() AND statement_timestamp()<d.expires_at
), counts AS (SELECT count(*) AS n FROM eligible), scored AS MATERIALIZED (
 SELECT eligible.*,embedding OPERATOR(knowledge_ext.<=>)
  %(vector)s::knowledge_ext.vector AS distance,
  encode(knowledge_ext.vector_send(embedding),'hex') AS stored_hex
 FROM eligible WHERE (SELECT n FROM counts)<=20
), ranked AS (
 SELECT evidence_id FROM scored WHERE distance<=%(threshold)s
 ORDER BY distance,document_key COLLATE "C",version COLLATE "C",chunk_key COLLATE "C" LIMIT 5
)
SELECT (SELECT n FROM counts) AS n,statement_timestamp() AS as_of,
 coalesce(jsonb_agg(jsonb_build_object('origin',origin::jsonb,'distance',distance,
  'stored_hex',stored_hex,'stored_sha256',stored_sha256,
  'selected',evidence_id IN(SELECT evidence_id FROM ranked))
 ORDER BY distance,document_key COLLATE "C",version COLLATE "C",
  chunk_key COLLATE "C"),'[]'::jsonb) AS pool
FROM scored
"""


def retrieve_in_transaction(
    db: DB,
    actor: Actor,
    shop_id: UUID,
    registry_id: UUID,
    expected_registry_digest: str,
    query: Query,
) -> PgRetrieval:
    _transaction(db)
    actor_guard(db, actor)
    locked = db.execute(
        "SELECT business.p6_lock_knowledge(%s,%s,%s,%s,%s,%s) AS allowed",
        (
            actor.principal_id,
            actor.organization_id,
            shop_id,
            actor.identity_id,
            actor.auth_version,
            registry_id,
        ),
    ).fetchone()
    if not locked or not locked["allowed"]:
        raise WebFailure("KNOWLEDGE_NOT_AVAILABLE", 403)
    row = db.execute(
        """SELECT manifest,manifest_digest,profile,profile_digest
     FROM business.p6_knowledge_registries WHERE id=%s AND organization_id=%s AND shop_id=%s""",
        (registry_id, actor.organization_id, shop_id),
    ).fetchone()
    if row is None or row["manifest_digest"] != expected_registry_digest:
        raise ValueError("KNOWLEDGE_REGISTRY_CHANGED")
    manifest = Manifest.model_validate_json(
        canonical(json.loads(row["manifest"]) | {"manifest_digest": row["manifest_digest"]})
    )
    profile = PgProfile.model_validate_json(
        canonical(json.loads(row["profile"]) | {"profile_digest": row["profile_digest"]})
    )
    query = checked(query)
    parameter = query_parameter(query, profile)
    # Check the full bound registry before authorization filtering, capacity, distance or top-k.
    duplicate = db.execute(
        REGISTRY_DUPLICATES_SQL, (registry_id, actor.organization_id, shop_id)
    ).fetchone()
    if duplicate is None or duplicate["ambiguous"]:
        raise ValueError("KNOWLEDGE_REGISTRY_AMBIGUOUS")
    ext = db.execute("""SELECT extversion,n.nspname FROM pg_extension e
     JOIN pg_namespace n ON n.oid=e.extnamespace WHERE extname='vector'""").fetchone()
    if ext != {"extversion": "0.8.7", "nspname": "knowledge_ext"}:
        raise ValueError("KNOWLEDGE_EXTENSION_INVALID")
    result = db.execute(
        RETRIEVE_SQL,
        dict(
            registry=registry_id,
            org=actor.organization_id,
            shop=shop_id,
            manifest_digest=manifest.manifest_digest,
            profile_digest=profile.profile_digest,
            vector=parameter,
            threshold=manifest.max_distance,
        ),
    ).fetchone()
    if not result or result["n"] > 20:
        raise ValueError("KNOWLEDGE_CAPACITY")
    pool = []
    selected = []
    for record in result["pool"]:
        item = Embedding.model_validate_json(canonical(record["origin"]))
        c = item.citation
        if (
            not manifest.permits(c.chunk.document, result["as_of"])
            or c.evidence_id not in manifest.evidence_ids
        ):
            raise ValueError("KNOWLEDGE_EVIDENCE_INVALID")
        evidence = PgEvidence(
            origin=item,
            profile=profile,
            query=query,
            stored_hex=record["stored_hex"],
            stored_sha256=record["stored_sha256"],
            distance=record["distance"],
            reference_distance=cosine_distance(f32_vector(item.vector), f32_vector(query.vector)),
        )
        pool.append(evidence)
        if record["selected"]:
            selected.append(c)
    body = dict(
        registry_id=registry_id,
        registry_version=manifest.manifest_version,
        scope=manifest.scope,
        registry_digest=manifest.manifest_digest,
        profile=profile,
        query=query,
        as_of=result["as_of"],
        eligible_count=result["n"],
        pool=tuple(pool),
        hits=tuple(selected),
        max_distance=manifest.max_distance,
        reason="OK" if selected else "INSUFFICIENT_EVIDENCE",
        complete=True,
        exhaustive=True,
        evidence_mode="synthetic_vector",
    )
    raw = PgRetrieval.model_construct(**body)
    return PgRetrieval.model_validate(body | {"result_hash": digest(raw.payload("result_hash"))})
