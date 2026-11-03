"""K3 PG candidate/review store. Explicit caller transactions; no external effects or retries."""

import json
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any
from uuid import UUID, uuid4

from commerceops.application.knowledge_copy.citations import ProductCitation
from commerceops.application.knowledge_copy.commands import CopyReceipt, CreateCopy, ReviewCopy
from commerceops.application.knowledge_copy.contracts import Manifest, Query, checked, digest
from commerceops.application.replenishment.contracts import WebActor, WebFailure
from commerceops.infrastructure.database import DatabaseSettings, connect
from commerceops.infrastructure.knowledge_copy_drafts import CopyCandidate, make_copy
from commerceops.infrastructure.knowledge_copy_repository import (
    DB,
    REGISTRY_DUPLICATES_SQL,
    RETRIEVE_SQL,
    _owner,
    _transaction,
    retrieve_in_transaction,
)
from commerceops.infrastructure.knowledge_copy_values import PgProfile, canonical, query_parameter
from commerceops.infrastructure.web_sessions import actor_guard, now, role_scope


def register_copy_product(db: DB, identifier: UUID, value: ProductCitation) -> None:
    _owner(db)
    value = checked(value)
    snapshot = value.snapshot
    if snapshot.revoked:
        raise ValueError("COPY_PRODUCT_INVALID")
    payload = canonical(value.payload("evidence_id"))
    row = db.execute(
        """INSERT INTO business.p6_copy_products
     (id,organization_id,shop_id,payload,evidence_id,captured_at,expires_at)
     VALUES(%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING RETURNING id""",
        (
            identifier,
            UUID(snapshot.scope.organization_id),
            UUID(snapshot.scope.shop_id),
            payload,
            value.evidence_id,
            snapshot.captured_at,
            snapshot.expires_at,
        ),
    ).fetchone()
    stored = db.execute(
        "SELECT payload,evidence_id FROM business.p6_copy_products WHERE id=%s", (identifier,)
    ).fetchone()
    if not stored or stored != {"payload": payload, "evidence_id": value.evidence_id}:
        raise ValueError("COPY_PRODUCT_CONFLICT")
    if row:
        db.execute(
            """INSERT INTO business.audit_events
         (id,organization_id,source,action,entity_type,entity_id,after_state,reason,trace_id)
         VALUES(gen_random_uuid(),%s,'knowledge_owner','synthetic_product_registered',
          'copy_product',%s,jsonb_build_object('evidence_id',%s::text),
          'self-authored synthetic product facts',gen_random_uuid())""",
            (UUID(snapshot.scope.organization_id), str(identifier), value.evidence_id),
        )


def grant_copy_runtime(db: DB) -> None:
    _owner(db)
    for suffix in ("products", "candidates", "decisions", "drafts"):
        # Only literals in this tuple, never request SQL or user identifiers.
        db.execute(f"REVOKE ALL ON business.p6_copy_{suffix} FROM commerceops_app")
        db.execute(f"GRANT SELECT ON business.p6_copy_{suffix} TO commerceops_app")
        if suffix != "products":
            db.execute(f"GRANT INSERT ON business.p6_copy_{suffix} TO commerceops_app")
    for signature in (
        "p6_copy_session(uuid,uuid,uuid,uuid,bigint)",
        "p6_copy_sources_current(uuid)",
        "p6_lock_copy(uuid,uuid,uuid,bigint,uuid)",
        "p6_copy_reviewer(uuid,uuid,uuid)",
        "p6_lock_copy_product(uuid,uuid,uuid,uuid,bigint,uuid)",
    ):
        db.execute(f"GRANT EXECUTE ON FUNCTION business.{signature} TO commerceops_app")


def _candidate(row: dict[str, Any]) -> CopyCandidate:
    return CopyCandidate.model_validate_json(
        canonical(json.loads(row["payload"]) | {"candidate_hash": row["candidate_hash"]})
    )


