"""薄M1离线装配：原API/唯一Worker/原Factory；不是平台或生产入口。"""

import argparse
import asyncio
import json
import multiprocessing
import os
import signal
import socket
import time
from datetime import UTC, datetime
from multiprocessing.connection import Connection
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID

import uvicorn
from commerceops.application.feishu_business.contracts import ProjectionRequest, ProjectionResult
from commerceops.application.feishu_business.delivery import DeliveryGate
from commerceops.entrypoints.api import create_app
from commerceops.infrastructure.database import DatabaseSettings, connect
from commerceops.infrastructure.explanation_repository import ExplanationStore
from commerceops.infrastructure.feishu_base_delivery import BaseDeliveryStore
from commerceops.infrastructure.intent_repository import IntentStore
from commerceops.infrastructure.inventory_repository import InventoryStore
from commerceops.infrastructure.replenishment_repository import ApprovalStore, ReplenishmentStore
from commerceops.infrastructure.web_config import WebConfig, private_bytes
from commerceops.infrastructure.worker import UnsafeShutdown, Worker
from commerceops.infrastructure.worker_lock import (
    TerminationRequired,
    WorkerSession,
    confirm_termination,
    open_async,
    process_namespace,
    require_process_absent,
)
from commerceops.workflows.inventory_analysis import InventoryRunner
from commerceops.workflows.inventory_routing import IntentRunner
from commerceops.workflows.replenishment import ApprovalRunner
from commerceops.workflows.report_explanation import (
    ExplanationRunner,
    InventoryCompositeRunner,
    ProviderFactory,
)

from scripts.prepare_pg import prepare
from tests.inventory_support import DIRECTORY
from tests.p3_support import initialize_p3
from tests.p4_demo_factory import M1DemoFactory


def save(path: Path, value: dict[str, Any]) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "w") as stream:
        json.dump(value, stream)


def request(directory: Path) -> dict[str, Any]:
    value: dict[str, Any] = json.loads(private_bytes(directory / "demo-request.json"))
    if (
        os.environ.get("COMMERCEOPS_MODE") != "m1-offline-demo"
        or value["project"] != os.environ.get("COMMERCEOPS_DEMO_PROJECT")
        or value["source_mode"] != "mock"
        or value["external_sender_enabled"] is not False
        or value["provider_enabled"] is not False
    ):
        raise ValueError("M1_OFFLINE_SCOPE_INVALID")
    expires = datetime.fromisoformat(value["expires_at"])
    if expires.utcoffset() is None or datetime.now(UTC) >= expires:
        raise ValueError("M1_OFFLINE_WINDOW_CLOSED")
    for origin in (value["web_origin"], value["api_origin"]):
        parsed = urlsplit(origin)
        if (
            parsed.scheme != "http"
            or parsed.hostname != "127.0.0.1"
            or parsed.port is None
            or parsed.username
            or parsed.password
            or parsed.path
            or parsed.query
            or parsed.fragment
            or origin != f"http://127.0.0.1:{parsed.port}"
        ):
            raise ValueError("M1_OFFLINE_ORIGIN_INVALID")
    return value


def seed(directory: Path) -> None:
    value = request(directory)
    if (directory / "demo-facts.json").exists():
        # 既有seed不换身份、密钥或业务UUID；重启只读取原私有配置。
        raise ValueError("M1_OFFLINE_ALREADY_SEEDED")
    owner = DatabaseSettings()
    if (owner.user, owner.host, owner.name, owner.port, owner.password_file) != (
        "commerceops_owner",
        "postgres",
        "commerceops",
        5432,
        Path("/run/secrets/owner_password"),
    ):
        raise ValueError("M1_OFFLINE_OWNED_DATABASE_REQUIRED")
    if owner.runtime_password_file != Path("/run/secrets/app_password"):
        raise ValueError("M1_OFFLINE_RUNTIME_SECRET_REQUIRED")
    with connect(owner) as db:
        if db.execute("SELECT count(*) AS n FROM business.organizations").fetchone() != {"n": 0}:
            raise ValueError("M1_OFFLINE_FRESH_DATABASE_REQUIRED")
    app = owner.model_copy(
        update={"user": "commerceops_app", "password_file": owner.runtime_password_file}
    )
    fixture = initialize_p3(owner, app, directory)
    fixture.client.close()
    configuration = json.loads(private_bytes(fixture.config_file))
    configuration["origins"] = [value["web_origin"]]
    configuration["recovery_scan_seconds"] = 1
    # initialize_p3写的本次自有配置，在启动API/Worker前原地替换公开origin。
    descriptor = os.open(fixture.config_file, os.O_WRONLY | os.O_TRUNC | os.O_NOFOLLOW)
    with os.fdopen(descriptor, "w") as stream:
        json.dump(configuration, stream)
    save(
        directory / "demo-facts.json",
        {
            "organization": str(fixture.actor.organization_id),
            "shop": str(fixture.inventory.data.shop),
            "source_mode": "mock",
            "approval_mode": "simulated_web",
            "model_mode": "not_used",
            "platform_calls": 0,
            "provider_calls": 0,
            "external_sender_enabled": False,
        },
    )
    save(
        directory / "demo-account.json",
        {"login": fixture.login, "password": fixture.password.get_secret_value()},
    )
    print("M1 owned synthetic account prepared; private values withheld", flush=True)


