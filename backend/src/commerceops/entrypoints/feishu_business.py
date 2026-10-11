"""P4正式入口的配置核实命令；真实Gateway启动待Root审后受控窗口。"""

import argparse
import asyncio
import json
import signal
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from commerceops.adapters.feishu.business_config import verify_config


def run_gateway(config: Path, window_file: Path) -> dict[str, object]:
    from commerceops.adapters.feishu.business_config import BusinessSettings
    from commerceops.adapters.feishu.business_factory import private_value
    from commerceops.adapters.feishu.sdk import restrict_sdk_logs
    from commerceops.application.feishu_business.gateway_window import GatewayWindow

    restrict_sdk_logs()
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
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    def stopped(signum: int, frame: object) -> None:
        raise KeyboardInterrupt

    previous = signal.signal(signal.SIGTERM, stopped)
    expired = False
    try:
        try:
            process.wait(timeout=max(0.01, cutoff - time.monotonic() - 10))
        except subprocess.TimeoutExpired:
            expired = True
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
    return {
        "result": "window_stopped"
        if expired
        else "child_exited"
        if process.returncode == 0
        else "failed",
        "child_exit": process.returncode,
        "child_reaped": process.poll() is not None,
        "sdk_start_intent": 1,
        "ws_endpoint_discovery": "not_verified",
        "ws_handshake": "not_verified",
        "ws_received_frames": "not_verified",
        "ws_ack_frames": "not_verified",
        "external_sender_enabled": False,
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
    parser.add_argument("action", choices=["verify-config", "preflight", "gateway"])
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--window-file", type=Path)
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    try:
        if args.action == "verify-config":
            result: dict[str, object] = dict(verify_config(args.config))
        else:
            if not args.live or args.window_file is None:
                raise PermissionError("P4_EXPLICIT_PREFLIGHT_REQUIRED")
            result = (
                run_gateway(args.config, args.window_file)
                if args.action == "gateway"
                else asyncio.run(run_preflight(args.config, args.window_file))
            )
        print(json.dumps(result, sort_keys=True))
        if result.get("result") == "failed":
            raise SystemExit(1)
    except Exception:
        raise SystemExit("P4_CONFIGURATION_INVALID") from None


if __name__ == "__main__":
    main()
