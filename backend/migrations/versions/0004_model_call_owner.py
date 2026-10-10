"""P204调用绑定原Worker owner；保留旧ledger，NULL旧owner按未知处理。"""

from alembic import op

revision = "0004_model_call_owner"
down_revision = "0003_inventory_explanations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 只追加列，不回填/删除不可变调用，不改变既有预留或halt。
    op.execute("ALTER TABLE business.model_calls ADD COLUMN worker_owner uuid")


def downgrade() -> None:
    raise RuntimeError("destructive downgrade disabled; restore verified backup")
