"""Add ATS minimum score threshold to policy config."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "004_ats_min_score"
down_revision: Union[str, None] = "003_job_sourcing"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add ats_min_score column for document critic pass threshold."""
    op.add_column(
        "policy_config",
        sa.Column("ats_min_score", sa.Float(), nullable=False, server_default="0.7"),
    )


def downgrade() -> None:
    """Remove ats_min_score column."""
    op.drop_column("policy_config", "ats_min_score")
