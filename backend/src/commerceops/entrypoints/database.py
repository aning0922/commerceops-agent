"""一次性初始化/版本查询命令；失败仅报告类别，不输出 SQL/参数/DSN。"""

import argparse
import asyncio
from pathlib import Path
from typing import Literal

from alembic import command
from alembic.config import Config
from psycopg import sql

from commerceops.infrastructure.checkpoint import checkpointer
from commerceops.infrastructure.database import DatabaseSettings, connect, migration_engine

MIGRATIONS = Path("backend/migrations")
RUNTIME_ROLE = "commerceops_app"


def migrate(settings: DatabaseSettings, *, migrations: Path = MIGRATIONS) -> None:
    config = Config()
    config.set_main_option("script_location", str(migrations))
    engine = migration_engine(settings)
    try:
        with engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
    finally:
        engine.dispose()


async def setup_checkpointer(settings: DatabaseSettings) -> None:
    with connect(settings) as connection:
        connection.execute("CREATE SCHEMA IF NOT EXISTS checkpoints")
    async with checkpointer(settings) as saver:
        await saver.setup()


def grant_runtime(
    settings: DatabaseSettings, *, legacy_revision: Literal["0015", "0016"] | None = None
) -> None:
    if legacy_revision not in (None, "0015", "0016"):
        raise ValueError("unsupported runtime bootstrap revision")
    if settings.runtime_password_file is None:
        raise ValueError("runtime password file required")
    secret = settings.runtime_password_file.read_text().strip()
    if not secret:
        raise ValueError("empty runtime password")
    with connect(settings) as connection:
        if legacy_revision is not None:
            row = connection.execute("SELECT version_num FROM business.alembic_version").fetchone()
            if row != {
                "version_num": "0015_p4_read_replies"
                if legacy_revision == "0015"
                else "0016_p4_clarification_requests"
            }:
                raise ValueError("runtime bootstrap revision mismatch")
        existing = connection.execute(
            "SELECT 1 FROM pg_roles WHERE rolname = %s", (RUNTIME_ROLE,)
        ).fetchone()
        verb = "ALTER" if existing else "CREATE"
        connection.execute(
            sql.SQL("{} ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD {}").format(
                sql.SQL(verb), sql.Identifier(RUNTIME_ROLE), sql.Literal(secret)
            )
        )
        connection.execute("REVOKE CREATE ON SCHEMA public FROM PUBLIC")
        connection.execute("GRANT USAGE ON SCHEMA business, checkpoints TO commerceops_app")
        # 显式列出业务表，未来新增实体必须另行审查授权；不允许历史删除。
        connection.execute("""
GRANT SELECT, INSERT, UPDATE ON business.organizations, business.shops, business.principals,
 business.identities, business.conversations, business.inbox_events, business.business_tasks,
 business.jobs TO commerceops_app
""")
        connection.execute("GRANT SELECT ON business.principal_shop_scopes TO commerceops_app")
        connection.execute("""GRANT SELECT, INSERT ON business.explanation_links,
            business.model_calls,business.model_call_observations,business.model_explanations,
            business.explanation_task_results,business.inventory_intent_requests,
            business.inventory_intent_results TO commerceops_app""")
        connection.execute("""GRANT SELECT, INSERT ON business.model_stage_budgets
            TO commerceops_app""")
        connection.execute("""GRANT UPDATE(reserved_count,reserved_nanos,halted,updated_at)
            ON business.model_stage_budgets TO commerceops_app""")
        connection.execute("""GRANT EXECUTE ON FUNCTION business.lock_inventory_permission(
            uuid,uuid,uuid,uuid,bigint) TO commerceops_app""")
        connection.execute("""GRANT SELECT, INSERT ON business.commerce_snapshots,
            business.snapshot_products,business.snapshot_order_lines,business.snapshot_refunds,
            business.analysis_reports TO commerceops_app""")
        connection.execute("""REVOKE UPDATE, DELETE, TRUNCATE ON business.commerce_snapshots,
            business.snapshot_products,business.snapshot_order_lines,business.snapshot_refunds,
            business.analysis_reports FROM commerceops_app""")
        connection.execute("GRANT SELECT, INSERT ON business.audit_events TO commerceops_app")
        connection.execute(
            "REVOKE UPDATE, DELETE, TRUNCATE ON business.audit_events FROM commerceops_app"
        )
        connection.execute(
            "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA checkpoints "
            "TO commerceops_app"
        )
        connection.execute("""GRANT SELECT ON business.principal_role_shop_grants,
            business.web_credentials TO commerceops_app""")
        connection.execute("""GRANT SELECT,INSERT,UPDATE ON business.web_sessions,
            business.web_login_attempts,business.web_requests,business.p3_task_sources,
            business.replenishment_plans,business.approvals,business.outbox TO commerceops_app""")
        connection.execute("""GRANT EXECUTE ON FUNCTION business.lock_p3_permission(
            uuid,uuid,uuid,uuid,bigint,text) TO commerceops_app""")
        connection.execute(
            "GRANT SELECT,INSERT,UPDATE ON business.approval_resumes TO commerceops_app"
        )
        connection.execute("""GRANT SELECT,INSERT ON business.p3_observations,
            business.p3_revalidation_failures,business.outbox_reconciliations TO commerceops_app""")
        connection.execute(
            "GRANT SELECT,INSERT ON business.p3_revalidation_transitions TO commerceops_app"
        )
        connection.execute("""GRANT UPDATE(applied_at,applied_checkpoint_id)
            ON business.p3_revalidation_transitions TO commerceops_app""")
        connection.execute("GRANT SELECT,INSERT ON business.executions TO commerceops_app")
        connection.execute("GRANT SELECT,INSERT ON business.p3_template_results TO commerceops_app")
        connection.execute("GRANT SELECT,INSERT ON business.p4_read_replies TO commerceops_app")
        connection.execute("""GRANT UPDATE(status,attempts,claimed_by,first_attempt_at,
            message_id,last_error)
            ON business.p4_read_replies TO commerceops_app""")
        connection.execute(
            "REVOKE DELETE,TRUNCATE ON business.p4_read_replies FROM commerceops_app"
        )
        connection.execute(
            "GRANT EXECUTE ON FUNCTION business.p4_read_reply_current(uuid) TO commerceops_app"
        )
        connection.execute("""GRANT UPDATE(status,completed_at,item_ids)
            ON business.executions TO commerceops_app""")
        connection.execute(
            "GRANT SELECT,INSERT,UPDATE ON business.replenishment_items TO commerceops_app"
        )

        connection.execute("""GRANT SELECT,INSERT ON business.p4_inbox_receipts,
            business.p4_card_bindings TO commerceops_app""")
        connection.execute("""GRANT SELECT,INSERT,UPDATE ON business.p4_clarification_replies
            TO commerceops_app""")
        if legacy_revision != "0015":
            connection.execute("""GRANT SELECT,INSERT ON business.p4_clarification_requests
                TO commerceops_app""")
        if legacy_revision is None:
            connection.execute("""GRANT SELECT,INSERT ON business.p4_history_recoveries,
                business.p4_history_messages,business.p4_read_message_sources TO commerceops_app""")
            connection.execute("""GRANT UPDATE(status,pages,completed_at,error_code)
                ON business.p4_history_recoveries TO commerceops_app""")
            connection.execute("""REVOKE UPDATE,DELETE,TRUNCATE ON business.p4_history_messages,
                business.p4_read_message_sources FROM commerceops_app""")
            connection.execute(
                "REVOKE DELETE,TRUNCATE ON business.p4_history_recoveries FROM commerceops_app"
            )
            connection.execute("""GRANT UPDATE(round,candidate,candidate_hash,state,task_id,
                confirmed_inbox_id,updated_at) ON business.p4_clarification_requests
                TO commerceops_app""")
        connection.execute("""GRANT SELECT,INSERT,UPDATE ON business.p4_base_deliveries
            TO commerceops_app""")
        connection.execute("GRANT SELECT,INSERT ON business.p4_base_links TO commerceops_app")
        connection.execute(
            "GRANT SELECT,INSERT,UPDATE ON business.p4_sender_state TO commerceops_app"
        )
        # SELECT FOR UPDATE用于原window cap串行；immutable trigger仍拒绝任何行修改。
        connection.execute(
            "GRANT SELECT,INSERT,UPDATE ON business.p4_sdk_windows TO commerceops_app"
        )
        connection.execute(
            "GRANT SELECT,INSERT,UPDATE ON business.p4_sdk_calls,"
            "business.p4_im_deliveries TO commerceops_app"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="PG initialization (separate deploy tasks)")
    parser.add_argument(
        "action", choices=["migrate", "setup-checkpointer", "grant-runtime", "revision"]
    )
    arguments = parser.parse_args()
    try:
        settings = DatabaseSettings()
        match arguments.action:
            case "migrate":
                migrate(settings)
            case "setup-checkpointer":
                asyncio.run(setup_checkpointer(settings))
            case "grant-runtime":
                grant_runtime(settings)
            case "revision":
                with connect(settings) as connection:
                    row = connection.execute(
                        "SELECT version_num FROM business.alembic_version"
                    ).fetchone()
                    if row is None:
                        raise RuntimeError("missing revision")
                    print(f"business revision: {row['version_num']}")
    except Exception:
        # 官方 setup 使用 autocommit；重跑恢复，不输出原始数据库错误。
        raise SystemExit(
            f"database {arguments.action} failed; inspect isolated DB safely"
        ) from None
    print(f"database {arguments.action}: ok")


if __name__ == "__main__":
    main()
