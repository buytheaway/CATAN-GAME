"""Nullable origin budget metadata; never infer or backfill legacy origins."""
from alembic import op
import sqlalchemy as sa

revision = "sec03a001"
down_revision = "f2a001"
branch_labels = depends_on = None


def upgrade():
    op.add_column("rooms", sa.Column("creation_peer_hash", sa.LargeBinary(), nullable=True))
    op.create_index("rooms_creation_peer", "rooms", ["creation_peer_hash", "created_at"])


def downgrade():
    op.drop_index("rooms_creation_peer", table_name="rooms")
    op.drop_column("rooms", "creation_peer_hash")