class OfflineProjection:
    """只为演示标offline_fake：合成全字段回执，不代表任何远端读取或写入。"""

    async def project(self, value: ProjectionRequest) -> ProjectionResult:
        return ProjectionResult(
            outcome="verified",
            code="OFFLINE_DEMO_FAKE",
            complete=True,
            matched_count=1,
            content_matches=True,
            observed_fields=value.projection.fields(),
            observed_version=value.projection.sync_version,
            external_id=value.external_id or "synthetic-" + value.projection.item_id.hex,
        )


def owned_config(directory: Path, value: dict[str, Any]) -> WebConfig:
    config = WebConfig.from_file(directory / "configuration.json")
    database = config.database
    if (
        (database.host, database.name, database.port, database.user, database.password_file)
        != ("postgres", "commerceops", 5432, "commerceops_app", Path("/run/secrets/app_password"))
        or config.origins != (value["web_origin"],)
        or config.transport_mode != "local_http"
    ):
        raise ValueError("M1_OFFLINE_CONFIGURATION_SCOPE_INVALID")
    return config


async def work(directory: Path, started: Connection | None = None) -> None:
    value = request(directory)
    config = owned_config(directory, value)
    facts = json.loads(private_bytes(directory / "demo-facts.json"))
    organization, shop = UUID(facts["organization"]), UUID(facts["shop"])
    session = WorkerSession(config.database, organization)
    await session.start()
    if started is not None:
        started.send(
            {
                "owner": session.owner,
                "pid": os.getpid(),
                "organization": str(organization),
                "host": socket.gethostname(),
                "pid_namespace": process_namespace(),
            }
        )
        started.close()
    factory, provider = M1DemoFactory(), ProviderFactory()
    approval = ApprovalRunner(ApprovalStore(config, session), collector_factory=factory)
    stop = asyncio.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        asyncio.get_running_loop().add_signal_handler(sig, stop.set)
    expiry = datetime.fromisoformat(value["expires_at"])
    runner = InventoryCompositeRunner(
        InventoryRunner(InventoryStore(config.database, session), factory),
        ExplanationRunner(ExplanationStore(config.database, session), provider),
        IntentRunner(IntentStore(config.database, session), provider),
        approval,
    )

    async def maintenance() -> None:
        await approval.reconcile()
        if datetime.now(UTC) >= expiry:
            stop.set()
            return
        async with await open_async(config.database) as db:
            cursor = await db.execute(
                """SELECT id FROM business.business_tasks
                WHERE organization_id=%s AND shop_id=%s AND kind='inventory_replenishment'
                AND workflow_version='p3-inventory-replenishment-v1'
                ORDER BY created_at,id LIMIT 6""",
                (organization, shop),
            )
            tasks = await cursor.fetchall()
        # 仍保原5task gate，不扩大真实adapter合同；超过5仅停止Fake projection。
        if 0 < len(tasks) <= 5:
            gate = DeliveryGate(
                organization,
                shop,
                frozenset(r["id"] for r in tasks),
                "m1-offline-demo",
                expiry,
                enabled=True,
                verification_mode="offline_fake",
            )
            await BaseDeliveryStore(session, OfflineProjection(), gate).reconcile()

    try:
        await Worker(
            session,
            runner,
            reconcile=maintenance,
            recovery_scan_seconds=config.recovery_scan_seconds,
        ).run(stop)
    except UnsafeShutdown:
        os._exit(75)  # 原Worker安全退出合同，不由asyncio清理猜未知线程已停。


def child(directory: Path, started: Connection | None = None) -> None:
    try:
        asyncio.run(work(directory, started))
    except Exception as error:
        print(
            json.dumps({"stage": "m1_owned_worker", "category": type(error).__name__}), flush=True
        )
        raise SystemExit(2) from None


