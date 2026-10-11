"""Store private image ownership and support modern password hashes.

Revision ID: 0002
Revises: 0001
"""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("user") as batch:
        batch.alter_column(
            "password", existing_type=sa.String(60), type_=sa.String(255), existing_nullable=False
        )
    with op.batch_alter_table("scans") as batch:
        batch.add_column(sa.Column("filename", sa.String(100), nullable=True))
        batch.create_unique_constraint("uq_scans_filename", ["filename"])
        batch.create_index("ix_scans_user_id", ["user_id"])


def downgrade():
    # Prevent silently truncating modern scrypt password hashes.
    connection = op.get_bind()
    if connection.scalar(sa.text('SELECT COUNT(*) FROM "user" WHERE length(password) > 60')):
        raise RuntimeError("Cannot downgrade: password hashes require the wider column.")
    with op.batch_alter_table("scans") as batch:
        batch.drop_index("ix_scans_user_id")
        batch.drop_constraint("uq_scans_filename", type_="unique")
        batch.drop_column("filename")
    with op.batch_alter_table("user") as batch:
        batch.alter_column(
            "password", existing_type=sa.String(255), type_=sa.String(60), existing_nullable=False
        )
