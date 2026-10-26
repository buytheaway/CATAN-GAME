"""Default-off owner preference; no account lookup, backfill or role assignment."""
from alembic import op
import sqlalchemy as sa

revision = "owner01"
down_revision = "sec03a001"
branch_labels = depends_on = None


def upgrade():
    op.add_column("users", sa.Column("test_tools_enabled", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade():
    op.drop_column("users", "test_tools_enabled")