async def finish_child(
    directory: Path,
    value: dict[str, Any],
    expected_pid: int | None,
    exitcode: int | None,
    reaped: bool,
    receipt: dict[str, Any],
) -> None:
    # 只在原父容器namespace仍有效且这个明确child已join/reap/exit0时结案。
    if not reaped or exitcode != 0 or type(expected_pid) is not int or expected_pid <= 0:
        raise TerminationRequired("M1_OWN_CHILD_NOT_CLEANLY_REAPED")
    facts = json.loads(private_bytes(directory / "demo-facts.json"))
    if (
        set(receipt) != {"owner", "pid", "organization", "host", "pid_namespace"}
        or receipt["pid"] != expected_pid
        or receipt["organization"] != facts["organization"]
        or receipt["host"] != socket.gethostname()
        or receipt["pid_namespace"] != process_namespace()
    ):
        raise TerminationRequired("M1_OWN_CHILD_RECEIPT_MISMATCH")
    try:
        owner = str(UUID(receipt["owner"]))
    except (ValueError, TypeError, AttributeError):
        raise TerminationRequired("M1_OWN_CHILD_OWNER_INVALID") from None
    process = {key: receipt[key] for key in ("pid", "host", "pid_namespace")}
    require_process_absent(process)  # 活PID/PID复用不以exitcode或session锁释放替代。
    config = owned_config(directory, value)
    async with await open_async(config.database) as db:
        cursor = await db.execute(
            """SELECT s.after_state FROM business.audit_events s
            WHERE s.organization_id=%s AND s.source='worker' AND s.entity_type='worker_runtime'
            AND s.entity_id=%s AND s.action='started' AND EXISTS(
            SELECT 1 FROM business.audit_events e WHERE e.organization_id=s.organization_id
            AND e.source='worker' AND e.entity_type=s.entity_type
            AND e.entity_id=s.entity_id AND e.action='stopped')""",
            (UUID(facts["organization"]), owner),
        )
        rows = await cursor.fetchall()
    if len(rows) != 1 or rows[0]["after_state"] != process:
        raise TerminationRequired("M1_OWN_CHILD_PERSISTENT_RECEIPT_MISMATCH")
    await confirm_termination(config.database, owner, "M1 original child clean stop and OS reap")


def supervise(directory: Path) -> None:
    value = request(directory)
    stopped, restart = False, False

    def stop_handler(signum: int, frame: Any) -> None:
        nonlocal stopped
        stopped = True

    def restart_handler(signum: int, frame: Any) -> None:
        nonlocal restart
        restart = True

    signal.signal(signal.SIGTERM, stop_handler)
    signal.signal(signal.SIGINT, stop_handler)
    signal.signal(signal.SIGUSR1, restart_handler)
    ctx = multiprocessing.get_context("spawn")
    while not stopped:
        received, sent = ctx.Pipe(duplex=False)
        process = ctx.Process(target=child, args=(directory, sent))
        process.start()
        sent.close()
        while process.is_alive() and not stopped and not restart:
            if datetime.now(UTC) >= datetime.fromisoformat(value["expires_at"]):
                stopped = True
                break
            time.sleep(0.1)
        if process.is_alive():
            process.terminate()
        process.join(timeout=20)
        if process.is_alive():
            os._exit(75)
        if process.exitcode != 0:
            received.close()
            raise SystemExit(2)
        try:
            if not received.poll(1):
                raise TerminationRequired("M1_OWN_CHILD_START_RECEIPT_MISSING")
            receipt = received.recv()
            asyncio.run(
                asyncio.wait_for(
                    finish_child(directory, value, process.pid, process.exitcode, True, receipt),
                    timeout=5,
                )
            )
        finally:
            received.close()
        if not restart:
            return
        # 原child已经join/reap，下一唯一Worker仍由原同namespace OS证明决定恢复。
        restart = False


def main() -> None:
    parser = argparse.ArgumentParser(description="M1 owned offline Compose assembly")
    parser.add_argument("action", choices=["prepare", "seed", "api", "worker"])
    parser.add_argument("--directory", required=True, type=Path)
    parser.add_argument("--project")
    parser.add_argument("--web-port", type=int)
    parser.add_argument("--api-port", type=int)
    parser.add_argument("--expires-at")
    args = parser.parse_args()
    try:
        if args.action == "prepare":
            if not args.project or not args.project.startswith("m1off-") or not args.expires_at:
                raise ValueError("M1_EXPLICIT_OWNED_PROJECT_REQUIRED")
            expiry = datetime.fromisoformat(args.expires_at)
            if (
                expiry.utcoffset() is None
                or not 75 < (expiry - datetime.now(UTC)).total_seconds() <= 1800
            ):
                raise ValueError("M1_FIXED_WINDOW_REQUIRED")
            if (
                any(
                    type(port) is not int or not 1024 <= port <= 65535
                    for port in (args.web_port, args.api_port)
                )
                or args.web_port == args.api_port
            ):
                raise ValueError("M1_LOOPBACK_PORTS_REQUIRED")
            prepare(args.directory)
            save(
                args.directory / "demo-request.json",
                {
                    "project": args.project,
                    "expires_at": expiry.isoformat(),
                    "web_origin": f"http://127.0.0.1:{args.web_port}",
                    "api_origin": f"http://127.0.0.1:{args.api_port}",
                    "source_mode": "mock",
                    "external_sender_enabled": False,
                    "provider_enabled": False,
                },
            )
            print("M1 owned offline request prepared; no services started")
        elif args.action == "seed":
            seed(args.directory)
        elif args.action == "worker":
            supervise(args.directory)
        else:
            value = request(args.directory)
            config = owned_config(args.directory, value)
            app = create_app(
                web_config=config, replenishment_store=ReplenishmentStore(config, DIRECTORY)
            )
            # 仅Docker内私有网络监听；overlay严格将主机端口发布到127.0.0.1。
            uvicorn.run(app, host="0.0.0.0", port=8000, proxy_headers=False, access_log=False)  # noqa: S104
    except Exception as error:
        raise SystemExit(f"M1 owned offline assembly failed: {type(error).__name__}") from None


if __name__ == "__main__":
    main()
