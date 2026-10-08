"""技术 Base 操作：固定持久 token、跨进程同表锁、unknown 停止并分页对账。"""

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Protocol
from uuid import UUID, uuid4

from lark_oapi.api.bitable.v1 import (  # type: ignore[import-untyped]
    AppTableRecord,
    CreateAppTableRecordRequest,
    ListAppTableRecordRequest,
    UpdateAppTableRecordRequest,
)
from psycopg import Connection
from psycopg.types.json import Jsonb

from commerceops.adapters.feishu.repository import Connections, ProbeConflict
from commerceops.adapters.feishu.sdk import restrict_sdk_logs
from commerceops.infrastructure.repository import TaskScope

PROBE_MARKER = "commerceops-p1-05-probe"
BASE_FIELDS = frozenset(
    {"ProbeID", "ProbeMarker", "SourceMode", "ApprovalMode", "State", "UpdatedAt"}
)
KNOWN_REJECTION_CODES = frozenset({1254290, 1254291})


@dataclass(frozen=True)
class ApiReply:
    http_status: int | None
    code: int | None
    data: dict[str, Any]

    @property
    def success(self) -> bool:
        return (
            type(self.http_status) is int
            and 200 <= self.http_status < 300
            and type(self.code) is int
            and self.code == 0
        )


class RecordTransport(Protocol):
    def create(
        self, app_token: str, table_id: str, token: str, fields: dict[str, str]
    ) -> ApiReply: ...

    def list(self, app_token: str, table_id: str, page_token: str | None) -> ApiReply: ...

    def update(
        self, app_token: str, table_id: str, record_id: str, fields: dict[str, str]
    ) -> ApiReply: ...


class RecordSDK:
    def __init__(self, client: Any, *, option: Any = None):
        restrict_sdk_logs()
        self.client = client
        self.option = option

    @staticmethod
    def _reply(response: Any) -> ApiReply:
        status = getattr(getattr(response, "raw", None), "status_code", None)
        code = getattr(response, "code", None)
        content = getattr(getattr(response, "raw", None), "content", None)
        data: dict[str, Any] = {}
        if type(content) is bytes and len(content) <= 4 * 1024 * 1024:
            try:
                body = json.loads(content)
                if type(body) is dict and type(body.get("data")) is dict:
                    data = body["data"]
            except (ValueError, UnicodeError, RecursionError):
                pass
        return ApiReply(status, code, data)

    def create(self, app_token: str, table_id: str, token: str, fields: dict[str, str]) -> ApiReply:
        request = (
            CreateAppTableRecordRequest.builder()
            .app_token(app_token)
            .table_id(table_id)
            .client_token(token)
            .ignore_consistency_check(False)
            .request_body(AppTableRecord.builder().fields(fields).build())
            .build()
        )
        return self._reply(self.client.bitable.v1.app_table_record.create(request, self.option))

    def list(self, app_token: str, table_id: str, page_token: str | None) -> ApiReply:
        builder = (
            ListAppTableRecordRequest.builder()
            .app_token(app_token)
            .table_id(table_id)
            .page_size(100)
            .field_names(json.dumps(sorted(BASE_FIELDS)))
        )
        if page_token is not None:
            builder.page_token(page_token)
        return self._reply(
            self.client.bitable.v1.app_table_record.list(builder.build(), self.option)
        )

    def update(
        self, app_token: str, table_id: str, record_id: str, fields: dict[str, str]
    ) -> ApiReply:
        request = (
            UpdateAppTableRecordRequest.builder()
            .app_token(app_token)
            .table_id(table_id)
            .record_id(record_id)
            .ignore_consistency_check(False)
            .request_body(AppTableRecord.builder().fields(fields).build())
            .build()
        )
        return self._reply(self.client.bitable.v1.app_table_record.update(request, self.option))


def validate_fields(probe_id: UUID, fields: dict[str, str]) -> None:
    if (
        set(fields) != BASE_FIELDS
        or any(type(value) is not str or not value or len(value) > 256 for value in fields.values())
        or fields["ProbeID"] != str(probe_id)
        or fields["ProbeMarker"] != PROBE_MARKER
        or fields["SourceMode"] != "feishu_technical_probe"
        or fields["ApprovalMode"] != "simulated_probe"
        or fields["State"] not in {"created", "updated", "probe_complete"}
    ):
        raise ProbeConflict()
    try:
        timestamp = datetime.fromisoformat(fields["UpdatedAt"])
    except ValueError:
        raise ProbeConflict() from None
    if timestamp.utcoffset() != timedelta(0):
        raise ProbeConflict()


