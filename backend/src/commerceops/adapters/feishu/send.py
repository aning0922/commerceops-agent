"""一次性技术卡片发送；固定持久 uuid，结果未知时停下，不构建生产 outbox。"""

import hmac
import json
from typing import Any
from uuid import UUID

from lark_oapi.api.im.v1 import (  # type: ignore[import-untyped]
    CreateMessageRequest,
    CreateMessageRequestBody,
)

from commerceops.adapters.feishu.cards import build_probe_card
from commerceops.adapters.feishu.contracts import ProbePlan
from commerceops.adapters.feishu.repository import ProbeConflict, ProbeRepository
from commerceops.adapters.feishu.sdk import restrict_sdk_logs


class CardSender:
    def __init__(self, repository: ProbeRepository, client: Any, *, option: Any = None):
        restrict_sdk_logs()
        self.repository = repository
        self.client = client
        self.option = option

    def send_once(self, plan: ProbePlan) -> str:
        repository = self.repository
        with repository.connections() as connection:
            scope = connection.execute(
                """SELECT 1 FROM business.organizations o WHERE o.id=%s
                AND o.feishu_app_id=%s AND o.feishu_tenant_key=%s""",
                (
                    repository.scope.organization_id,
                    repository.policy.app_id,
                    repository.policy.tenant_key,
                ),
            ).fetchone()
            if scope is None:
                raise ProbeConflict()
            row = connection.execute(
                """SELECT * FROM feishu_probe.cards WHERE id=%s
                AND organization_id=%s AND shop_id=%s FOR UPDATE""",
                (UUID(plan.probe_id), repository.scope.organization_id, repository.scope.shop_id),
            ).fetchone()
            if row is None:
                raise ProbeConflict()
            expected = plan.binding()
            if (
                row["chat_id"] != plan.chat_id
                or plan.chat_id not in repository.policy.allowed_group_chat_ids
                or row["binding"]["plan_id"] != plan.plan_id
                or row["binding"]["task_id"] != plan.task_id
                or row["binding"]["approval_id"] != plan.approval_id
                or row["binding"]["plan_hash"] != plan.plan_hash
                or row["binding"]["plan_version"] != plan.plan_version
                or sorted(row["binding"]["required_assumption_keys"])
                != sorted(plan.required_assumption_keys)
                or row["expires_at"] != plan.expires_at
                or not hmac.compare_digest(row["nonce_sha256"], expected.nonce_sha256)
            ):
                raise ProbeConflict()
            clock = connection.execute("SELECT clock_timestamp() AS now").fetchone()
            if clock is None or clock["now"] >= plan.expires_at:
                raise ProbeConflict()
            if row["send_status"] != "draft":
                return str(row["send_status"])
            connection.execute(
                "UPDATE feishu_probe.cards SET send_status='inflight' WHERE id=%s",
                (UUID(plan.probe_id),),
            )
        # 真正 COMMIT 后才开始外部请求，同一卡片另一个进程看到 inflight 不会再次发送。
        request = (
            CreateMessageRequest.builder()
            .receive_id_type("chat_id")
            .request_body(
                CreateMessageRequestBody.builder()
                .receive_id(plan.chat_id)
                .msg_type("interactive")
                .content(json.dumps(build_probe_card(plan), ensure_ascii=False))
                .uuid(str(row["send_uuid"]))
                .build()
            )
            .build()
        )
        status = "unknown"
        message_id = row["message_id"]
        try:
            response = self.client.im.v1.message.create(request, self.option)
            http_status = getattr(getattr(response, "raw", None), "status_code", None)
            code = getattr(response, "code", None)
            data = getattr(response, "data", None)
            candidate = getattr(data, "message_id", None)
            if (
                type(http_status) is int
                and 200 <= http_status < 300
                and type(code) is int
                and code == 0
                and type(candidate) is str
                and candidate
                and getattr(data, "chat_id", None) == plan.chat_id
            ):
                status = "sent"
                message_id = candidate
        except Exception:
            status = "unknown"
        with repository.connections() as connection:
            connection.execute(
                "UPDATE feishu_probe.cards SET send_status=%s,message_id=%s WHERE id=%s",
                (status, message_id, UUID(plan.probe_id)),
            )
        return status
