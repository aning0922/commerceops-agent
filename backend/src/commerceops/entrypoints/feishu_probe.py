"""显式技术探针命令；默认配置检查，不启动网络/真实审批。"""

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import lark_oapi as lark  # type: ignore[import-untyped]
from lark_oapi.core.enum import AccessTokenType, HttpMethod  # type: ignore[import-untyped]

from commerceops.adapters.feishu.base import BaseProbe, RecordSDK
from commerceops.adapters.feishu.cards import build_probe_card
from commerceops.adapters.feishu.config import FeishuProbeSettings, runtime_pool
from commerceops.adapters.feishu.contracts import ProbePlan, decode_payload
from commerceops.adapters.feishu.probe_schema import setup_probe_schema
from commerceops.adapters.feishu.repository import ProbeRepository
from commerceops.adapters.feishu.sdk import ProbeGateway, restrict_sdk_logs
from commerceops.adapters.feishu.send import CardSender
from commerceops.infrastructure.database import DatabaseSettings, connect
from commerceops.infrastructure.repository import TaskScope


def load_plan(path: Path) -> ProbePlan:
    body = decode_payload(path.read_bytes())
    body["required_assumption_keys"] = tuple(body["required_assumption_keys"])
    body["expires_at"] = datetime.fromisoformat(body["expires_at"])
    return ProbePlan(**body)


def live_client(settings: FeishuProbeSettings) -> Any:
    restrict_sdk_logs()
    client = (
        lark.Client.builder()
        .app_id(settings.app_id)
        .app_secret(settings.secret().get_secret_value())
        .timeout(2.0)
        .build()
    )
    # 出站探针开始前验证机器人真实应用身份；只读 API，失败不继续。
    request = (
        lark.BaseRequest.builder()
        .http_method(HttpMethod.GET)
        .uri("/open-apis/bot/v3/info")
        .token_types({AccessTokenType.TENANT})
        .build()
    )
    response = client.request(request)
    raw = response.raw
    if (
        raw is None
        or raw.status_code != 200
        or type(response.code) is not int
        or response.code != 0
    ):
        raise ValueError("bot identity unavailable")
    body = json.loads(raw.content)
    if body.get("bot", {}).get("open_id") != settings.bot_open_id:
        raise ValueError("bot identity mismatch")
    return client


def main() -> None:
    parser = argparse.ArgumentParser(description="Feishu isolated technical probe")
    parser.add_argument(
        "action",
        choices=[
            "verify-config",
            "setup-schema",
            "emit-card",
            "register-card",
            "send-card",
            "gateway",
            "base-create",
            "base-reconcile",
            "base-update",
        ],
        default="verify-config",
        nargs="?",
    )
    parser.add_argument("--plan-file", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--base-fields-file", type=Path)
    parser.add_argument("--probe-id", type=UUID)
    parser.add_argument("--state")
    parser.add_argument("--updated-at")
    parser.add_argument("--retry-known-rejection", action="store_true")
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    restrict_sdk_logs()
    try:
        if args.action == "emit-card":
            if args.plan_file is None or args.output is None:
                raise ValueError("plan/output required")
            target = args.output.resolve()
            if not target.is_relative_to((Path.cwd() / "runtime").resolve()):
                raise ValueError("card artifact must stay in ignored runtime")
            card = build_probe_card(load_plan(args.plan_file))
            target.parent.mkdir(parents=True, exist_ok=True)
            descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "w") as output:
                output.write(json.dumps(card, ensure_ascii=False, indent=2))
            print("probe card artifact written; simulated approval only")
            return
        db = DatabaseSettings()
        if args.action == "setup-schema":
            setup_probe_schema(db)
            print("technical probe schema ready; no business migration")
            return
        settings = FeishuProbeSettings()
        policy = settings.policy()
        if db.user != "commerceops_app":
            raise ValueError("restricted role required")
        if args.action == "verify-config":
            print("probe configuration valid; G3 blocked_external until live evidence")
            return
        scope = TaskScope(settings.organization_id, settings.shop_id)
        repository = ProbeRepository(lambda: connect(db), scope, policy)
        if args.action == "register-card":
            if args.plan_file is None:
                raise ValueError("plan required")
            repository.register_card(load_plan(args.plan_file))
            print("technical card contract registered; no platform write")
            return
        if not args.live or not settings.external_ready:
            raise SystemExit(
                "blocked_external: explicit live execution and dedicated resources required"
            )
        client = live_client(settings)
        if args.action == "send-card":
            if args.plan_file is None:
                raise ValueError("plan required")
            plan = load_plan(args.plan_file)
            with connect(db) as connection:
                exists = connection.execute(
                    "SELECT 1 FROM feishu_probe.cards WHERE id=%s", (UUID(plan.probe_id),)
                ).fetchone()
            if exists is None:
                repository.register_card(plan, outbound=True)
            print("technical card send: " + CardSender(repository, client).send_once(plan))
        elif args.action == "gateway":
            pool = runtime_pool(db)
            try:
                gateway = ProbeGateway(ProbeRepository(pool.connection, scope, policy))
                websocket = lark.ws.Client(
                    settings.app_id,
                    settings.secret().get_secret_value(),
                    event_handler=gateway.dispatcher(),
                )
                restrict_sdk_logs()
                websocket.start()
            finally:
                pool.close()
        else:
            if (
                settings.base_app_token is None
                or settings.base_table_id is None
                or args.probe_id is None
            ):
                raise ValueError("dedicated Base/probe required")
            probe = BaseProbe(
                lambda: connect(db),
                scope,
                RecordSDK(client),
                target=(settings.base_app_token, settings.base_table_id),
            )
            if args.action == "base-create":
                if args.base_fields_file is None:
                    raise ValueError("probe fields required")
                fields = decode_payload(args.base_fields_file.read_bytes())
                probe.prepare(
                    args.probe_id, settings.base_app_token, settings.base_table_id, fields
                )
                result = probe.create_once(
                    args.probe_id, retry_known_rejection=args.retry_known_rejection
                )
            elif args.action == "base-reconcile":
                result = probe.reconcile(args.probe_id, verify_succeeded=True)
            else:
                if args.state is None or args.updated_at is None:
                    raise ValueError("update fields required")
                result = probe.update_once(
                    args.probe_id, state=args.state, updated_at=args.updated_at
                )
            print("technical Base operation: " + result)
    except SystemExit:
        raise
    except Exception:
        raise SystemExit(
            "feishu probe failed; inspect configuration/technical records safely"
        ) from None


if __name__ == "__main__":
    main()
