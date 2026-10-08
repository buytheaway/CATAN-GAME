"""Explicit match ruleset provenance; legacy rows deliberately remain NULL."""
from alembic import op
import sqlalchemy as sa

revision = "f2a001"
down_revision = "f1a001"
branch_labels = depends_on = None


def upgrade():
    op.add_column("matches", sa.Column("ruleset_id", sa.Text(), nullable=True))


def downgrade():
    op.drop_column("matches", "ruleset_id")
