"""Relational API baseline; adopt existing SQLite auth/job tables in place."""
from alembic import op
import sqlalchemy as sa

revision = "0001_database"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # Frozen definitions: later application model changes must not rewrite this migration.
    meta = sa.MetaData()
    sa.Table("users", meta,
             sa.Column("id", sa.Integer, primary_key=True),
             sa.Column("email", sa.Text, nullable=False, unique=True),
             sa.Column("pw", sa.Text, nullable=False),
             sa.Column("settings", sa.LargeBinary), sa.Column("schedule", sa.Text),
             sa.Column("created_at", sa.Text))
    sa.Table("sessions", meta,
             sa.Column("token", sa.Text, primary_key=True),
             sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
             sa.Column("created_at", sa.Float))
    sa.Table("jobs", meta,
             sa.Column("id", sa.Integer, primary_key=True),
             sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
             sa.Column("command", sa.Text), sa.Column("args", sa.Text),
             sa.Column("status", sa.Text), sa.Column("pid", sa.Integer),
             sa.Column("started_at", sa.Text), sa.Column("finished_at", sa.Text),
             sa.Column("exit_code", sa.Integer))
    sa.Table("waitlist", meta, sa.Column("email", sa.Text, primary_key=True),
             sa.Column("created_at", sa.Text))
    table = sa.Table("researchers", meta,
             sa.Column("id", sa.Integer, primary_key=True),
             sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
             sa.Column("name", sa.Text, nullable=False),
             sa.Column("email", sa.Text),
             sa.Column("institution", sa.Text, nullable=False),
             sa.Column("country", sa.Text, nullable=False),
             sa.Column("research_area", sa.Text, nullable=False),
             sa.Column("notes", sa.Text, nullable=False),
             sa.Column("created_at", sa.Text, nullable=False),
             sa.Column("updated_at", sa.Text, nullable=False),
             sa.UniqueConstraint("user_id", "email", name="uq_researchers_user_email"))
    sa.Index("ix_researchers_user_id", table.c.user_id, table.c.id)
    meta.create_all(op.get_bind(), checkfirst=True)


def downgrade():
    raise RuntimeError("Baseline downgrade is disabled to protect existing accounts and records.")
