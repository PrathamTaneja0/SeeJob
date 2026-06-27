"""Add profile_documents table for supporting document uploads."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "007_profile_documents"
down_revision: Union[str, None] = "006_pipeline_claim"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create profile_documents table."""
    op.create_table(
        "profile_documents",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("person_id", sa.Integer(), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=True),
        sa.Column("filename", sa.String(length=500), nullable=False),
        sa.Column("path", sa.String(length=1000), nullable=False),
        sa.Column(
            "uploaded_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["person_id"], ["persons.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_profile_documents_person_id"),
        "profile_documents",
        ["person_id"],
        unique=False,
    )


def downgrade() -> None:
    """Drop profile_documents table."""
    op.drop_index(op.f("ix_profile_documents_person_id"), table_name="profile_documents")
    op.drop_table("profile_documents")
