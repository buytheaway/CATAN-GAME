"""Accounts and opaque sessions; existing guest members remain NULL-owned."""
from alembic import op
import sqlalchemy as sa

revision = "f1a001"
down_revision = "ab68cc7c6ebb"
branch_labels = depends_on = None


def upgrade():
    op.create_table("users",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("username", sa.Text(), nullable=False),
        sa.Column("username_normalized", sa.Text(), nullable=False, unique=True),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("disabled_at", sa.DateTime(timezone=True)))
    op.create_table("user_sessions",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("user_id", sa.UUID(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("token_hash", sa.LargeBinary(), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("octet_length(token_hash) = 32", name="session_hash_length"))
    op.create_index("sessions_user", "user_sessions", ["user_id"])
    op.create_index("sessions_active_expiry", "user_sessions", ["expires_at"], postgresql_where=sa.text("revoked_at IS NULL"))
    op.add_column("room_players", sa.Column("user_id", sa.UUID(), nullable=True))
    op.create_foreign_key("room_player_user", "room_players", "users", ["user_id"], ["id"])
    op.create_index("room_active_user", "room_players", ["room_id", "user_id"], unique=True,
                    postgresql_where=sa.text("status = 'active' AND user_id IS NOT NULL"))


def downgrade():
    op.drop_index("room_active_user", table_name="room_players")
    op.drop_constraint("room_player_user", "room_players", type_="foreignkey")
    op.drop_column("room_players", "user_id")
    op.drop_table("user_sessions")
    op.drop_table("users")
