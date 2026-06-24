"""Add pipeline orchestration fields — interrupt metadata and sourcing interval."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "005_pipeline_orchestration"
down_revision: Union[str, None] = "004_ats_min_score"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add interrupt metadata on applications and sourcing interval on policy."""
    op.add_column(
        "applications",
        sa.Column("interrupt_metadata_json", sa.Text(), nullable=True),
    )
    op.add_column(
        "policy_config",
        sa.Column(
            "sourcing_interval_minutes",
            sa.Integer(),
            nullable=False,
            server_default="60",
        ),
    )


def downgrade() -> None:
    """Remove pipeline orchestration columns."""
    op.drop_column("policy_config", "sourcing_interval_minutes")
    op.drop_column("applications", "interrupt_metadata_json")