def _receipt(row: dict[str, Any]) -> CopyReceipt:
    return CopyReceipt(
        request_key=row["request_key"],
        candidate_id=row["candidate_id"],
        candidate_hash=row["candidate_hash"],
        decision_id=row["id"],
        draft_id=row["draft_id"],
        state="saved" if row["action"] == "approve" else "rejected",
    )


RECEIPT = """SELECT d.*,s.id AS draft_id FROM business.p6_copy_decisions d
 LEFT JOIN business.p6_copy_drafts s ON s.decision_id=d.id
 WHERE d.organization_id=%s AND d.actor_id=%s AND d.request_key=%s"""


@dataclass(frozen=True)
class CopyStore:
    settings: DatabaseSettings
    # Server-owned, explicitly synthetic vectors. The HTTP body cannot provide these.
    queries: Mapping[tuple[UUID, UUID, str], Query]

    def __post_init__(self) -> None:
        bounded = {}
        if len(self.queries) > 1000:
            raise ValueError("COPY_QUERY_CONFIGURATION")
        for key, value in self.queries.items():
            if (
                type(key) is not tuple
                or len(key) != 3
                or not isinstance(key[0], UUID)
                or not isinstance(key[1], UUID)
                or type(key[2]) is not str
            ):
                raise ValueError("COPY_QUERY_CONFIGURATION")
            bounded[key] = checked(value)
        object.__setattr__(self, "queries", MappingProxyType(bounded))

    def _create_in_transaction(self, db: DB, actor: WebActor, request: CreateCopy) -> CopyCandidate:
        _transaction(db)
        request = checked(request)
        if not role_scope(db, actor, request.shop_id, "operator"):
            raise WebFailure("ACCESS_DENIED", 403)
        payload = canonical(request.payload("request_key"))
        existing = db.execute(
            """SELECT * FROM business.p6_copy_candidates WHERE organization_id=%s
         AND owner_id=%s AND request_key=%s""",
            (actor.organization_id, actor.principal_id, request.request_key),
        ).fetchone()
        if existing:
            if existing["request_hash"] != digest(request.payload("request_key")):
                raise WebFailure("IDEMPOTENCY_CONFLICT", 409)
            value = _candidate(existing)
            self.verify_sources(db, existing, value, replay_rank=False)
            return value
        query = self.queries.get((actor.organization_id, request.shop_id, request.query_ref))
        if query is None:
            raise WebFailure("COPY_QUERY_UNAVAILABLE", 409)
        eligible = db.execute(
            "SELECT business.p6_copy_reviewer(%s,%s,%s) AS allowed",
            (request.reviewer_id, actor.organization_id, request.shop_id),
        ).fetchone()
        if not eligible or not eligible["allowed"]:
            raise WebFailure("COPY_REVIEWER_UNAVAILABLE", 409)
        retrieval = retrieve_in_transaction(
            db, actor, request.shop_id, request.registry_id, request.registry_digest, query
        )
        locked = db.execute(
            "SELECT business.p6_lock_copy_product(%s,%s,%s,%s,%s,%s) AS allowed",
            (
                actor.principal_id,
                actor.organization_id,
                request.shop_id,
                actor.identity_id,
                actor.auth_version,
                request.product_source_id,
            ),
        ).fetchone()
        if not locked or not locked["allowed"]:
            raise WebFailure("COPY_PRODUCT_UNAVAILABLE", 409)
        product = db.execute(
            """SELECT payload,evidence_id FROM business.p6_copy_products
         WHERE id=%s AND organization_id=%s AND shop_id=%s""",
            (request.product_source_id, actor.organization_id, request.shop_id),
        ).fetchone()
        if product is None:
            raise WebFailure("COPY_PRODUCT_UNAVAILABLE", 409)
        citation = ProductCitation.model_validate_json(
            canonical(json.loads(product["payload"]) | {"evidence_id": product["evidence_id"]})
        )
        candidate = make_copy(
            uuid4(),
            actor.principal_id,
            request.reviewer_id,
            request.product_source_id,
            retrieval,
            citation,
            now=now(db),
        )
        db.execute(
            """INSERT INTO business.p6_copy_candidates
         (id,organization_id,shop_id,owner_id,reviewer_id,owner_identity,owner_session,owner_auth_version,
          registry_id,product_id,request_key,request_payload,request_hash,payload,candidate_hash,
          created_at,expires_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
         ON CONFLICT(organization_id,owner_id,request_key) DO NOTHING""",
            (
                candidate.candidate_id,
                actor.organization_id,
                request.shop_id,
                actor.principal_id,
                request.reviewer_id,
                actor.identity_id,
                actor.session_id,
                actor.auth_version,
                request.registry_id,
                request.product_source_id,
                request.request_key,
                payload,
                digest(request.payload("request_key")),
                canonical(candidate.payload("candidate_hash")),
                candidate.candidate_hash,
                candidate.as_of,
                candidate.expires_at,
            ),
        )
        stored = db.execute(
            """SELECT * FROM business.p6_copy_candidates WHERE organization_id=%s
         AND owner_id=%s AND request_key=%s""",
            (actor.organization_id, actor.principal_id, request.request_key),
        ).fetchone()
        if stored is None or stored["request_hash"] != digest(request.payload("request_key")):
            raise WebFailure("IDEMPOTENCY_CONFLICT", 409)
        value = _candidate(stored)
        self.verify_sources(db, stored, value, replay_rank=True)
        return value

    def verify_sources(
        self, db: DB, row: dict[str, Any], value: CopyCandidate, *, replay_rank: bool
    ) -> None:
        """Bind stored JSON to authoritative owner inputs, including the server-owned query."""
        request = CreateCopy.model_validate_json(
            canonical(json.loads(row["request_payload"]) | {"request_key": str(row["request_key"])})
        )
        query = self.queries.get((row["organization_id"], row["shop_id"], request.query_ref))
        if (
            query is None
            or value.retrieval.query != query
            or value.candidate_id != row["id"]
            or value.owner_id != row["owner_id"]
            or value.reviewer_id != row["reviewer_id"]
            or value.product_source_id != row["product_id"]
            or value.retrieval.registry_id != row["registry_id"]
            or request.shop_id != row["shop_id"]
            or request.registry_id != row["registry_id"]
            or request.product_source_id != row["product_id"]
            or request.reviewer_id != row["reviewer_id"]
        ):
            raise ValueError("COPY_QUERY_OR_BINDING_CHANGED")
        product = db.execute(
            "SELECT payload,evidence_id FROM business.p6_copy_products "
            "WHERE id=%s AND organization_id=%s AND shop_id=%s",
            (row["product_id"], row["organization_id"], row["shop_id"]),
        ).fetchone()
        if product is None or value.product != ProductCitation.model_validate_json(
            canonical(json.loads(product["payload"]) | {"evidence_id": product["evidence_id"]})
        ):
            raise ValueError("COPY_PRODUCT_CHANGED")
        registry = db.execute(
            "SELECT manifest,manifest_digest,profile,profile_digest FROM "
            "business.p6_knowledge_registries WHERE id=%s AND organization_id=%s "
            "AND shop_id=%s",
            (row["registry_id"], row["organization_id"], row["shop_id"]),
        ).fetchone()
        if registry is None or value.retrieval.registry_digest != registry["manifest_digest"]:
            raise ValueError("COPY_REGISTRY_CHANGED")
        manifest = Manifest.model_validate_json(
            canonical(
                json.loads(registry["manifest"]) | {"manifest_digest": registry["manifest_digest"]}
            )
        )
        if (
            request.registry_digest != manifest.manifest_digest
            or value.retrieval.scope != manifest.scope
            or value.retrieval.registry_version != manifest.manifest_version
            or value.retrieval.max_distance != manifest.max_distance
        ):
            raise ValueError("COPY_REGISTRY_CHANGED")
        profile = PgProfile.model_validate_json(
            canonical(
                json.loads(registry["profile"]) | {"profile_digest": registry["profile_digest"]}
            )
        )
        if value.retrieval.profile != profile:
            raise ValueError("COPY_PROFILE_CHANGED")
        # Even historical reads verify exact immutable evidence against owner rows.
        for evidence in value.retrieval.pool:
            if evidence.origin.citation.evidence_id not in manifest.evidence_ids:
                raise ValueError("COPY_CITATION_CHANGED")
            stored = db.execute(
                """SELECT origin,stored_sha256,
             encode(knowledge_ext.vector_send(embedding),'hex') AS stored_hex
             FROM business.p6_knowledge_embeddings WHERE organization_id=%s AND shop_id=%s
             AND evidence_id=%s AND profile_digest=%s""",
                (
                    row["organization_id"],
                    row["shop_id"],
                    evidence.origin.citation.evidence_id,
                    profile.profile_digest,
                ),
            ).fetchone()
            if (
                stored is None
                or json.loads(stored["origin"]) != evidence.origin.model_dump(mode="json")
                or stored["stored_sha256"] != evidence.stored_sha256
                or stored["stored_hex"] != evidence.stored_hex
            ):
                raise ValueError("COPY_CITATION_CHANGED")
        if not replay_rank:
            return
        ambiguous = db.execute(
            REGISTRY_DUPLICATES_SQL, (row["registry_id"], row["organization_id"], row["shop_id"])
        ).fetchone()
        if ambiguous is None or ambiguous["ambiguous"]:
            raise ValueError("COPY_REGISTRY_AMBIGUOUS")
        observed = db.execute(
            RETRIEVE_SQL,
            dict(
                registry=row["registry_id"],
                org=row["organization_id"],
                shop=row["shop_id"],
                manifest_digest=value.retrieval.registry_digest,
                profile_digest=profile.profile_digest,
                vector=query_parameter(query, profile),
                threshold=manifest.max_distance,
            ),
        ).fetchone()
        if observed is None or observed["n"] != len(value.retrieval.pool):
            raise ValueError("COPY_RANKING_CHANGED")
        actual = observed["pool"]
        if len(actual) != len(value.retrieval.pool):
            raise ValueError("COPY_RANKING_CHANGED")
        for a, expected in zip(actual, value.retrieval.pool, strict=True):
            if (
                a["origin"] != expected.origin.model_dump(mode="json")
                or a["distance"] != expected.distance
                or a["stored_hex"] != expected.stored_hex
                or a["stored_sha256"] != expected.stored_sha256
                or a["selected"] != (expected.origin.citation in value.retrieval.hits)
            ):
                raise ValueError("COPY_RANKING_CHANGED")

    def create_in_transaction(self, db: DB, actor: WebActor, request: CreateCopy) -> CopyCandidate:
        _transaction(db)
        with db.transaction():
            return self._create_in_transaction(db, actor, request)

    def create(self, actor: WebActor, request: CreateCopy) -> CopyCandidate:
        with connect(self.settings) as db:
            return self.create_in_transaction(db, actor, request)

    def candidate_request(self, actor: WebActor, request_key: UUID) -> dict[str, Any]:
        with connect(self.settings) as db:
            actor_guard(db, actor)
            row = db.execute(
                "SELECT id,shop_id FROM business.p6_copy_candidates "
                "WHERE organization_id=%s AND owner_id=%s AND request_key=%s",
                (actor.organization_id, actor.principal_id, request_key),
            ).fetchone()
            if row is None:
                return dict(
                    state="UNKNOWN", request_key=str(request_key), publication_allowed=False
                )
            identifier = row["id"]
        return self.read(actor, identifier)

    def _review_in_transaction(
        self, db: DB, actor: WebActor, identifier: UUID, request: ReviewCopy
    ) -> CopyReceipt:
        _transaction(db)
        request = checked(request)
        actor_guard(db, actor)
        row = db.execute(
            """SELECT * FROM business.p6_copy_candidates
         WHERE id=%s AND organization_id=%s AND reviewer_id=%s""",
            (identifier, actor.organization_id, actor.principal_id),
        ).fetchone()
        if row is None:
            raise WebFailure("RESOURCE_NOT_FOUND", 404)
        if not role_scope(db, actor, row["shop_id"], "approver"):
            raise WebFailure("ACCESS_DENIED", 403)
        semantics = request.model_dump(mode="json", exclude={"request_key"})
        semantics["candidate_id"] = str(identifier)
        expected_hash = digest(semantics)
        previous = db.execute(
            RECEIPT, (actor.organization_id, actor.principal_id, request.request_key)
        ).fetchone()
        if previous:
            if previous["request_hash"] != expected_hash:
                raise WebFailure("IDEMPOTENCY_CONFLICT", 409)
            return _receipt(previous)
        locked = db.execute(
            "SELECT business.p6_lock_copy(%s,%s,%s,%s,%s) AS allowed",
            (
                actor.principal_id,
                actor.organization_id,
                actor.identity_id,
                actor.auth_version,
                identifier,
            ),
        ).fetchone()
        if not locked or not locked["allowed"]:
            raise WebFailure("ACCESS_DENIED", 403)
        # Refresh after the candidate lock: another session may have committed the first decision.
        previous = db.execute(
            RECEIPT, (actor.organization_id, actor.principal_id, request.request_key)
        ).fetchone()
        if previous:
            if previous["request_hash"] != expected_hash:
                raise WebFailure("IDEMPOTENCY_CONFLICT", 409)
            return _receipt(previous)
        if db.execute(
            "SELECT 1 FROM business.p6_copy_decisions WHERE candidate_id=%s", (identifier,)
        ).fetchone():
            raise WebFailure("COPY_ALREADY_REVIEWED", 409)
        if request.candidate_hash != row["candidate_hash"]:
            raise WebFailure("COPY_VERSION_CHANGED", 409)
        current = db.execute(
            "SELECT business.p6_copy_sources_current(%s) AS allowed", (identifier,)
        ).fetchone()
        if not current or not current["allowed"]:
            raise WebFailure("COPY_SOURCE_EXPIRED_OR_REVOKED", 409)
        candidate = _candidate(row)
        self.verify_sources(db, row, candidate, replay_rank=True)
        identifier_decision, draft = uuid4(), uuid4() if request.action == "approve" else None
        db.execute(
            """INSERT INTO business.p6_copy_decisions
         (id,organization_id,shop_id,candidate_id,candidate_hash,actor_id,identity_id,session_id,
          auth_version,request_key,action,reason,request_payload,request_hash)
         VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (
                identifier_decision,
                actor.organization_id,
                row["shop_id"],
                identifier,
                request.candidate_hash,
                actor.principal_id,
                actor.identity_id,
                actor.session_id,
                actor.auth_version,
                request.request_key,
                request.action,
                request.reason,
                canonical(semantics),
                expected_hash,
            ),
        )
        if draft:
            candidate = _candidate(row)
            db.execute(
                """INSERT INTO business.p6_copy_drafts
             (id,organization_id,shop_id,candidate_id,candidate_hash,decision_id,text)
             VALUES(%s,%s,%s,%s,%s,%s,%s)""",
                (
                    draft,
                    actor.organization_id,
                    row["shop_id"],
                    identifier,
                    request.candidate_hash,
                    identifier_decision,
                    candidate.text,
                ),
            )
        return CopyReceipt(
            request_key=request.request_key,
            candidate_id=identifier,
            candidate_hash=request.candidate_hash,
            decision_id=identifier_decision,
            draft_id=draft,
            state="saved" if draft else "rejected",
        )

    def review_in_transaction(
        self, db: DB, actor: WebActor, identifier: UUID, request: ReviewCopy
    ) -> CopyReceipt:
        _transaction(db)
        with db.transaction():
            return self._review_in_transaction(db, actor, identifier, request)

    def review(self, actor: WebActor, identifier: UUID, request: ReviewCopy) -> CopyReceipt:
        with connect(self.settings) as db:
            # Return after confirmed COMMIT; transport loss is UNKNOWN at the router.
            value = self.review_in_transaction(db, actor, identifier, request)
        return value

    def receipt(
        self, actor: WebActor, identifier: UUID, request_key: UUID, candidate_hash: str
    ) -> CopyReceipt:
        with connect(self.settings) as db:
            actor_guard(db, actor)
            row = db.execute(
                """SELECT shop_id FROM business.p6_copy_candidates
             WHERE id=%s AND organization_id=%s AND reviewer_id=%s""",
                (identifier, actor.organization_id, actor.principal_id),
            ).fetchone()
            if row is None or not role_scope(db, actor, row["shop_id"], "approver"):
                raise WebFailure("RESOURCE_NOT_FOUND", 404)
            prior = db.execute(
                RECEIPT, (actor.organization_id, actor.principal_id, request_key)
            ).fetchone()
            if prior:
                if prior["candidate_id"] != identifier or prior["candidate_hash"] != candidate_hash:
                    raise WebFailure("IDEMPOTENCY_CONFLICT", 409)
                return _receipt(prior)
            # Absence in a read does not prove an in-flight COMMIT rolled back.
            return CopyReceipt(
                request_key=request_key,
                candidate_id=identifier,
                candidate_hash=candidate_hash,
                state="UNKNOWN",
            )

    def read(self, actor: WebActor, identifier: UUID) -> dict[str, Any]:
        with connect(self.settings) as db:
            db.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
            actor_guard(db, actor)
            row = db.execute(
                "SELECT * FROM business.p6_copy_candidates WHERE id=%s AND organization_id=%s",
                (identifier, actor.organization_id),
            ).fetchone()
            if row is None:
                raise WebFailure("RESOURCE_NOT_FOUND", 404)
            decision = db.execute(
                "SELECT id,action FROM business.p6_copy_decisions WHERE candidate_id=%s",
                (identifier,),
            ).fetchone()
            owner = row["owner_id"] == actor.principal_id and role_scope(
                db, actor, row["shop_id"], "operator"
            )
            reviewer = (
                row["reviewer_id"] == actor.principal_id
                and not decision
                and role_scope(db, actor, row["shop_id"], "approver")
            )
            if not owner and not reviewer:
                raise WebFailure("RESOURCE_NOT_FOUND", 404)
            available = db.execute(
                "SELECT business.p6_copy_sources_current(%s) AS allowed", (identifier,)
            ).fetchone()
            draft = (
                db.execute(
                    "SELECT id,text FROM business.p6_copy_drafts WHERE candidate_id=%s",
                    (identifier,),
                ).fetchone()
                if owner
                else None
            )
            value = _candidate(row)
            self.verify_sources(
                db, row, value, replay_rank=bool(available and available["allowed"])
            )
            if decision and ((decision["action"] == "approve") != bool(draft)):
                raise ValueError("COPY_ATOMIC_RECEIPT_INVALID")
            if draft and draft["text"] != value.text:
                raise ValueError("COPY_DRAFT_INVALID")
            return dict(
                candidate=value.model_dump(mode="json"),
                state=(
                    "saved"
                    if draft
                    else "rejected"
                    if decision
                    else "awaiting_review"
                    if available and available["allowed"]
                    else "source_unavailable"
                ),
                source_current=bool(available and available["allowed"]),
                draft_id=str(draft["id"]) if draft else None,
                publication_allowed=False,
            )
