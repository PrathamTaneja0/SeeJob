"""Add pipeline claim timestamp for concurrent tick protection."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "006_pipeline_claim"
down_revision: Union[str, None] = "005_pipeline_orchestration"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add lease timestamp used to claim applications during pipeline ticks."""
    op.add_column(
        "applications",
        sa.Column("pipeline_claimed_at", sa.String(length=50), nullable=True),
    )


def downgrade() -> None:
    """Remove pipeline claim column."""
    op.drop_column("applications", "pipeline_claimed_at")
