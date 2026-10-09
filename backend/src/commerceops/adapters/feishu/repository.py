"""技术接收与探针决定的 PG 事务；不创建业务 task/job/approval。"""

import hashlib
import json
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

from psycopg import Connection
from psycopg.types.json import Jsonb

from commerceops.adapters.feishu.contracts import (
    CardProbe,
    ContractCode,
    PlatformIdentity,
    ProbeBinding,
    ProbeContractError,
    ProbePlan,
    ProbePolicy,
    _envelope,
    _identity,
    _object,
    _uuid,
    parse_card,
    parse_message,
)
from commerceops.infrastructure.repository import TaskScope

Connections = Callable[[], AbstractContextManager[Connection[dict[str, Any]]]]


class ProbeDatabaseFailure(RuntimeError):
    def __init__(self) -> None:
        super().__init__("PROBE_DATABASE_FAILURE")


class ProbeConflict(ValueError):
    def __init__(self) -> None:
        super().__init__("PROBE_EVENT_CONFLICT")


@dataclass(frozen=True)
class ProbeReceipt:
    receipt_id: UUID
    result: str


def semantic_hash(payload: dict[str, Any]) -> str:
    body = {key: value for key, value in payload.items() if key != "event_id"}
    return hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


class ProbeRepository:
    def __init__(self, connections: Connections, scope: TaskScope, policy: ProbePolicy):
        self.connections = connections
        self.scope = scope
        self.policy = policy

    def _authorize(
        self, connection: Connection[dict[str, Any]], identity: PlatformIdentity, role: str
    ) -> UUID:
        row = connection.execute(
            """SELECT p.id FROM business.principals p
            JOIN business.identities i ON i.organization_id=p.organization_id
            AND i.principal_id=p.id
            JOIN business.organizations o ON o.id=p.organization_id
            JOIN business.shops s ON s.organization_id=o.id
            WHERE o.id=%s AND s.id=%s AND i.provider='feishu' AND i.app_id=%s
            AND i.tenant_key=%s AND i.external_subject=%s AND p.enabled
            AND o.feishu_app_id=i.app_id AND o.feishu_tenant_key=i.tenant_key
            AND (%s=ANY(p.roles) OR 'admin'=ANY(p.roles))
            FOR SHARE OF p,i,o,s""",
            (
                self.scope.organization_id,
                self.scope.shop_id,
                identity.app_id,
                identity.tenant_key,
                identity.open_id,
                role,
            ),
        ).fetchone()
        if row is None:
            raise ProbeContractError(ContractCode.IDENTITY_DENIED)
        return UUID(str(row["id"]))

    def _event_lock(self, connection: Connection[dict[str, Any]], event_id: str) -> None:
        key = f"feishu-event:{self.policy.app_id}:{self.policy.tenant_key}:{event_id}"
        connection.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))", (key,))

    def _existing(
        self, connection: Connection[dict[str, Any]], event_id: str, digest: str
    ) -> ProbeReceipt | None:
        row = connection.execute(
            """SELECT r.* FROM feishu_probe.event_keys e
            JOIN feishu_probe.receipts r ON r.id=e.receipt_id
            WHERE e.app_id=%s AND e.tenant_key=%s AND e.event_id=%s""",
            (self.policy.app_id, self.policy.tenant_key, event_id),
        ).fetchone()
        if row is None:
            return None
        if (
            row["organization_id"] != self.scope.organization_id
            or row["shop_id"] != self.scope.shop_id
            or row["payload_sha256"] != digest
        ):
            raise ProbeConflict()
        return ProbeReceipt(row["id"], "duplicate:" + row["result"])

    def _alias(
        self, connection: Connection[dict[str, Any]], event_id: str, receipt_id: UUID
    ) -> None:
        connection.execute(
            "INSERT INTO feishu_probe.event_keys VALUES (%s,%s,%s,%s)",
            (self.policy.app_id, self.policy.tenant_key, event_id, receipt_id),
        )

    def _insert(
        self,
        connection: Connection[dict[str, Any]],
        payload: dict[str, Any],
        actor: UUID,
        result: str,
        *,
        message_id: str | None = None,
        card: CardProbe | None = None,
    ) -> ProbeReceipt:
        receipt_id = uuid4()
        connection.execute(
            """INSERT INTO feishu_probe.receipts
            (id,organization_id,shop_id,app_id,tenant_key,kind,message_id,context_message_id,
            probe_id,actor_id,payload_sha256,sanitized_payload,result)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (
                receipt_id,
                self.scope.organization_id,
                self.scope.shop_id,
                self.policy.app_id,
                self.policy.tenant_key,
                "card" if card else "message",
                message_id,
                card.context_message_id if card else None,
                UUID(card.probe_id) if card else None,
                actor,
                semantic_hash(payload),
                Jsonb(payload),
                result,
            ),
        )
        self._alias(connection, str(payload["event_id"]), receipt_id)
        return ProbeReceipt(receipt_id, result)

    def receive_message(self, payload: object) -> ProbeReceipt:
        parsed = parse_message(payload, self.policy)
        sanitized = parsed.sanitized_payload()
        digest = semantic_hash(sanitized)
        try:
            with self.connections() as connection:
                actor = self._authorize(connection, parsed.identity, "operator")
                self._event_lock(connection, parsed.event_id)
                self._event_lock(connection, "message:" + parsed.message_id)
                result = self._existing(connection, parsed.event_id, digest)
                if result is None:
                    row = connection.execute(
                        """SELECT * FROM feishu_probe.receipts
                        WHERE app_id=%s AND tenant_key=%s AND message_id=%s""",
                        (self.policy.app_id, self.policy.tenant_key, parsed.message_id),
                    ).fetchone()
                    if row is not None:
                        if row["payload_sha256"] != digest or row["shop_id"] != self.scope.shop_id:
                            raise ProbeConflict()
                        self._alias(connection, parsed.event_id, row["id"])
                        result = ProbeReceipt(row["id"], "duplicate:" + row["result"])
                    else:
                        result = self._insert(
                            connection,
                            sanitized,
                            actor,
                            "message_received",
                            message_id=parsed.message_id,
                        )
            # 不得将 return 移到 with 内；退出时真正 COMMIT，失败不能返回 receipt。
            return result
        except (ProbeContractError, ProbeConflict):
            raise
        except Exception:
            raise ProbeDatabaseFailure() from None

    def register_card(self, plan: ProbePlan, *, outbound: bool = False) -> None:
        if plan.chat_id not in self.policy.allowed_group_chat_ids:
            raise ProbeContractError(ContractCode.CHAT_DENIED)
        bound = plan.binding()
        binding = {
            "probe_id": bound.probe_id,
            "task_id": bound.task_id,
            "approval_id": bound.approval_id,
            "plan_id": bound.plan_id,
            "plan_version": bound.plan_version,
            "plan_hash": bound.plan_hash,
            "required_assumption_keys": list(bound.required_assumption_keys),
        }
        with self.connections() as connection:
            scope = connection.execute(
                """SELECT 1 FROM business.organizations o JOIN business.shops s
                ON s.organization_id=o.id WHERE o.id=%s AND s.id=%s
                AND o.feishu_app_id=%s AND o.feishu_tenant_key=%s""",
                (
                    self.scope.organization_id,
                    self.scope.shop_id,
                    self.policy.app_id,
                    self.policy.tenant_key,
                ),
            ).fetchone()
            if scope is None:
                raise ProbeContractError(ContractCode.TENANT_DENIED)
            connection.execute(
                """INSERT INTO feishu_probe.cards
                (id,organization_id,shop_id,binding,nonce_sha256,expires_at,chat_id,message_id,send_status)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (
                    UUID(bound.probe_id),
                    self.scope.organization_id,
                    self.scope.shop_id,
                    Jsonb(binding),
                    bound.nonce_sha256,
                    bound.expires_at,
                    bound.chat_id,
                    bound.message_id,
                    "draft" if outbound else "registered",
                ),
            )

    def receive_card(self, payload: object) -> ProbeReceipt:
        event_id, event = _envelope(payload, self.policy, "card.action.trigger")
        operator = _object(event.get("operator"))
        identity = _identity(operator, operator.get("open_id"), self.policy)
        probe_id = UUID(_uuid(_object(_object(event.get("action")).get("value")).get("probe_id")))
        try:
            with self.connections() as connection:
                actor = self._authorize(connection, identity, "approver")
                # event 在 card 之前锁；同一卡片首次决定通过 FOR UPDATE 串行裁决。
                self._event_lock(connection, event_id)
                row = connection.execute(
                    """SELECT * FROM feishu_probe.cards
                    WHERE id=%s AND organization_id=%s AND shop_id=%s FOR UPDATE""",
                    (probe_id, self.scope.organization_id, self.scope.shop_id),
                ).fetchone()
                if row is None:
                    raise ProbeContractError(ContractCode.PLAN_MISMATCH)
                if row["send_status"] not in {"registered", "sent"}:
                    raise ProbeContractError(ContractCode.PLAN_MISMATCH)
                if row["chat_id"] not in self.policy.allowed_group_chat_ids:
                    raise ProbeContractError(ContractCode.CHAT_DENIED)
                clock = connection.execute("SELECT clock_timestamp() AS checked_at").fetchone()
                if clock is None:
                    raise ProbeDatabaseFailure()
                expected = ProbeBinding(
                    **{
                        key: value
                        for key, value in row["binding"].items()
                        if key != "required_assumption_keys"
                    },
                    required_assumption_keys=tuple(row["binding"]["required_assumption_keys"]),
                    nonce_sha256=row["nonce_sha256"],
                    expires_at=row["expires_at"],
                    chat_id=row["chat_id"],
                    message_id=row["message_id"],
                )
                parsed = parse_card(payload, self.policy, expected, clock["checked_at"])
                sanitized = parsed.sanitized_payload()
                result = self._existing(connection, event_id, semantic_hash(sanitized))
                if result is None:
                    if row["decision"] is None:
                        connection.execute(
                            """UPDATE feishu_probe.cards SET decision=%s,decided_by=%s,
                            decided_value_sha256=%s,decided_at=clock_timestamp() WHERE id=%s""",
                            (parsed.action, actor, parsed.value_sha256, probe_id),
                        )
                        state = "probe_recorded:" + parsed.action
                    elif (
                        row["decided_by"] == actor
                        and row["decision"] == parsed.action
                        and row["decided_value_sha256"] == parsed.value_sha256
                    ):
                        state = "duplicate_decision:" + parsed.action
                    else:
                        state = "decision_conflict"
                    result = self._insert(connection, sanitized, actor, state, card=parsed)
            return result
        except (ProbeContractError, ProbeConflict):
            raise
        except Exception:
            raise ProbeDatabaseFailure() from None