def request_hash(app_token: str, table_id: str, fields: dict[str, str]) -> str:
    data = {"app_token": app_token, "table_id": table_id, "fields": fields}
    return hashlib.sha256(
        json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


class BaseProbe:
    def __init__(
        self,
        connections: Connections,
        scope: TaskScope,
        transport: RecordTransport,
        *,
        target: tuple[str, str] | None = None,
    ):
        self.connections = connections
        self.scope = scope
        self.transport = transport
        self.target = target

    def prepare(
        self, probe_id: UUID, app_token: str, table_id: str, fields: dict[str, str]
    ) -> UUID:
        validate_fields(probe_id, fields)
        if not app_token or not table_id:
            raise ProbeConflict()
        digest = request_hash(app_token, table_id, fields)
        with self.connections() as connection:
            connection.execute(
                """INSERT INTO feishu_probe.base_operations
                (id,organization_id,shop_id,app_token,table_id,client_token,request_sha256,fields)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(id) DO NOTHING""",
                (
                    probe_id,
                    self.scope.organization_id,
                    self.scope.shop_id,
                    app_token,
                    table_id,
                    uuid4(),
                    digest,
                    Jsonb(fields),
                ),
            )
            row = self._load(connection, probe_id)
            if row["request_sha256"] != digest:
                raise ProbeConflict()
        return UUID(str(row["client_token"]))

    def _load(self, connection: Connection[dict[str, Any]], probe_id: UUID) -> dict[str, Any]:
        row = connection.execute(
            """SELECT * FROM feishu_probe.base_operations
            WHERE id=%s AND organization_id=%s AND shop_id=%s""",
            (probe_id, self.scope.organization_id, self.scope.shop_id),
        ).fetchone()
        if row is None:
            raise ProbeConflict()
        if self.target is not None and (row["app_token"], row["table_id"]) != self.target:
            raise ProbeConflict()
        validate_fields(probe_id, row["fields"])
        if row["request_sha256"] != request_hash(row["app_token"], row["table_id"], row["fields"]):
            raise ProbeConflict()
        if row["pending_kind"] == "update":
            validate_fields(probe_id, row["pending_fields"])
            if row["pending_sha256"] != request_hash(
                row["app_token"], row["table_id"], row["pending_fields"]
            ):
                raise ProbeConflict()
        return row

    def _status(
        self,
        probe_id: UUID,
        status: str,
        *,
        record_id: str | None = None,
        code: int | None = None,
    ) -> None:
        with self.connections() as connection:
            connection.execute(
                """UPDATE feishu_probe.base_operations SET status=%s,record_id=%s,last_code=%s,
                updated_at=clock_timestamp() WHERE id=%s AND organization_id=%s AND shop_id=%s""",
                (
                    status,
                    record_id,
                    code if type(code) is int else None,
                    probe_id,
                    self.scope.organization_id,
                    self.scope.shop_id,
                ),
            )

    def _table_lock(self, connection: Connection[dict[str, Any]], row: dict[str, Any]) -> str:
        key = f"feishu-base:{row['app_token']}:{row['table_id']}"
        connection.execute("SELECT pg_advisory_lock(hashtextextended(%s,0))", (key,))
        connection.commit()
        return key

    def create_once(self, probe_id: UUID, *, retry_known_rejection: bool = False) -> str:
        with self.connections() as lock_connection:
            row = self._load(lock_connection, probe_id)
            key = self._table_lock(lock_connection, row)
            try:
                row = self._load(lock_connection, probe_id)
                lock_connection.commit()
                allowed = row["status"] == "ready" or (
                    retry_known_rejection
                    and row["status"] == "blocked"
                    and row["last_code"] in KNOWN_REJECTION_CODES
                )
                if not allowed:
                    return str(row["status"])
                # commit inflight 在外部调用之前；崩溃遗留 inflight 也只可对账。
                self._status(probe_id, "inflight")
                try:
                    reply = self.transport.create(
                        row["app_token"], row["table_id"], str(row["client_token"]), row["fields"]
                    )
                except Exception:
                    self._status(probe_id, "unknown")
                    return "unknown"
                record = reply.data.get("record")
                record_id = record.get("record_id") if type(record) is dict else None
                if reply.success and type(record_id) is str and record_id:
                    self._status(probe_id, "succeeded", record_id=record_id, code=0)
                    return "succeeded"
                if (
                    type(reply.code) is int
                    and reply.code > 0
                    and type(reply.http_status) is int
                    and (reply.http_status == 200 or 400 <= reply.http_status < 500)
                    and reply.code not in {1255006, 1255040, 1254607}
                ):
                    self._status(probe_id, "blocked", code=reply.code)
                    return "blocked"
                status = "conflict" if reply.code == 1255006 else "unknown"
                self._status(probe_id, status, code=reply.code)
                return status
            finally:
                lock_connection.execute("SELECT pg_advisory_unlock(hashtextextended(%s,0))", (key,))

    def reconcile(self, probe_id: UUID, *, verify_succeeded: bool = False) -> str:
        with self.connections() as lock_connection:
            row = self._load(lock_connection, probe_id)
            key = self._table_lock(lock_connection, row)
            try:
                row = self._load(lock_connection, probe_id)
                lock_connection.commit()
                allowed = {"unknown", "inflight"} | ({"succeeded"} if verify_succeeded else set())
                if row["status"] not in allowed:
                    return str(row["status"])
                found: list[str] = []
                content_matches = True
                page_token: str | None = None
                seen: set[str] = set()
                for _ in range(100):
                    try:
                        reply = self.transport.list(row["app_token"], row["table_id"], page_token)
                    except Exception:
                        return "unknown"
                    items = reply.data.get("items")
                    more = reply.data.get("has_more")
                    if not reply.success or type(items) is not list or type(more) is not bool:
                        return "unknown"
                    for item in items:
                        if type(item) is not dict or type(item.get("fields")) is not dict:
                            return "unknown"
                        fields = item["fields"]
                        if fields.get("ProbeID") == str(probe_id):
                            if (
                                fields.get("ProbeMarker") != PROBE_MARKER
                                or fields.get("SourceMode") != "feishu_technical_probe"
                                or fields.get("ApprovalMode") != "simulated_probe"
                                or type(item.get("record_id")) is not str
                                or not item["record_id"]
                            ):
                                self._status(probe_id, "conflict")
                                return "conflict"
                            found.append(item["record_id"])
                            expected_fields = (
                                row["pending_fields"]
                                if row["pending_kind"] == "update"
                                else row["fields"]
                            )
                            if any(
                                fields.get(name) != value for name, value in expected_fields.items()
                            ):
                                content_matches = False
                    if not more:
                        if len(found) == 1:
                            if not content_matches:
                                self._status(probe_id, "unknown", record_id=found[0])
                                return "unknown"
                            self._status(probe_id, "succeeded", record_id=found[0])
                            return "succeeded"
                        if len(found) > 1:
                            self._status(probe_id, "conflict")
                            return "conflict"
                        # 全量未找到也不回到 ready；未知外部一致性窗口不能推导未创建。
                        self._status(probe_id, "unknown")
                        return "unknown"
                    next_token = reply.data.get("page_token")
                    if type(next_token) is not str or not next_token or next_token in seen:
                        return "unknown"
                    seen.add(next_token)
                    page_token = next_token
                return "unknown"
            finally:
                lock_connection.execute("SELECT pg_advisory_unlock(hashtextextended(%s,0))", (key,))

    def update_once(self, probe_id: UUID, *, state: str, updated_at: str) -> str:
        with self.connections() as lock_connection:
            row = self._load(lock_connection, probe_id)
            key = self._table_lock(lock_connection, row)
            try:
                row = self._load(lock_connection, probe_id)
                lock_connection.commit()
                if row["status"] != "succeeded" or not row["record_id"]:
                    return str(row["status"])
                fields = {**row["fields"], "State": state, "UpdatedAt": updated_at}
                validate_fields(probe_id, fields)
                digest = request_hash(row["app_token"], row["table_id"], fields)
                if row["pending_kind"] == "update" and row["pending_sha256"] == digest:
                    return "succeeded"
                with self.connections() as connection:
                    connection.execute(
                        """UPDATE feishu_probe.base_operations SET status='inflight',
                        pending_kind='update',pending_fields=%s,pending_sha256=%s WHERE id=%s
                        AND organization_id=%s AND shop_id=%s""",
                        (
                            Jsonb(fields),
                            digest,
                            probe_id,
                            self.scope.organization_id,
                            self.scope.shop_id,
                        ),
                    )
                try:
                    reply = self.transport.update(
                        row["app_token"], row["table_id"], row["record_id"], fields
                    )
                except Exception:
                    self._status(probe_id, "unknown", record_id=row["record_id"])
                    return "unknown"
                if not reply.success:
                    self._status(probe_id, "unknown", record_id=row["record_id"], code=reply.code)
                    return "unknown"
                record = reply.data.get("record")
                if type(record) is not dict or record.get("record_id") != row["record_id"]:
                    self._status(probe_id, "unknown", record_id=row["record_id"])
                    return "unknown"
                self._status(probe_id, "succeeded", record_id=row["record_id"], code=0)
                return "succeeded"
            finally:
                lock_connection.execute("SELECT pg_advisory_unlock(hashtextextended(%s,0))", (key,))
