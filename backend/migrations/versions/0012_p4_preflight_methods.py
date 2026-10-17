"""显式认证一次与原已授bot读取；不增加其他平台接口或复位窗口。"""

from alembic import op

revision = "0012_p4_preflight_methods"
down_revision = "0011_p4_sdk_ledger"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""ALTER TABLE business.p4_sdk_calls
    DROP CONSTRAINT p4_sdk_calls_method_check""")
    op.execute("""ALTER TABLE business.p4_sdk_calls ADD CONSTRAINT p4_sdk_calls_method_check
    CHECK(method IN ('auth.v3.tenant_access_token.internal','bot.v3.info',
    'im.v1.message.create','bitable.v1.app_table_record.create',
    'bitable.v1.app_table_record.list','bitable.v1.app_table_record.update',
    'bitable.v1.app_table.list','bitable.v1.app_table_field.list'))""")


def downgrade() -> None:
    raise RuntimeError("P4 original authentication call history cannot be discarded")
