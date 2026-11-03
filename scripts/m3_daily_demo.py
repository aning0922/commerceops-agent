"""一次性新owned空库的本地演示种子；只生成新合成数据/新凭据，不启动服务。"""

import argparse
import json
import re
from datetime import timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from commerceops.infrastructure.database import DatabaseSettings, connect


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", type=Path, required=True)
    args = parser.parse_args()
    try:
        settings = DatabaseSettings()
        if (
            not re.fullmatch(r"m3_daily_demo_[a-z0-9_]{1,40}", settings.name)
            or settings.runtime_password_file is None
        ):
            raise ValueError("NEW_OWNED_DATABASE_REQUIRED")
        directory = args.directory.resolve()
        if args.directory.exists() or not args.directory.is_absolute():
            raise ValueError("NEW_PRIVATE_DIRECTORY_REQUIRED")
        with connect(settings) as db:
            row = db.execute("SELECT count(*) AS n FROM business.organizations").fetchone()
            if row is None or row["n"] != 0:
                raise ValueError("EMPTY_OWNED_DATABASE_REQUIRED")
            clock = db.execute("SELECT clock_timestamp() AS time").fetchone()
            if clock is None:
                raise ValueError("CLOCK_UNAVAILABLE")
            timestamp = clock["time"]
        directory.mkdir(mode=0o700, parents=False)
        runtime = settings.model_copy(
            update={"user": "commerceops_app", "password_file": settings.runtime_password_file}
        )
        # 复用已受审的本地合成身份/会话及新数据构造器；不是平台登录或验收结论。
        from tests.p3_support import initialize_p3
        from tests.test_daily_pg import prepare

        fixture = initialize_p3(settings, runtime, directory)
        try:
            day = timestamp.astimezone(ZoneInfo("Asia/Taipei")).date() - timedelta(days=1)
            files, _ = prepare(fixture, directory / "daily", day)
            deployment = directory / "daily-deployment.json"
            deployment.write_text(files.model_dump_json())
            deployment.chmod(0o600)
            login = directory / "local-login.json"
            login.write_text(
                json.dumps(
                    {"login": fixture.login, "password": fixture.password.get_secret_value()}
                )
            )
            login.chmod(0o600)
            token = directory / "local-session"
            token.write_text(fixture.client.cookies.get("commerceops_session"))
            token.chmod(0o600)
            public = {
                "mode": "local_synthetic_only",
                "organization_id": str(fixture.actor.organization_id),
                "shop_id": str(fixture.inventory.data.shop),
                "business_day": day.isoformat(),
                "source_config_version": "source-1",
                "web_config": str(fixture.config_file),
                "daily_config": str(deployment),
                "model_requests_enabled": False,
                "external_sender_enabled": False,
            }
            (directory / "demo.json").write_text(json.dumps(public, indent=2) + "\n")
            (directory / "demo.json").chmod(0o600)
            print(json.dumps(public))
        finally:
            fixture.client.close()
    except Exception:
        raise SystemExit("本地日报种子失败；保留新owned资源供核实，不自动重试") from None


if __name__ == "__main__":
    main()
