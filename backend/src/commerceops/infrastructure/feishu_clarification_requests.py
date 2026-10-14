"""F02单请求短事务；复用原T1/inbox/权限，不执行SDK或业务Graph。"""

import json
from dataclasses import replace
from datetime import timedelta
from typing import TYPE_CHECKING, Any
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from psycopg.types.json import Jsonb

from commerceops.adapters.commerce.mock import Fixture
from commerceops.adapters.feishu.contracts import MessageProbe
from commerceops.application.feishu_business.clarification import (
    F02_TTL_SECONDS,
    F02_WORKFLOW,
    F02Candidate,
    F02Command,
    F02Source,
    parse_f02_command,
)
from commerceops.application.replenishment.contracts import (
    CreateNewCycle,
    FeishuActor,
    Parameters,
    WebFailure,
)
from commerceops.application.replenishment.nl_preflight import (
    PreflightInput,
    Window,
    parse_preflight,
)
from commerceops.domain.commerce_values import complete_days, facts_hash
from commerceops.infrastructure.web_sessions import DB, now, role_scope

if TYPE_CHECKING:
    from commerceops.infrastructure.feishu_business import FeishuBusinessStore


class F02Requests:
    def __init__(self, business: "FeishuBusinessStore"):
        self.business = business

    def _row(self, db: DB, actor: FeishuActor, identifier: UUID) -> dict[str, Any]:
        row = db.execute(
            """SELECT * FROM business.p4_clarification_requests WHERE id=%s
            AND organization_id=%s AND shop_id=%s AND app_id=%s AND tenant_key=%s
            AND principal_id=%s AND identity_id=%s AND chat_id=%s FOR UPDATE""",
            (
                identifier,
                actor.organization_id,
                self.business.shop,
                actor.app_id,
                actor.tenant_key,
                actor.principal_id,
                actor.identity_id,
                actor.chat_id,
            ),
        ).fetchone()
        if not row:
            raise WebFailure("RESOURCE_NOT_FOUND", 404)
        if not role_scope(
            db, replace(actor, auth_version=row["auth_version"]), self.business.shop, "operator"
        ):
            raise WebFailure("ACCESS_DENIED", 403)
        origin = db.execute(
            """SELECT i.payload_hash,i.sanitized_payload,r.identity_id,r.result
            FROM business.inbox_events i JOIN business.p4_inbox_receipts r ON r.inbox_id=i.id
            WHERE i.id=%s AND i.organization_id=%s AND i.shop_id=%s AND i.app_id=%s
            AND i.tenant_key=%s AND i.source='feishu_business' AND i.task_id IS NULL""",
            (
                row["origin_inbox_id"],
                row["organization_id"],
                row["shop_id"],
                row["app_id"],
                row["tenant_key"],
            ),
        ).fetchone()
        if (
            not origin
            or origin["payload_hash"] != row["source_hash"]
            or origin["identity_id"] != row["identity_id"]
            or origin["sanitized_payload"].get("principal_id") != str(row["principal_id"])
            or origin["sanitized_payload"].get("auth_version") != row["auth_version"]
            or origin["result"].get("clarification_id") != str(row["id"])
            or origin["result"].get("round") != 1
        ):
            raise WebFailure("SERVICE_UNAVAILABLE", 503)
        return row

    @staticmethod
    def _candidate(db: DB, row: dict[str, Any]) -> F02Candidate:
        value = F02Candidate.model_validate_json(json.dumps(row["candidate"]))
        if (
            value.request_id != row["id"]
            or value.round != row["round"]
            or value.confirmation_hash() != row["candidate_hash"]
        ):
            raise WebFailure("SERVICE_UNAVAILABLE", 503)
        frozen = db.execute(
            """SELECT after_state FROM business.audit_events
            WHERE organization_id=%s AND source='feishu_clarification' AND action='candidate_frozen'
            AND entity_id=%s AND after_state->>'candidate_hash'=%s""",
            (row["organization_id"], str(row["id"]), row["candidate_hash"]),
        ).fetchall()
        if len(frozen) != 1 or frozen[0]["after_state"].get("candidate") != value.model_dump(
            mode="json"
        ):
            raise WebFailure("SERVICE_UNAVAILABLE", 503)
        for key, source in value.parameter_sources.items():
            receipt = db.execute(
                """SELECT i.sanitized_payload,r.identity_id,r.result
                FROM business.inbox_events i JOIN business.p4_inbox_receipts r ON r.inbox_id=i.id
                WHERE i.id=%s AND i.organization_id=%s AND i.shop_id=%s AND i.app_id=%s
                AND i.tenant_key=%s AND i.source='feishu_business'""",
                (
                    source.inbox_id,
                    row["organization_id"],
                    row["shop_id"],
                    row["app_id"],
                    row["tenant_key"],
                ),
            ).fetchone()
            if (
                not receipt
                or receipt["identity_id"] != row["identity_id"]
                or receipt["sanitized_payload"].get("text_sha256") != source.text_hash
                or receipt["result"].get("clarification_id") != str(row["id"])
                or receipt["result"].get("clarification", {}).get("parameters", {}).get(key)
                != value.parameters[key]
                or receipt["result"].get("clarification", {}).get("parameter_sources", {}).get(key)
                != source.model_dump(mode="json")
            ):
                raise WebFailure("SERVICE_UNAVAILABLE", 503)
        return value

    def replay(self, db: DB, actor: FeishuActor, receipt: dict[str, Any]) -> None:
        self._row(db, actor, UUID(receipt["clarification_id"]))

    def _context(self, db: DB, actor: FeishuActor, text: str) -> Any:
        if len(text) > 2000:
            raise WebFailure("INVALID_REQUEST", 422)
        params = self.business.parameters
        row = db.execute(
            """SELECT external_shop_key,currency,timezone FROM business.shops
            WHERE id=%s AND organization_id=%s AND adapter_kind='mock'
            AND environment IN ('test','mock') FOR SHARE""",
            (self.business.shop, actor.organization_id),
        ).fetchone()
        fixture = Fixture.load(self.business.store.fixture_directory, params.fixture_case)
        if not row or (row["external_shop_key"], row["currency"], row["timezone"]) != (
            fixture.source.shop_id,
            fixture.source.currency,
            fixture.source.timezone,
        ):
            raise WebFailure("RESOURCE_NOT_FOUND", 404)
        start, end = complete_days(fixture.now, fixture.source.timezone)
        return parse_preflight(
            PreflightInput(
                schema_version="p3-web-v1",
                shop_id=self.business.shop,
                fixture_case=params.fixture_case,
                text=text,
            ),
            Window(start=start, end=end, timezone=fixture.source.timezone, as_of=fixture.now),
        )

    @staticmethod
    def _receipt(
        candidate: F02Candidate, reply: UUID, *, duplicate: bool = False
    ) -> dict[str, Any]:
        return {
            "schema_version": "p4-v1",
            "identity_mode": "feishu",
            "state": "needs_clarification",
            "clarification_id": str(candidate.request_id),
            "round": candidate.round,
            "candidate_hash": candidate.confirmation_hash(),
            "clarification_state": "awaiting_parameters"
            if candidate.kind == "question"
            else "awaiting_confirmation",
            "reply_id": str(reply),
            "duplicate": duplicate,
            "model_mode": "not_used",
            "clarification": candidate.model_dump(mode="json"),
        }

    def _record(
        self,
        db: DB,
        actor: FeishuActor,
        message: MessageProbe,
        semantic: str,
        inbox: UUID,
        receipt: dict[str, Any],
        *,
        task: bool = False,
    ) -> None:
        self.business._record(
            db,
            actor,
            message.event_id,
            message.message_id,
            semantic,
            receipt,
            {
                "schema_version": "p4-v1",
                "event_type": "im.message.receive_v1" if task else "p4.clarification",
                "chat_id": message.chat_id,
                "chat_type": message.chat_type,
                "text_sha256": facts_hash(message.text),
                "source_mode": "mock",
                "model_mode": "not_used",
                "clarification_id": receipt["clarification_id"],
                "round": receipt["round"],
                "auth_version": actor.auth_version,
            },
            inbox_id=inbox,
            link_task=task,
        )

    @staticmethod
    def _audit(db: DB, actor: FeishuActor, candidate: F02Candidate, inbox: UUID) -> None:
        db.execute(
            """INSERT INTO business.audit_events(id,organization_id,source,action,
            entity_type,entity_id,after_state,trace_id) VALUES(%s,%s,'feishu_clarification',
            'candidate_frozen','clarification_request',%s,%s,%s)""",
            (
                uuid4(),
                actor.organization_id,
                str(candidate.request_id),
                Jsonb(
                    {
                        "candidate": candidate.model_dump(mode="json"),
                        "candidate_hash": candidate.confirmation_hash(),
                        "inbox_id": str(inbox),
                    }
                ),
                inbox,
            ),
        )

    def _reply(
        self,
        db: DB,
        actor: FeishuActor,
        message: MessageProbe,
        inbox: UUID,
        identifier: UUID,
        candidate: F02Candidate,
    ) -> None:
        db.execute(
            """INSERT INTO business.p4_clarification_replies
            (id,inbox_id,organization_id,shop_id,principal_id,identity_id,chat_id,chat_type,
             reason_code,template_version,provider_uuid,request_id,round,kind,
             frozen_payload,frozen_payload_hash)
            VALUES(%s,%s,%s,%s,%s,%s,%s,%s,'REQUEST_NEEDS_CLARIFICATION',
            'p4-f02-reply-v1',%s,%s,%s,%s,%s,%s)""",
            (
                identifier,
                inbox,
                actor.organization_id,
                self.business.shop,
                actor.principal_id,
                actor.identity_id,
                message.chat_id,
                message.chat_type,
                uuid4(),
                candidate.request_id,
                candidate.round,
                candidate.kind,
                Jsonb(candidate.model_dump(mode="json")),
                facts_hash(candidate.model_dump(mode="json")),
            ),
        )

    def accept(
        self, db: DB, actor: FeishuActor, message: MessageProbe, semantic: str
    ) -> dict[str, Any] | None:
        try:
            command = parse_f02_command(message.text)
        except ValueError:
            raise WebFailure("INVALID_REQUEST", 422) from None
        if command is not None:
            return self._turn(db, actor, message, semantic, command)
        parsed = self._context(db, actor, message.text)
        if parsed.status == "unsupported":
            return None
        inbox, identifier, reply = uuid4(), uuid4(), uuid4()
        explicit = {c.name: c.value for c in parsed.candidates if c.source == "explicit_text"}
        sources = {
            c.name: F02Source(
                inbox_id=inbox, text_hash=facts_hash(message.text), start=c.start, end=c.end
            )
            for c in parsed.candidates
            if c.source == "explicit_text" and c.start is not None and c.end is not None
        }
        candidate = F02Candidate(
            request_id=identifier,
            round=1,
            kind="ready" if len(explicit) == 3 else "question",
            source=parsed.source,
            window=parsed.window,
            scope=parsed.scope,
            parameters=explicit,
            parameter_sources=sources,
        )
        receipt = self._receipt(candidate, reply)
        self._record(db, actor, message, semantic, inbox, receipt)
        timestamp = now(db)
        payload = candidate.model_dump(mode="json")
        db.execute(
            """INSERT INTO business.p4_clarification_requests
            (id,origin_inbox_id,organization_id,shop_id,app_id,tenant_key,principal_id,identity_id,
             auth_version,chat_id,chat_type,workflow_version,source_hash,request_key,round,context,
             candidate,candidate_hash,state,created_at,expires_at,updated_at)
            VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,1,%s,%s,%s,%s,%s,%s,%s)""",
            (
                identifier,
                inbox,
                actor.organization_id,
                self.business.shop,
                actor.app_id,
                actor.tenant_key,
                actor.principal_id,
                actor.identity_id,
                actor.auth_version,
                message.chat_id,
                message.chat_type,
                F02_WORKFLOW,
                semantic,
                uuid5(NAMESPACE_URL, f"p4-f02-t1:{identifier}"),
                Jsonb({k: payload[k] for k in ("source", "window", "scope")}),
                Jsonb(payload),
                candidate.confirmation_hash(),
                receipt["clarification_state"],
                timestamp,
                timestamp + timedelta(seconds=F02_TTL_SECONDS),
                timestamp,
            ),
        )
        self._reply(db, actor, message, inbox, reply, candidate)
        self._audit(db, actor, candidate, inbox)
        return receipt

    def _turn(
        self, db: DB, actor: FeishuActor, message: MessageProbe, semantic: str, command: F02Command
    ) -> dict[str, Any]:
        row = self._row(db, actor, command.request_id)
        if row["chat_type"] != message.chat_type:
            raise WebFailure("RESOURCE_NOT_FOUND", 404)
        if row["state"] == "consumed":
            if command.action != "confirm":
                raise WebFailure("CLARIFICATION_CONSUMED")
            saved = db.execute(
                "SELECT result FROM business.p4_inbox_receipts WHERE inbox_id=%s",
                (row["confirmed_inbox_id"],),
            ).fetchone()
            if not saved:
                raise WebFailure("SERVICE_UNAVAILABLE", 503)
            receipt = {**saved["result"], "duplicate": True}
            self._record(db, actor, message, semantic, uuid4(), receipt)
            return receipt
        if row["state"] == "expired" or now(db) >= row["expires_at"]:
            raise WebFailure("CLARIFICATION_EXPIRED")
        if command.round != row["round"]:
            raise WebFailure("CLARIFICATION_ROUND_CONFLICT")
        candidate = self._candidate(db, row)
        inbox, reply = uuid4(), uuid4()
        if command.action == "supplement":
            if all(candidate.parameters.get(k) == v for k, v in command.parameters.items()):
                old_reply = db.execute(
                    "SELECT id FROM business.p4_clarification_replies "
                    "WHERE request_id=%s AND round=%s ORDER BY created_at DESC LIMIT 1",
                    (row["id"], row["round"]),
                ).fetchone()
                if not old_reply:
                    raise WebFailure("SERVICE_UNAVAILABLE", 503)
                receipt = self._receipt(candidate, old_reply["id"], duplicate=True)
                self._record(db, actor, message, semantic, inbox, receipt)
                return receipt
            parameters = {**candidate.parameters, **command.parameters}
            sources = {
                **candidate.parameter_sources,
                **{
                    k: F02Source(
                        inbox_id=inbox,
                        text_hash=facts_hash(message.text),
                        start=span[0],
                        end=span[1],
                    )
                    for k, span in command.spans.items()
                },
            }
            candidate = F02Candidate(
                request_id=candidate.request_id,
                round=candidate.round + 1,
                kind="ready" if len(parameters) == 3 else "question",
                source=candidate.source,
                window=candidate.window,
                scope=candidate.scope,
                parameters=parameters,
                parameter_sources=sources,
            )
            receipt = self._receipt(candidate, reply)
            self._record(db, actor, message, semantic, inbox, receipt)
            db.execute(
                """UPDATE business.p4_clarification_requests SET round=%s,candidate=%s,
                candidate_hash=%s,state=%s,updated_at=clock_timestamp() WHERE id=%s""",
                (
                    candidate.round,
                    Jsonb(candidate.model_dump(mode="json")),
                    candidate.confirmation_hash(),
                    receipt["clarification_state"],
                    row["id"],
                ),
            )
            self._reply(db, actor, message, inbox, reply, candidate)
            self._audit(db, actor, candidate, inbox)
            return receipt
        if candidate.kind != "ready":
            raise WebFailure("CLARIFICATION_INCOMPLETE")
        confirmed_parameters = Parameters(
            source_mode=candidate.source.source_mode,
            dataset_version=candidate.source.dataset_version,
            fixture_case=candidate.source.fixture_case,
            L=candidate.parameters["L"],
            R=candidate.parameters["R"],
            S=candidate.parameters["S"],
        )
        if (
            confirmed_parameters != self.business.parameters
            or candidate.scope.shop_id != self.business.shop
        ):
            raise WebFailure("CLARIFICATION_WINDOW_SCOPE_CHANGED", 503)
        current = self._context(db, actor, "分析库存 L=0 R=0 S=0")
        if (current.source, current.window, current.scope) != (
            candidate.source,
            candidate.window,
            candidate.scope,
        ):
            raise WebFailure("CLARIFICATION_SOURCE_CHANGED")
        if self.business.gateway_guard:
            self.business.gateway_guard(db, True)
        task = self.business.store.create_in_transaction(
            db,
            replace(actor, topic_key=f"p4-f02:{row['id']}"),
            CreateNewCycle(
                schema_version="p3-web-v1",
                mode="new_cycle",
                shop_id=self.business.shop,
                request_key=row["request_key"],
                parameters=confirmed_parameters,
            ),
        )
        receipt = {
            **task,
            "schema_version": "p4-v1",
            "identity_mode": "feishu",
            "clarification_id": str(row["id"]),
            "round": row["round"],
            "candidate_hash": row["candidate_hash"],
            "clarification_state": "consumed",
            "reply_id": str(reply),
            "model_mode": "not_used",
        }
        self._record(db, actor, message, semantic, inbox, receipt, task=True)
        if self.business.hook:
            self.business.hook("before_f02_consume")
        db.execute(
            """UPDATE business.p4_clarification_requests SET state='consumed',task_id=%s,
            confirmed_inbox_id=%s,updated_at=clock_timestamp() WHERE id=%s""",
            (UUID(receipt["task_id"]), inbox, row["id"]),
        )
        created = F02Candidate.model_validate(
            {**candidate.model_dump(), "kind": "created", "task_id": UUID(receipt["task_id"])}
        )
        self._reply(db, actor, message, inbox, reply, created)
        return receipt
