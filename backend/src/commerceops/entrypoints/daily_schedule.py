"""显式owner连接+当前Web session的日报schedule/Fake destination配置CLI。"""

import argparse
from pathlib import Path
from uuid import UUID

from commerceops.adapters.commerce.woocommerce_config import read_private_file
from commerceops.application.daily.scheduling import ScheduleConfig
from commerceops.infrastructure.daily_schedules import configure_schedule, pause_schedule
from commerceops.infrastructure.daily_sources import DailyDeployment, checked_json
from commerceops.infrastructure.database import DatabaseSettings, connect
from commerceops.infrastructure.web_config import WebConfig
from commerceops.infrastructure.web_sessions import SessionStore, actor_guard, role_scope


def main() -> None:
    parser = argparse.ArgumentParser(description="仅新owned合成环境；不发送平台消息")
    parser.add_argument("--web-config", type=Path, required=True)
    parser.add_argument("--deployment", type=Path, required=True)
    parser.add_argument("--session-file", type=Path, required=True)
    parser.add_argument("--action", choices=("configure", "pause", "register-fake"), required=True)
    parser.add_argument("--schedule-file", type=Path)
    parser.add_argument("--schedule-id", type=UUID)
    parser.add_argument("--version", type=int)
    parser.add_argument("--destination-id", type=UUID)
    parser.add_argument("--shop-id", type=UUID)
    parser.add_argument("--enable", action="store_true")
    args = parser.parse_args()
    try:
        config = WebConfig.from_file(args.web_config)
        owner = DatabaseSettings()
        if any(getattr(owner, k) != getattr(config.database, k) for k in ("host", "port", "name")):
            raise ValueError("DAILY_OWNER_DATABASE_MISMATCH")
        files = DailyDeployment.load(args.deployment)
        token = read_private_file(str(args.session_file), 32768).decode().strip()
        actor = SessionStore(config).authenticate(token)
        if args.action == "configure":
            if args.schedule_file is None:
                raise ValueError
            raw = read_private_file(str(args.schedule_file), 32768)
            checked_json(raw)
            body = ScheduleConfig.model_validate_json(raw)
            identifier = configure_schedule(owner, files, actor, body, enabled=args.enable)
            print(f"daily schedule registered: {identifier}")
        elif args.action == "pause":
            if args.schedule_id is None or args.version is None:
                raise ValueError
            pause_schedule(owner, actor, args.schedule_id, args.version)
            print("daily schedule paused")
        else:
            if (
                args.destination_id is None
                or args.shop_id is None
                or args.version is None
                or args.version < 1
            ):
                raise ValueError
            with connect(owner) as db:
                row = db.execute(
                    """SELECT current_user=pg_get_userbyid(relowner) AS owner FROM pg_class
                    WHERE oid='business.p6_daily_destinations'::regclass"""
                ).fetchone()
                actor_guard(db, actor)
                if (
                    not row
                    or not row["owner"]
                    or not all(
                        role_scope(db, actor, args.shop_id, r) for r in ("operator", "admin")
                    )
                ):
                    raise ValueError
                db.execute(
                    """INSERT INTO business.p6_daily_destinations
                    (id,organization_id,shop_id,owner_id,binding_version,transport,enabled)
                VALUES(%s,%s,%s,%s,%s,'fake',%s)""",
                    (
                        args.destination_id,
                        actor.organization_id,
                        args.shop_id,
                        actor.principal_id,
                        args.version,
                        args.enable,
                    ),
                )
            print(f"daily Fake destination registered: {args.destination_id}")
    except Exception:
        # 不回显session/配置路径/原SQL或凭据值；所有运行必须由Root新owned窗口承载。
        raise SystemExit("日报配置失败，请核对同owned数据库、当前权限和显式参数") from None


if __name__ == "__main__":
    main()
