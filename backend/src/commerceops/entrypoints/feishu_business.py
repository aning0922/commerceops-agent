"""P4正式入口的配置核实命令；真实Gateway启动待Root审后受控窗口。"""

import argparse
import asyncio
import json
import os
import signal
import socket
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Literal
from uuid import UUID

from commerceops.adapters.feishu.business_config import verify_config

if TYPE_CHECKING:
    from commerceops.infrastructure.web_config import WebConfig


def run_gateway(
    config: Path, window_file: Path, *, web_config_sha256: str | None = None
) -> dict[str, object]:
    from commerceops.adapters.feishu.business_config import BusinessSettings
    from commerceops.adapters.feishu.business_factory import private_value
    from commerceops.adapters.feishu.sdk import restrict_sdk_logs
    from commerceops.application.feishu_business.gateway_window import GatewayWindow

    restrict_sdk_logs()
    if web_config_sha256 is not None and (
        type(web_config_sha256) is not str
        or len(web_config_sha256) != 64
        or any(c not in "0123456789abcdef" for c in web_config_sha256)
    ):
        raise PermissionError("P4_GATEWAY_WEB_BINDING_REQUIRED")
    settings = BusinessSettings.model_validate_json(private_value(config))
    window = GatewayWindow.model_validate_json(private_value(window_file))
    if not window.active() or (settings.organization_id, settings.shop_id) != (
        window.organization_id,
        window.shop_id,
    ):
        raise PermissionError("P4_GATEWAY_WINDOW_CLOSED")
    remaining = (window.expires_at - datetime.now(UTC)).total_seconds()
    if remaining <= 10:
        raise PermissionError("P4_GATEWAY_STOP_RESERVE_REQUIRED")
    cutoff = time.monotonic() + remaining
    process = subprocess.Popen(  # noqa: S603 - fixed executable/module, verified file args, no shell
        [
            sys.executable,
            "-m",
            "commerceops.entrypoints.feishu_gateway_child",
            "--config",
            str(config),
            "--window-file",
            str(window_file),
            *(["--web-config-sha256", web_config_sha256] if web_config_sha256 is not None else []),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    def stopped(signum: int, frame: object) -> None:
        raise KeyboardInterrupt

    previous = signal.signal(signal.SIGTERM, stopped)
    expired = False
    manual = False
    try:
        try:
            process.wait(timeout=max(0.01, cutoff - time.monotonic() - 10))
        except subprocess.TimeoutExpired:
            expired = True
        except KeyboardInterrupt:
            manual = True
    finally:
        if process.poll() is None:
            process.terminate()
        try:
            process.wait(timeout=max(0.01, min(5, cutoff - time.monotonic())))
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=max(0.01, min(5, cutoff - time.monotonic())))
        finally:
            signal.signal(signal.SIGTERM, previous)
    confirmed = False
    try:
        from commerceops.infrastructure.web_config import WebConfig

        async def bounded_confirmation() -> None:
            async with asyncio.timeout(max(0.01, min(5, cutoff - time.monotonic()))):
                await confirm_gateway_child(
                    WebConfig.from_file(settings.web_config_file)
                    if web_config_sha256 is None
                    else WebConfig.from_file(
                        settings.web_config_file, expected_sha256=web_config_sha256
                    ),
                    window.organization_id,
                    window.window_id,
                    process.pid,
                    process.returncode,
                )

        asyncio.run(bounded_confirmation())
        confirmed = True
    except Exception:
        confirmed = False
    return {
        "result": "window_stopped"
        if expired
        else "manual_stopped"
        if manual
        else "child_exited"
        if process.returncode == 0
        else "failed",
        "child_exit": process.returncode,
        "child_reaped": process.poll() is not None,
        "lifecycle_termination_confirmed": confirmed,
        "sdk_start_intent": 1,
        "ws_endpoint_discovery": "not_verified",
        "ws_handshake": "not_verified",
        "ws_received_frames": "not_verified",
        "ws_ack_frames": "not_verified",
        "external_sender_enabled": False,
        "phase4_gate_passed": False,
    }


async def confirm_gateway_child(
    config: "WebConfig", organization: UUID, window_id: UUID, pid: int, child_exit: int
) -> None:
    """原parent wait/reap后复核同namespace原started，持久真实终止回执。"""
    from uuid import uuid4

    from psycopg.types.json import Jsonb

    from commerceops.infrastructure.worker_lock import (
        TerminationRequired,
        open_async,
        process_namespace,
        require_process_absent,
    )

    expected = {"pid": pid, "host": socket.gethostname(), "pid_namespace": process_namespace()}
    if type(child_exit) is not int:
        raise TerminationRequired("original child exit required")
    async with await open_async(config.database) as db, db.transaction():
        cursor = await db.execute(
            """SELECT after_state FROM business.audit_events WHERE organization_id=%s
            AND source='feishu_gateway' AND action='started' AND entity_type='gateway_runtime'
            AND entity_id=%s""",
            (organization, str(window_id)),
        )
        rows = await cursor.fetchall()
        if len(rows) != 1 or rows[0]["after_state"] != expected:
            raise TerminationRequired("original unique Gateway process receipt required")
        require_process_absent(expected)
        await db.execute(
            """INSERT INTO business.audit_events(id,organization_id,source,action,
            entity_type,entity_id,after_state,trace_id) VALUES(%s,%s,'feishu_gateway',
            'termination_confirmed','gateway_runtime',%s,%s,%s)""",
            (
                uuid4(),
                organization,
                str(window_id),
                Jsonb({"process": expected, "child_exit": child_exit, "child_reaped": True}),
                window_id,
            ),
        )


async def confirm_worker_child(config: "WebConfig", organization: UUID, pid: int) -> None:
    from psycopg.types.json import Jsonb

    from commerceops.infrastructure.web_config import WebConfig
    from commerceops.infrastructure.worker_lock import (
        TerminationRequired,
        confirm_termination,
        open_async,
        process_namespace,
        require_process_absent,
    )

    if not isinstance(config, WebConfig):
        raise ValueError("P4_CONTROLLED_CONFIGURATION_REQUIRED")
    expected = {"pid": pid, "host": socket.gethostname(), "pid_namespace": process_namespace()}
    async with await open_async(config.database) as db:
        cursor = await db.execute(
            """SELECT s.entity_id,s.after_state AS started,e.after_state AS stopped
            FROM business.audit_events s LEFT JOIN business.audit_events e
            ON e.organization_id=s.organization_id AND e.entity_id=s.entity_id
            AND e.source='worker' AND e.entity_type='worker_runtime' AND e.action='stopped'
            WHERE s.organization_id=%s AND s.source='worker'
            AND s.entity_type='worker_runtime' AND s.action='started'
            AND s.after_state=%s""",
            (organization, Jsonb(expected)),
        )
        rows = await cursor.fetchall()
    if len(rows) != 1 or rows[0]["started"] != expected or rows[0]["stopped"] != expected:
        raise TerminationRequired("original full started/stopped receipt required")
    require_process_absent(expected)
    await confirm_termination(
        config.database,
        rows[0]["entity_id"],
        "controlled Feishu Worker child stopped and OS reaped",
    )


def run_worker(
    config: Path, window_file: Path, *, mode: Literal["workflow", "f02_clarification"] = "workflow"
) -> dict[str, object]:
    from commerceops.adapters.feishu.business_config import BusinessSettings
    from commerceops.adapters.feishu.business_factory import private_value
    from commerceops.adapters.feishu.sdk import restrict_sdk_logs
    from commerceops.application.feishu_business.f02_window import F02WorkerWindow
    from commerceops.application.feishu_business.worker_window import ControlledWorkerWindow
    from commerceops.infrastructure.web_config import WebConfig

    restrict_sdk_logs()
    if os.environ.get("COMMERCEOPS_MODE") != "p4-controlled-test":
        raise PermissionError("P4_CONTROLLED_TEST_MODE_REQUIRED")
    settings = BusinessSettings.model_validate_json(private_value(config))
    if mode not in ("workflow", "f02_clarification"):
        raise PermissionError("P4_CONTROLLED_WORKER_MODE_REQUIRED")
    window_type = F02WorkerWindow if mode == "f02_clarification" else ControlledWorkerWindow
    window = window_type.model_validate_json(private_value(window_file))
    window.window(settings)
    web = WebConfig.from_file(settings.web_config_file)
    if web.database.user != "commerceops_app":
        raise PermissionError("P4_CONTROLLED_RUNTIME_ROLE_REQUIRED")
    deadline = time.monotonic() + (window.expires_at - datetime.now(UTC)).total_seconds()
    child = subprocess.Popen(  # noqa: S603 - fixed module, verified files, no shell
        [
            sys.executable,
            "-m",
            "commerceops.entrypoints.feishu_worker_child",
            "--live",
            "--config",
            str(config),
            "--window-file",
            str(window_file),
            *(["--mode", mode] if mode != "workflow" else []),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )

    def interrupted(signum: int, frame: object) -> None:
        raise KeyboardInterrupt

    previous = signal.signal(signal.SIGTERM, interrupted)
    forced = False
    try:
        try:
            output, _ = child.communicate(timeout=max(0.01, deadline - time.monotonic() - 15))
        except (subprocess.TimeoutExpired, KeyboardInterrupt):
            forced = True
            child.terminate()
            try:
                output, _ = child.communicate(
                    timeout=max(0.01, min(5, deadline - time.monotonic()))
                )
            except subprocess.TimeoutExpired:
                child.kill()
                output, _ = child.communicate(
                    timeout=max(0.01, min(5, deadline - time.monotonic()))
                )
    finally:
        if child.poll() is None:
            child.terminate()
            try:
                child.wait(timeout=max(0.01, min(5, deadline - time.monotonic())))
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait(timeout=max(0.01, min(5, deadline - time.monotonic())))
        signal.signal(signal.SIGTERM, previous)
    summary: dict[str, object] = {}
    for line in output.splitlines():
        try:
            row = json.loads(line)
        except (ValueError, UnicodeError):
            continue
        if type(row) is dict and row.get("verification_mode") == "controlled_sdk":
            summary = row
    confirmed = False
    try:

        async def bounded_confirmation() -> None:
            async with asyncio.timeout(max(0.01, min(5, deadline - time.monotonic()))):
                await confirm_worker_child(web, window.organization_id, child.pid)

        asyncio.run(bounded_confirmation())
        confirmed = True
    except Exception:
        confirmed = False  # 缺原真实完整pair/OS证明时不替代人工终止合同。
    return {
        "result": "window_stopped"
        if child.returncode == 0 and confirmed and summary.get("result") == "window_stopped"
        else "failed",
        "child_exit": child.returncode,
        "child_reaped": child.poll() is not None,
        "forced_stop": forced,
        "lifecycle_termination_confirmed": confirmed,
        "official_summary": summary,
        "phase4_gate_passed": False,
    }


async def run_preflight(config: Path, window_file: Path) -> dict[str, object]:
    from commerceops.adapters.feishu.business_config import BusinessSettings
    from commerceops.adapters.feishu.business_factory import BusinessSDKFactory, private_value
    from commerceops.adapters.feishu.business_preflight import preflight
    from commerceops.application.feishu_business.preflight_window import PreflightWindow
    from commerceops.infrastructure.feishu_sdk_ledger import PersistentSDKLedger
    from commerceops.infrastructure.web_config import WebConfig
    from commerceops.infrastructure.worker_lock import WorkerSession, open_async

    settings = BusinessSettings.model_validate_json(private_value(config))
    window = PreflightWindow.model_validate_json(private_value(window_file)).window()
    if not window.enabled or (settings.organization_id, settings.shop_id) != (
        window.organization_id,
        window.shop_id,
    ):
        raise PermissionError("P4_PREFLIGHT_WINDOW_CLOSED")
    web = WebConfig.from_file(settings.web_config_file)
    if web.database.user != "commerceops_app":
        raise PermissionError("P4_PREFLIGHT_RUNTIME_ROLE_REQUIRED")
    session = WorkerSession(web.database, settings.organization_id)
    summary: dict[str, object] = {"result": "failed", "method_counts": "not_verified"}
    try:
        async with asyncio.timeout((window.expires_at - datetime.now(UTC)).total_seconds()):
            await session.start()
            ledger = PersistentSDKLedger(session, window)
            summary.update(await preflight(BusinessSDKFactory(settings, ledger)))
            summary["result"] = "schema_verified"
    except Exception as error:
        # 不打印exception message/args/SDK raw，方法已started仍保消耗，不重试。
        summary["failure_category"] = type(error).__name__
    finally:
        async with asyncio.timeout(20):
            try:
                async with await open_async(web.database) as db:
                    cursor = await db.execute(
                        """SELECT method,status,count(*) AS n FROM business.p4_sdk_calls
                        WHERE window_id=%s GROUP BY method,status ORDER BY method,status""",
                        (window.window_id,),
                    )
                    summary["method_counts"] = await cursor.fetchall()
            except Exception:
                summary["method_counts"] = "not_verified"
            finally:
                await session.close(clean=True)
    summary["worker_stopped"] = True
    summary["external_sender_enabled"] = False
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Formal Feishu business configuration")
    parser.add_argument("action", choices=["verify-config", "preflight", "gateway", "worker"])
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--window-file", type=Path)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--web-config-sha256")
    parser.add_argument(
        "--worker-mode", choices=("workflow", "f02_clarification"), default="workflow"
    )
    args = parser.parse_args()
    try:
        if args.web_config_sha256 is not None and args.action != "gateway":
            raise PermissionError("P4_GATEWAY_WEB_BINDING_REQUIRED")
        if args.worker_mode != "workflow" and args.action != "worker":
            raise PermissionError("P4_CONTROLLED_WORKER_MODE_REQUIRED")
        if args.action == "verify-config":
            result: dict[str, object] = dict(verify_config(args.config))
        else:
            if not args.live or args.window_file is None:
                raise PermissionError("P4_EXPLICIT_PREFLIGHT_REQUIRED")
            if args.action == "gateway":
                result = (
                    run_gateway(args.config, args.window_file)
                    if args.web_config_sha256 is None
                    else run_gateway(
                        args.config, args.window_file, web_config_sha256=args.web_config_sha256
                    )
                )
            elif args.action == "worker":
                result = (
                    run_worker(args.config, args.window_file)
                    if args.worker_mode == "workflow"
                    else run_worker(args.config, args.window_file, mode=args.worker_mode)
                )
            else:
                result = asyncio.run(run_preflight(args.config, args.window_file))
        print(json.dumps(result, sort_keys=True))
        if result.get("result") == "failed":
            raise SystemExit(1)
    except Exception:
        raise SystemExit("P4_CONFIGURATION_INVALID") from None


if __name__ == "__main__":
    main()
